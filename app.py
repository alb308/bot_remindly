import os
import json
import re
from datetime import datetime, date
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from db_sqlite import SQLiteClient
import bot_tools # Importa la nostra nuova cassetta degli attrezzi

load_dotenv()
app = Flask(__name__)

# --- Inizializzazione Servizi ---
db = SQLiteClient
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Definizione degli "Strumenti" per l'AI ---
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

        # Carica la cronologia in modo robusto
        conversation = db.conversations.find_one({"user_id": from_number, "business_id": business_id})
        messages = []
        if conversation and 'messages' in conversation:
            if isinstance(conversation['messages'], str):
                try:
                    messages = json.loads(conversation['messages'])
                except json.JSONDecodeError:
                    messages = []
            elif isinstance(conversation['messages'], list):
                messages = conversation['messages']

        # --- NUOVO "REGOLAMENTO INTERNO" PER L'AI ---
        system_prompt = f"""
        Sei un assistente AI professionale per '{business.get('business_name')}', un'attività di tipo '{business.get('business_type')}'.
        Il tuo unico scopo è aiutare gli utenti a gestire le prenotazioni e a ricevere informazioni relative a questo business.
        
        REGOLE FONDAMENTALI E OBBLIGATORIE:
        1.  Focalizzati al 100% sui tuoi compiti: prenotare, modificare, cancellare appuntamenti e fornire informazioni (orari, servizi, indirizzo).
        2.  NON DEVI rispondere a domande non pertinenti (off-topic). Questo include meteo, matematica, cultura generale, politica, sport, ecc.
        3.  NON DEVI fare conversazione generica o chiacchiere. NON usare solo emoji per rispondere.
        4.  Se un utente fa una domanda non pertinente, DEVI rispondere con una frase gentile ma ferma per riportare la conversazione in argomento.
            - Esempio di risposta corretta: "Mi dispiace, non sono programmato per questo. Posso però aiutarti a prenotare o darti informazioni sui nostri servizi."
            - Esempio di risposta corretta: "Il mio ruolo è di assistente per le prenotazioni. Come posso aiutarti riguardo a '{business.get('business_name')}'?"
        5.  Sii sempre cortese, professionale e vai dritto al punto.
        """
        
        # Prepara la lista di messaggi per l'API, inserendo sempre il regolamento all'inizio
        api_messages = [{"role": "system", "content": system_prompt}]
        # Aggiungi solo gli ultimi 10 messaggi per mantenere il contesto senza appesantire
        api_messages.extend(messages[-10:])
        api_messages.append({"role": "user", "content": incoming_msg})

        # --- PRIMA CHIAMATA ALL'AI ---
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=api_messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message
        
        # Aggiungi alla cronologia sia il messaggio dell'utente che la risposta dell'AI
        messages.append({"role": "user", "content": incoming_msg})
        messages.append(response_message.model_dump())

        if response_message.tool_calls:
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if 'business_id' not in function_args: function_args['business_id'] = business_id
                if 'user_id' not in function_args: function_args['user_id'] = from_number
                if 'user_name' not in function_args: function_args['user_name'] = user_name

                print(f"🧠 AI ha scelto di chiamare la funzione: {function_name} con argomenti: {function_args}")
                function_to_call = getattr(bot_tools, function_name)
                function_response = function_to_call(**function_args)
                
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
            
            # Prepara una nuova lista di messaggi per la seconda chiamata
            api_messages_for_second_call = [{"role": "system", "content": system_prompt}]
            api_messages_for_second_call.extend(messages[-11:]) # Includi anche il risultato del tool

            # --- SECONDA CHIAMATA ALL'AI ---
            second_response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=api_messages_for_second_call,
            )
            response_text = second_response.choices[0].message.content
            # Aggiorna l'ultimo messaggio dell'assistente con la risposta finale
            messages[-1] = second_response.choices[0].message.model_dump()
        else:
            response_text = response_message.content

        # Salva la conversazione e invia la risposta
        db.conversations.update_one(
            {"user_id": from_number, "business_id": business_id},
            {"$set": {"messages": messages, "last_interaction": datetime.now().isoformat()}},
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