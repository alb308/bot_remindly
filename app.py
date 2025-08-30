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

def create_error_response(message="Servizio temporaneamente non disponibile. Riprova tra poco."):
    """Crea una risposta di errore standardizzata"""
    try:
        resp = MessagingResponse()
        resp.message(message)
        return Response(str(resp), mimetype='text/xml', status=200)
    except Exception:
        # Fallback estremo
        return Response(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Errore del sistema</Message></Response>', 
            mimetype='text/xml', 
            status=200
        )

@app.route('/webhook', methods=['POST'])
def webhook():
    start_time = time.time()
    
    try:
        # VALIDAZIONE IMMEDIATE DEI DATI
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"📱 [{timestamp}] WEBHOOK: '{incoming_msg}' da {from_number}")
        
        # CONTROLLO RAPIDO: Se dati essenziali mancano, errore immediato
        if not incoming_msg or not from_number or not to_number:
            print("⚠️ Dati webhook incompleti")
            return create_error_response("Dati messaggio incompleti")

        # CONTROLLO BUSINESS CON TIMEOUT
        try:
            business = db.businesses.find_one({"twilio_phone_number": to_number})
        except Exception as db_error:
            print(f"❌ Errore database: {db_error}")
            return create_error_response("Errore database temporaneo")
            
        if not business: 
            print(f"❌ Business non trovato per: {to_number}")
            return create_error_response("Configurazione non trovata")
            
        business_id = business['_id']
        print(f"✅ Business: {business.get('business_name')}")

        # CRONOLOGIA LIMITATA per velocità
        try:
            conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
            messages_history = conversation.get('messages', [])[-4:] if conversation else []
        except Exception as e:
            print(f"⚠️ Errore cronologia: {e}")
            messages_history = []

        # SYSTEM PROMPT CONCISO
        system_prompt = f"""
Sei un assistente per '{business.get('business_name', 'il business')}' specializzato in prenotazioni.
Risposte brevi e professionali.

DATA OGGI: {datetime.now().strftime('%Y-%m-%d')} - ORA: {datetime.now().strftime('%H:%M')}
DOMANI: {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}

REGOLE:
- "prima possibile" = usa get_next_available_slot
- Sii conciso e diretto
- Solo prenotazioni e info business
- Mai "sto elaborando" o "un momento"
"""
        
        # COSTRUISCI MESSAGGI API (minimo indispensabile)
        api_messages = [
            {"role": "system", "content": system_prompt},
            *messages_history[-3:],  # Solo ultimi 3 messaggi
            {"role": "user", "content": incoming_msg}
        ]

        # LOOP AI CON TIMEOUT RIGOROSO
        max_iterations = 2  # Ridotto a 2 per velocità
        iteration = 0
        final_response_text = None
        timeout_reached = False
        
        while iteration < max_iterations and not timeout_reached:
            iteration += 1
            elapsed = time.time() - start_time
            
            # TIMEOUT RIGIDO: Se già passati 20 secondi, esci
            if elapsed > 20:
                print(f"⏰ TIMEOUT raggiunto: {elapsed:.2f}s")
                timeout_reached = True
                break
            
            print(f"⏱️ Iterazione {iteration}, tempo: {elapsed:.2f}s")
            
            try:
                # TIMEOUT OPENAI RIDOTTO
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",  # Modello più veloce
                    messages=api_messages, 
                    tools=tools, 
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=200,  # Ridotto per velocità
                    timeout=15  # Timeout ridotto a 15 secondi
                )
                response_message = response.choices[0].message
            except Exception as e:
                print(f"❌ Errore OpenAI: {e}")
                final_response_text = "Non riesco a elaborare la richiesta. Contattaci direttamente."
                break

            # Se nessun tool call, abbiamo la risposta finale
            if not response_message.tool_calls:
                final_response_text = response_message.content
                break
            
            # GESTIONE TOOL CALLS VELOCE
            assistant_message = {
                "role": "assistant",
                "content": response_message.content or "",
                "tool_calls": [
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
            }
            api_messages.append(assistant_message)

            # ESECUZIONE TOOLS CON TIMEOUT
            for tool_call in response_message.tool_calls:
                # Controllo timeout prima di ogni tool call
                if time.time() - start_time > 22:
                    timeout_reached = True
                    break
                    
                function_name = tool_call.function.name
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                    function_args.update({
                        'business_id': business_id, 
                        'user_id': from_number, 
                        'user_name': user_name
                    })

                    print(f"🛠️ Eseguo: {function_name}")
                    
                    function_to_call = getattr(bot_tools, function_name)
                    function_response = function_to_call(**function_args)
                    
                except Exception as e:
                    print(f"❌ Errore in {function_name}: {e}")
                    function_response = "Errore nella funzione"
                
                api_messages.append({
                    "tool_call_id": tool_call.id, 
                    "role": "tool",
                    "name": function_name, 
                    "content": str(function_response),
                })
        
        # GESTIONE FINALE DELLA RISPOSTA
        if timeout_reached:
            final_response_text = "Richiesta in elaborazione. Ti risponderemo al più presto."
        elif not final_response_text:
            final_response_text = "Non sono riuscito a completare l'operazione. Riprova."

        # VALIDAZIONE LUNGHEZZA RISPOSTA
        if len(final_response_text) > 1600:  # Limite WhatsApp
            final_response_text = final_response_text[:1597] + "..."

        # SALVATAGGIO DATABASE ASINCRONO (senza bloccare la risposta)
        try:
            messages_to_save = messages_history + [
                {"role": "user", "content": incoming_msg},
                {"role": "assistant", "content": final_response_text}
            ][-6:]  # Solo ultimi 6 messaggi
            
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
            print(f"⚠️ Errore salvataggio DB (non critico): {e}")

        elapsed = time.time() - start_time
        print(f"📤 [{elapsed:.2f}s] Invio risposta: '{final_response_text[:50]}...'")
        
        # RISPOSTA TWIML ROBUSTA
        try:
            resp = MessagingResponse()
            msg = resp.message()
            msg.body(final_response_text)
            
            response_xml = str(resp)
            print(f"📋 TwiML generato: {response_xml[:200]}...")
            
            return Response(response_xml, mimetype='text/xml', status=200)
            
        except Exception as twiml_error:
            print(f"❌ Errore creazione TwiML: {twiml_error}")
            return create_error_response("Errore formattazione risposta")

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"💥 CRASH dopo {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        
        return create_error_response("Sistema temporaneamente non disponibile")

@app.route('/health', methods=['GET'])
def health_check():
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "service": "WhatsApp Bot v2.0"
    }, 200

@app.route('/test', methods=['GET'])
def test():
    return f"🤖 Bot OK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 200

# GESTIONE ERRORI GLOBALE
@app.errorhandler(500)
def handle_500(e):
    print(f"❌ Errore 500: {e}")
    return create_error_response("Errore interno del server")

@app.errorhandler(Exception)
def handle_exception(e):
    print(f"❌ Eccezione non gestita: {e}")
    return create_error_response("Errore imprevisto")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 WhatsApp Bot v2.0 avvio su porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False)