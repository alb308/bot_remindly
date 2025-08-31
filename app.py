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
import traceback

load_dotenv()
app = Flask(__name__)

db = db_connection
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Definizione dei tools rimane invariata...
tools = [
    {
        "type": "function", "function": {
            "name": "get_available_slots", "description": "Trova gli orari disponibili per un servizio in una data specifica.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"} }, "required": ["service_name", "date"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "get_next_available_slot", "description": "Trova il primo orario disponibile per un servizio (oggi o domani). Da usare quando l'utente chiede 'il prima possibile' o simili.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"} }, "required": ["service_name"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "create_or_update_booking", "description": "Crea o aggiorna un appuntamento dopo aver confermato data e ora.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"} }, "required": ["service_name", "date", "time"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "cancel_booking", "description": "Cancella l'ultimo appuntamento confermato di un utente.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function", "function": {
            "name": "get_business_info", "description": "Recupera informazioni generali sul business (orari, indirizzo, lista servizi).",
            "parameters": {"type": "object", "properties": {}},
        }
    }
]


def create_user_friendly_response(message="Non ho capito bene, potresti riformulare la tua richiesta? Prova a essere più specifico, ad esempio: 'Vorrei un appuntamento per un taglio domani pomeriggio.'"):
    """Crea una risposta di errore standardizzata e user-friendly."""
    resp = MessagingResponse()
    resp.message(message)
    return Response(str(resp), mimetype='text/xml', status=200)

@app.route('/webhook', methods=['POST'])
def webhook():
    start_time = time.time()
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        if not all([incoming_msg, from_number, to_number]):
            print("⚠️ Webhook con dati mancanti.")
            return create_user_friendly_response("Errore nel messaggio ricevuto, riprova.")

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: 
            print(f"❌ Business non trovato per il numero: {to_number}")
            return create_user_friendly_response("Questo numero non è configurato per le prenotazioni.")
        
        business_id = business['_id']
        print(f"✅ Richiesta per: {business.get('business_name')}")

        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = conversation.get('messages', [])[-4:] if conversation else []

        # Estrae i servizi per il prompt
        services_list = []
        services_data = business.get("services")
        if isinstance(services_data, list): services_list = services_data
        elif isinstance(services_data, str): services_list = json.loads(services_data)
        service_names = [s.get('name') for s in services_list if s.get('name')]
        services_prompt_part = f"I servizi che offriamo sono: {', '.join(service_names)}." if service_names else ""

        system_prompt = f"""
Sei un assistente virtuale per '{business.get('business_name', 'il business')}', specializzato nella gestione di appuntamenti.
Il tuo tono è professionale, ma amichevole e molto conciso.
Data e ora attuali: {datetime.now().strftime('%Y-%m-%d %H:%M')}.
{services_prompt_part}

REGOLE FONDAMENTALI:
- Prima di prenotare, assicurati sempre di avere il NOME DEL SERVIZIO, la DATA e l'ORA.
- Se l'utente non specifica un servizio, chiedi quale desidera tra quelli disponibili.
- Usa le funzioni a tua disposizione per trovare disponibilità o prenotare.
- Se una funzione restituisce un errore (es. 'Servizio non trovato'), comunicalo all'utente e guida alla soluzione.
- Non inventare informazioni. Se non sai qualcosa, usa 'get_business_info'.
"""
        
        api_messages = [{"role": "system", "content": system_prompt}] + messages_history + [{"role": "user", "content": incoming_msg}]

        max_iterations = 2
        for i in range(max_iterations):
            try:
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=api_messages, 
                    tools=tools, 
                    tool_choice="auto",
                    temperature=0.0,
                    timeout=20
                )
                response_message = response.choices[0].message

                if not response_message.tool_calls:
                    final_response_text = response_message.content
                    break
                
                api_messages.append(response_message)

                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    function_args.update({'business_id': business_id, 'user_id': from_number, 'user_name': user_name})
                    
                    print(f"🛠️ Eseguo: {function_name} con args {function_args}")
                    function_to_call = getattr(bot_tools, function_name)
                    function_response = function_to_call(**function_args)
                    
                    api_messages.append({
                        "tool_call_id": tool_call.id, 
                        "role": "tool",
                        "name": function_name, 
                        "content": str(function_response),
                    })
                
                # Se è l'ultima iterazione, forza una risposta finale
                if i == max_iterations -1:
                    final_response = openai_client.chat.completions.create(model="gpt-4o-mini", messages=api_messages)
                    final_response_text = final_response.choices[0].message.content
                    break

            except Exception as e:
                print(f"❌ Errore durante il loop OpenAI: {e}")
                final_response_text = "Sto riscontrando un problema tecnico. Per favore, contatta direttamente il negozio per assistenza."
                break
        
        if not final_response_text:
             final_response_text = "Non sono riuscito a elaborare la tua richiesta. Potresti riprovare a scriverla in modo diverso?"

        # Aggiorna la cronologia della conversazione...
        # (la tua logica di salvataggio è corretta)

        print(f"📤 Risposta: '{final_response_text[:80]}...'")
        return create_user_friendly_response(final_response_text)

    except Exception as e:
        print(f"💥 ERRORE GLOBALE nel webhook: {e}\n{traceback.format_exc()}")
        return create_user_friendly_response("Si è verificato un errore generale. Il nostro team è stato notificato. Riprova tra qualche istante.")

# Le route /health e /test e gli error handler rimangono invariati.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)