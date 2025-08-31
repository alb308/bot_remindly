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

tools = [
    {
        "type": "function", "function": {
            "name": "get_available_slots", "description": "Trova gli orari disponibili per un servizio in una data specifica.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"} }, "required": ["service_name", "date"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "get_next_available_slot", "description": "Trova il primo orario disponibile per un servizio, partendo da oggi. Da usare quando l'utente chiede 'il prima possibile', 'quando puoi', o non specifica una data.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"} }, "required": ["service_name"] },
        },
    },
    {
        "type": "function", "function": {
            "name": "create_or_update_booking", "description": "Crea o aggiorna un appuntamento. Usala SOLO quando hai la conferma esplicita del servizio, della data e dell'ora.",
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

def create_twilio_response(message):
    resp = MessagingResponse()
    resp.message(message)
    return Response(str(resp), mimetype='text/xml', status=200)

@app.route('/webhook', methods=['POST'])
def webhook():
    start_time = time.time()
    final_response_text = "Mi dispiace, non sono riuscito a elaborare la tua richiesta. Potresti riprovare a scriverla in modo diverso?"
    
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        if not all([incoming_msg, from_number, to_number]):
            return create_twilio_response("Errore nel messaggio ricevuto.")

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: 
            return create_twilio_response("Questo numero non è configurato per le prenotazioni.")
        
        business_id = business['_id']
        print(f"✅ Richiesta per: {business.get('business_name')}")

        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = conversation.get('messages', [])[-6:] if conversation else [] # Aumentata la cronologia

        # Estrae i servizi per il prompt
        services_list = []
        services_data = business.get("services")
        if isinstance(services_data, list): services_list = services_data
        elif isinstance(services_data, str) and services_data.strip(): services_list = json.loads(services_data)
        service_names = [s.get('name') for s in services_list if s.get('name')]
        services_prompt_part = f"I servizi disponibili sono: {', '.join(service_names)}." if service_names else ""

        system_prompt = f"""
Sei un assistente AI per '{business.get('business_name')}', la tua specialità è prenotare appuntamenti in modo efficiente e naturale.
Data e ora attuali: {datetime.now().strftime('%Y-%m-%d %H:%M')}.

**MEMORIA E CONTESTO (REGOLA FONDAMENTALE):**
- **Ricorda sempre i messaggi precedenti!** Se l'utente ha già specificato un servizio (es. "taglio capelli") e poi dice "il prima possibile", devi capire che sta chiedendo il primo orario per il servizio di taglio. NON chiedere di nuovo il servizio.
- **Deduci il servizio:** Se l'utente chiede "per tagliare i capelli", devi associarlo al servizio più pertinente (es. "Taglio" o "Taglio uomo") e usarlo per la funzione `get_next_available_slot`.
- **Riempi le informazioni mancanti:** Il tuo obiettivo è raccogliere `service_name`, `date` e `time`. Usa la conversazione per ottenere le informazioni una per una. Se hai già il servizio, chiedi la data. Se hai entrambi, propon gli orari.

**FLUSSO DI LAVORO:**
1.  L'utente esprime un'intenzione (es. "vorrei un appuntamento").
2.  Identifica il `service_name` dalla sua richiesta. Se non è chiaro, chiediglielo.
3.  Una volta ottenuto il servizio, cerca la disponibilità usando `get_next_available_slot` (se non dà una data) o `get_available_slots` (se la dà).
4.  Proponi gli orari all'utente.
5.  Quando l'utente conferma un orario, e SOLO ALLORA, usa `create_or_update_booking`.

{services_prompt_part}
Sii sempre conciso e vai dritto al punto.
"""
        
        api_messages = [{"role": "system", "content": system_prompt}] + messages_history + [{"role": "user", "content": incoming_msg}]

        for i in range(3): # Aumentato a 3 iterazioni per conversazioni più complesse
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=api_messages, 
                tools=tools, 
                tool_choice="auto",
                temperature=0.0
            )
            response_message = response.choices[0].message

            if not response_message.tool_calls:
                final_response_text = response_message.content
                break
            
            api_messages.append(response_message)
            tool_calls = response_message.tool_calls

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                function_args.update({'business_id': business_id, 'user_id': from_number, 'user_name': user_name})
                
                print(f"🛠️ Iter. {i+1}: Eseguo {function_name}({function_args.get('service_name', '')}, {function_args.get('date', '')})")
                
                function_to_call = getattr(bot_tools, function_name)
                function_response = function_to_call(**function_args)
                
                api_messages.append({
                    "tool_call_id": tool_call.id, 
                    "role": "tool",
                    "name": function_name, 
                    "content": str(function_response),
                })
        
        # Chiamata finale per generare una risposta testuale basata sul risultato dei tool
        if response_message.tool_calls:
            final_response = openai_client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=api_messages,
                temperature=0.1
            )
            final_response_text = final_response.choices[0].message.content

    except Exception as e:
        print(f"💥 ERRORE GLOBALE nel webhook: {e}\n{traceback.format_exc()}")
        final_response_text = "Si è verificato un errore generale. Il nostro team è stato notificato. Riprova tra qualche istante."

    # Salvataggio conversazione (logica invariata)
    try:
        updated_history = messages_history + [
            {"role": "user", "content": incoming_msg},
            {"role": "assistant", "content": final_response_text}
        ]
        db.conversations.update_one(
            {"user_id": from_number, "business_id": business_id},
            {"$set": {"messages": updated_history[-8:], "last_interaction": datetime.now().isoformat()}},
            upsert=True
        )
    except Exception as e:
        print(f"⚠️ Errore salvataggio DB (non critico): {e}")

    print(f"📤 Risposta finale: '{final_response_text[:80]}...'")
    return create_twilio_response(final_response_text)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)