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
    start_time = time.time()
    
    try:
        # Estrai dati immediatamente
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        # Log dettagliato per debug
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"🔵 [{timestamp}] WEBHOOK: '{incoming_msg}' da {from_number}")
        
        # Risposta immediata se il messaggio è vuoto
        if not incoming_msg:
            print("⚠️ Messaggio vuoto, ignoro")
            return Response(status=200)

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: 
            print(f"❌ Business non trovato per: {to_number}")
            return Response(status=200)
            
        business_id = business['_id']
        print(f"✅ Business: {business.get('business_name')}")

        # Recupera cronologia conversazione (limitata)
        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = conversation.get('messages', []) if conversation else []
        
        # Mantieni solo ultimi 8 messaggi per ridurre memory usage
        if len(messages_history) > 8:
            messages_history = messages_history[-8:]

        # System prompt ottimizzato
        system_prompt = f"""
        Sei un assistente AI per '{business.get('business_name', 'questo business')}'.
        Parli in modo professionale, gestisci quando lo chiedono una prenotazione e dare info sul business.
        RISPETTA SEMPRE LE REGOLE
        
        DATA: {datetime.now().strftime('%Y-%m-%d')} - ORA: {datetime.now().strftime('%H:%M')}
        
        REGOLE:
        - "oggi" = {datetime.now().strftime('%Y-%m-%d')}
        - "domani" = {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}
        - "prima possibile" = usa get_next_available_slot
        - Sii breve e diretto
        - Non accettare richieste non correlate alle prenotazioni
        """
        
        # Costruisci messaggi API (limitati per velocità)
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages_history[-6:])  # Solo ultimi 6
        api_messages.append({"role": "user", "content": incoming_msg})

        # Loop AI con timeout stringente
        max_iterations = 2  # Ridotto drasticamente
        timeout_seconds = 12  # Timeout molto aggressivo
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Controllo timeout critico
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                print(f"⏰ TIMEOUT dopo {elapsed:.2f}s")
                final_response_text = "Elaboro la richiesta, un momento..."
                break
            
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o", 
                    messages=api_messages, 
                    tools=tools, 
                    tool_choice="auto",
                    temperature=0.1,  # Ridotta per risposte più deterministiche
                    max_tokens=300    # Limita lunghezza risposta
                )
                response_message = response.choices[0].message
            except Exception as e:
                print(f"❌ Errore OpenAI: {e}")
                final_response_text = "Problema tecnico temporaneo, riprova."
                break

            # Se nessun tool call, abbiamo la risposta finale
            if not response_message.tool_calls:
                final_response_text = response_message.content
                break
            
            # Aggiungi messaggio assistant
            assistant_message = {
                "role": "assistant",
                "content": response_message.content or "",
            }
            
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

            # Esegui tool calls
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                
                # Timeout check per ogni tool call
                if time.time() - start_time > timeout_seconds:
                    final_response_text = "Elaboro la richiesta, un momento..."
                    break
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    function_response = "Errore nei parametri della funzione"
                else:
                    function_args.update({
                        'business_id': business_id, 
                        'user_id': from_number, 
                        'user_name': user_name
                    })

                    print(f"🛠️ Chiamo: {function_name}")
                    
                    try:
                        function_to_call = getattr(bot_tools, function_name)
                        function_response = function_to_call(**function_args)
                    except AttributeError:
                        function_response = f"Funzione {function_name} non trovata"
                    except Exception as e:
                        print(f"❌ Errore in {function_name}: {e}")
                        function_response = "Errore temporaneo nella funzione"
                
                api_messages.append({
                    "tool_call_id": tool_call.id, 
                    "role": "tool",
                    "name": function_name, 
                    "content": str(function_response),
                })
        
        # Fallback se non abbiamo risposta finale
        if 'final_response_text' not in locals():
            final_response_text = "Un momento, sto elaborando..."

        # Salva cronologia (molto limitata)
        messages_to_save = messages_history + [
            {"role": "user", "content": incoming_msg},
            {"role": "assistant", "content": final_response_text}
        ]
        
        # Mantieni solo ultimi 10 messaggi totali
        if len(messages_to_save) > 10:
            messages_to_save = messages_to_save[-10:]
        
        # Update database
        try:
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
        except Exception as e:
            print(f"⚠️ Errore salvataggio DB: {e}")

        elapsed = time.time() - start_time
        print(f"📤 [{elapsed:.2f}s] Risposta: '{final_response_text[:50]}...'")
        
        # Risposta WhatsApp
        resp = MessagingResponse()
        resp.message(final_response_text)
        return Response(str(resp), mimetype='text/xml')

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"💥 CRASH dopo {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        
        # Risposta di emergenza
        try:
            resp = MessagingResponse()
            resp.message("Problema tecnico, riprova tra poco.")
            return Response(str(resp), mimetype='text/xml')
        except:
            return Response(status=500)

@app.route('/health', methods=['GET'])
def health_check():
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat(),
        "uptime": "Railway bot attivo"
    }

@app.route('/test', methods=['GET'])
def test():
    return f"Server OK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Bot starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)