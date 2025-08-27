import os
import json
from datetime import datetime
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
            "name": "get_available_slots", "description": "Trova gli orari disponibili per un servizio in una data.",
            "parameters": { "type": "object", "properties": { "service_name": {"type": "string"}, "date": {"type": "string"} }, "required": ["service_name", "date"] },
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
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business: return Response(status=200)
        business_id = business['_id']

        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages_history = conversation.get('messages', []) if conversation else []

        system_prompt = f"""
        Sei un assistente AI professionale per '{business.get('business_name')}'.
        Il tuo unico scopo è gestire prenotazioni e dare informazioni su questo business.
        Sii breve, professionale e non rispondere a domande non pertinenti.
        """
        
        # 1. Costruisce la sequenza di messaggi per l'API
        api_messages = [{"role": "system", "content": system_prompt}]
        api_messages.extend(messages_history[-10:])
        api_messages.append({"role": "user", "content": incoming_msg})

        # 2. Esegue il ciclo di conversazione con l'AI
        while True:
            response = openai_client.chat.completions.create(
                model="gpt-4o", messages=api_messages, tools=tools, tool_choice="auto",
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

                print(f"🧠 AI chiama: {function_name}")
                function_to_call = getattr(bot_tools, function_name)
                function_response = function_to_call(**function_args)
                
                api_messages.append({
                    "tool_call_id": tool_call.id, "role": "tool",
                    "name": function_name, "content": function_response,
                })
        
        # 3. Aggiorna la cronologia da salvare nel database
        # Salva solo i messaggi utente/assistente, non i passaggi intermedi
        messages_to_save = messages_history + [
            {"role": "user", "content": incoming_msg},
            {"role": "assistant", "content": final_response_text}
        ]
        
        db.conversations.update_one(
            {"user_id": from_number, "business_id": business_id},
            {"$set": {"messages": messages_to_save, "last_interaction": datetime.now().isoformat()}},
            upsert=True
        )

        print(f"--- Risposta inviata: '{final_response_text[:70]}...' ---")
        resp = MessagingResponse()
        resp.message(final_response_text)
        return Response(str(resp), mimetype='text/xml')

    except Exception as e:
        print(f"--- ERRORE CRITICO E IMPREVISTO NEL WEBHOOK: {e} ---")
        import traceback
        traceback.print_exc()
        return Response(status=500)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)