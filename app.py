import os
import json
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from database import db_connection
import bot_tools

load_dotenv()
app = Flask(__name__)

db = db_connection
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

tools = [
    {
        "type": "function", "function": {
            "name": "get_available_slots", "description": "Trova gli orari disponibili per un servizio in una data specifica.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"} }, "required": ["service_name", "date"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "get_next_available_slot", "description": "Trova il primo orario disponibile per un servizio (oggi o domani). Usa questa funzione quando l'utente dice 'prima possibile', 'il prima possibile', 'primo disponibile'.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"} }, "required": ["service_name"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "create_or_update_booking", "description": "Crea o aggiorna un appuntamento.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"} }, "required": ["service_name", "date", "time"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "cancel_booking", "description": "Cancella l'ultimo appuntamento di un utente.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function", "function": {
            "name": "get_business_info", "description": "Recupera le informazioni generali sul business (orari, indirizzo, servizi).",
            "parameters": {"type": "object", "properties": {}},
        }
    }
]

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Estrai dati immediatamente
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        # Log immediato per debug
        print(f"🔵 WEBHOOK RICEVUTO: '{incoming_msg}' da {from_number} alle {datetime.now().strftime('%H:%M:%S')}")
        
        # Risposta immediata se il messaggio è vuoto
        if not incoming_msg:
            print("⚠️ Messaggio vuoto, ignoro")
            return Response(status=200)

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: 
            print(f"❌ Business non trovato per numero: {to_number}")
            return Response(status=200)
        business_id = business['_id']
        
        print(f"✅ Business trovato: {business.get('business_name')}")

        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = conversation.get('messages', []) if conversation else []

        system_prompt = f"""
        Sei un assistente AI professionale per '{business.get('business_name', 'questo business')}'.
        Il tuo unico scopo è gestire prenotazioni e dare informazioni su questo business.
        
        DATA ATTUALE: {datetime.now().strftime('%Y-%m-%d')} (oggi)
        ORA ATTUALE: {datetime.now().strftime('%H:%M')}
        
        Regole importanti:
        - Quando l'utente dice "oggi", usa la data attuale: {datetime.now().strftime('%Y-%m-%d')}
        - Quando dice "domani", usa: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
        - Quando dice "il prima possibile", "prima possibile", "il primo disponibile":
          1. Cerca prima gli slot disponibili per OGGI {datetime.now().strftime('%Y-%m-%d')}
          2. Se non ci sono, prova domani {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
          3. Proponi SUBITO il primo orario trovato senza chiedere conferma della data
        - Se menziona solo un orario senza data, assumi OGGI se l'orario non è passato
        - Usa sempre il formato YYYY-MM-DD per le date nelle funzioni
        - Sii breve, diretto e non chiedere conferme inutili
        - Se qualcuno chiede qualcosa che non riguarda prenotazioni, rispondi cortesemente che puoi aiutare solo con prenotazioni e informazioni sul servizio
        
        ESEMPI DI COMPORTAMENTO CORRETTO:
        - User: "il prima possibile per un taglio" → Cerca subito oggi, se trovi slot proponi il primo
        - User: "domani alle 10" → Controlla se le 10 sono disponibili domani
        - User: "alle 15" → Assumi oggi se non sono ancora le 15, altrimenti chiedi quale giorno
        """
        
        # Costruisce la sequenza di messaggi per l'API
        api_messages = [{"role": "system", "content": system_prompt}]
        # Prendi solo gli ultimi 10 messaggi per evitare token limite
        api_messages.extend(messages_history[-10:])
        api_messages.append({"role": "user", "content": incoming_msg})

        # Ciclo di conversazione con l'AI
        max_iterations = 3  # Ridotto per evitare timeout
        iteration = 0
        start_time = time.time()
        timeout_seconds = 25  # Timeout prima dei 30s di Twilio
        
        while iteration < max_iterations:
            iteration += 1
            
            # Controllo timeout
            if time.time() - start_time > timeout_seconds:
                final_response_text = "Sto elaborando la tua richiesta, ti rispondo tra poco."
                break
            
            response = openai_client.chat.completions.create(
                model="gpt-4o", 
                messages=api_messages, 
                tools=tools, 
                tool_choice="auto",
                temperature=0.3
            )
            response_message = response.choices[0].message

            # Se non ci sono tool calls, abbiamo la risposta finale
            if not response_message.tool_calls:
                final_response_text = response_message.content
                break
            
            # Aggiungi il messaggio dell'assistant con i tool calls
            assistant_message = {
                "role": "assistant",
                "content": response_message.content or "",
            }
            
            # Aggiungi i tool calls se presenti
            if response_message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments
                        }
                    }
                    for tool_call in response_message.tool_calls
                ]
            
            api_messages.append(assistant_message)

            # Esegui ogni tool call
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    print(f"Errore parsing argomenti function: {e}")
                    function_response = f"Errore: argomenti function non validi"
                else:
                    # Aggiungi parametri del contesto
                    function_args.update({
                        'business_id': business_id, 
                        'user_id': from_number, 
                        'user_name': user_name
                    })

                    print(f"🧠 AI chiama: {function_name} con args: {function_args}")
                    
                    try:
                        function_to_call = getattr(bot_tools, function_name)
                        function_response = function_to_call(**function_args)
                        print(f"✅ Risposta function: {function_response[:100]}...")
                    except AttributeError:
                        function_response = f"Errore: funzione {function_name} non trovata"
                        print(f"❌ Funzione {function_name} non esiste")
                    except Exception as e:
                        function_response = f"Errore nell'esecuzione della funzione: {str(e)}"
                        print(f"❌ Errore in {function_name}: {e}")
                
                # Aggiungi la risposta del tool
                api_messages.append({
                    "tool_call_id": tool_call.id, 
                    "role": "tool",
                    "name": function_name, 
                    "content": str(function_response),
                })
        
        # Se abbiamo raggiunto il limite di iterazioni senza una risposta finale
        if iteration >= max_iterations:
            final_response_text = "Mi dispiace, c'è stato un problema tecnico. Puoi riprovare?"
        
        # Aggiorna la cronologia - salva solo messaggi utente/assistente finali
        messages_to_save = messages_history + [
            {"role": "user", "content": incoming_msg},
            {"role": "assistant", "content": final_response_text}
        ]
        
        # Mantieni solo gli ultimi 20 messaggi per evitare database troppo grandi
        if len(messages_to_save) > 20:
            messages_to_save = messages_to_save[-20:]
        
        db.conversations.update_one(
            {"user_id": from_number, "business_id": business_id},
            {
                "$set": {
                    "messages": messages_to_save, 
                    "last_interaction": datetime.now().isoformat()
                }
            },
            upsert=True
        )

        print(f"📤 Risposta inviata: '{final_response_text[:70]}...'")
        
        # Invia risposta via WhatsApp
        resp = MessagingResponse()
        resp.message(final_response_text)
        return Response(str(resp), mimetype='text/xml')

    except Exception as e:
        print(f"💥 ERRORE CRITICO NEL WEBHOOK: {e}")
        import traceback
        traceback.print_exc()
        
        # Invia messaggio di errore all'utente
        try:
            resp = MessagingResponse()
            resp.message("Mi dispiace, c'è stato un problema tecnico. Riprova tra poco.")
            return Response(str(resp), mimetype='text/xml')
        except:
            return Response(status=500)

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint per verificare che il server sia attivo"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # debug=False in produzione