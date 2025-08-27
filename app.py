import os
import json
from datetime import datetime
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from db_sqlite import SQLiteClient
import bot_tools

load_dotenv()
app = Flask(__name__)

db = SQLiteClient
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Trova gli orari disponibili per un servizio specifico in una data specifica. Da usare quando un utente chiede la disponibilità.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Il nome del servizio richiesto dall'utente."},
                    "date": {"type": "string", "description": "La data richiesta, formattata come 'YYYY-MM-DD'. Se l'utente dice 'domani', calcola la data corretta."},
                },
                "required": ["service_name", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_update_booking",
            "description": "Crea un nuovo appuntamento o aggiorna uno esistente. Da usare quando l'utente conferma un orario specifico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "Il nome del servizio da prenotare."},
                    "date": {"type": "string", "description": "La data della prenotazione, formattata come 'YYYY-MM-DD'."},
                    "time": {"type": "string", "description": "L'ora della prenotazione, formattata come 'HH:MM'."},
                },
                "required": ["service_name", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancella l'ultimo appuntamento di un utente. Da usare quando l'utente dice che non può venire, ha un imprevisto o vuole disdire.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_business_info",
            "description": "Recupera le informazioni generali sul business. Da usare per domande su orari, indirizzo, servizi disponibili o descrizione.",
            "parameters": {"type": "object", "properties": {}},
        }
    }
]

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: return Response(status=200)
        business_id = business['_id']

        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = []
        if conversation and 'messages' in conversation:
            if isinstance(conversation['messages'], str):
                try: messages_history = json.loads(conversation['messages'])
                except json.JSONDecodeError: messages_history = []
            elif isinstance(conversation['messages'], list):
                messages_history = conversation['messages']

        system_prompt = f"""
        Sei un assistente AI professionale per '{business.get('business_name')}', un'attività di tipo '{business.get('business_type')}'.
        Il tuo unico scopo è aiutare gli utenti a gestire le prenotazioni e a ricevere informazioni relative a questo business.
        REGOLE FONDAMENTALI:
        1. Focalizzati al 100% sui tuoi compiti: prenotare, modificare, cancellare appuntamenti e fornire informazioni.
        2. NON DEVI rispondere a domande non pertinenti (meteo, matematica, cultura generale, etc.).
        3. Se un utente fa una domanda non pertinente, DEVI rispondere con una frase gentile per riportare la conversazione in argomento, come: "Mi dispiace, non sono programmato per questo. Posso però aiutarti a prenotare o darti informazioni sui nostri servizi."
        """
        
        # Aggiungi il messaggio dell'utente alla cronologia per questa interazione
        current_interaction_messages = messages_history[-10:] # Lavora con una cronologia recente
        current_interaction_messages.append({"role": "user", "content": incoming_msg})

        # Prepara i messaggi per l'API, includendo sempre il prompt di sistema
        api_messages = [{"role": "system", "content": system_prompt}] + current_interaction_messages

        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        # Aggiungi la decisione dell'AI alla cronologia di questa interazione
        current_interaction_messages.append(response_message.model_dump())

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                function_args['business_id'] = business_id
                function_args['user_id'] = from_number
                function_args['user_name'] = user_name

                print(f"🧠 AI ha scelto di chiamare: {function_name} con {function_args}")
                function_to_call = getattr(bot_tools, function_name)
                function_response = function_to_call(**function_args)
                
                # Aggiungi il risultato del tool alla cronologia di questa interazione
                current_interaction_messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
            
            # Prepara i messaggi per la seconda chiamata con il risultato del tool
            second_api_messages = [{"role": "system", "content": system_prompt}] + current_interaction_messages
            
            second_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=second_api_messages,
            )
            response_text = second_response.choices[0].message.content
        else:
            response_text = response_message.content

        # Aggiorna la cronologia principale con i messaggi di questa interazione
        messages_history.append({"role": "user", "content": incoming_msg})
        messages_history.append({"role": "assistant", "content": response_text})

        db.conversations.update_one(
            {"user_id": from_number, "business_id": business_id},
            {"$set": {"messages": messages_history, "last_interaction": datetime.now().isoformat()}},
            upsert=True
        )

        print(f"--- Risposta inviata: '{response_text[:70]}...' ---")
        resp = MessagingResponse()
        resp.message(response_text)
        return Response(str(resp), mimetype='text/xml')

    except Exception as e:
        print(f"--- ERRORE CRITICO E IMPREVISTO NEL WEBHOOK: {e} ---")
        import traceback
        traceback.print_exc()
        return Response(status=500)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)