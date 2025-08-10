import os
import json
from datetime import datetime
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from db_sqlite import SQLiteClient # Ora questo importa il wrapper per MongoDB
from booking_manager import BookingManager
from calendar_service import CalendarService
from memory import MemoryService

# Carica variabili d'ambiente
load_dotenv()

app = Flask(__name__)

# Inizializzazione servizi
# Assicurati che MONGO_URI sia impostato prima di inizializzare il DB
if not os.getenv("MONGO_URI"):
    raise Exception("ERRORE CRITICO: La variabile d'ambiente MONGO_URI non è impostata.")

db = SQLiteClient # Il nome è mantenuto per compatibilità, ma ora è il client Mongo
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
booking_manager = BookingManager(db)
memory_service = MemoryService(db, os.getenv("OPENAI_API_KEY"))

# Cache per i servizi calendar
calendar_services = {}

def get_calendar_service(business_id):
    """Ottiene o crea un servizio calendar per un business specifico"""
    if business_id not in calendar_services:
        business = db.businesses.find_one({"_id": business_id})
        if business and business.get("google_calendar_id"):
            calendar_id = business["google_calendar_id"]
            service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
            if service_account_key:
                calendar_services[business_id] = CalendarService(
                    calendar_id=calendar_id,
                    service_account_key=service_account_key
                )
    return calendar_services.get(business_id)

def get_ai_response(user_message, business_context, conversation_context=""):
    """Genera risposta AI basata sul contesto del business"""
    system_prompt = f"""
    Sei l'assistente virtuale di {business_context.get('business_name', 'questo business')}.
    
    Informazioni sul business:
    - Tipo: {business_context.get('business_type', 'N/A')}
    - Indirizzo: {business_context.get('address', 'N/A')}
    - Telefono: {business_context.get('phone', 'N/A')}
    - Email: {business_context.get('email', 'N/A')}
    - Orari: {business_context.get('opening_hours', 'N/A')}
    - Servizi: {business_context.get('services', 'N/A')}
    - Descrizione: {business_context.get('description', 'N/A')}
    
    {conversation_context}
    
    Rispondi in modo professionale ma amichevole. Se l'utente chiede di prenotare, 
    fornisci le informazioni necessarie e conferma la disponibilità.
    Mantieni le risposte concise e utili.
    """
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"--- ERRORE DURANTE CHIAMATA OPENAI: {e} ---")
        return "Mi dispiace, c'è stato un problema nel formulare una risposta. Riprova tra poco."

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # Estrai dati dal messaggio
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        
        # LOG 1: Messaggio ricevuto
        print(f"--- LOG 1: Messaggio ricevuto da {from_number} a {to_number} ---")
        print(f"Testo: {incoming_msg}")

        # Trova il business associato al numero
        business = db.businesses.find_one({"twilio_phone_number": to_number})
        
        if not business:
            # LOG 2: Errore, business non trovato
            print(f"--- LOG 2: ERRORE! Business non trovato per il numero {to_number} ---")
            # È importante restituire una risposta vuota con stato 200 per evitare errori di Twilio
            return Response(status=200)

        # LOG 3: Business trovato
        # In MongoDB, l'ID è un oggetto, quindi lo gestiamo correttamente
        business_id = business['_id'] 
        print(f"--- LOG 3: Business trovato: {business.get('business_name')} (ID: {business_id}) ---")
        user_id = from_number
        
        # Recupera o crea conversazione
        conversation = db.conversations.find_one({
            "user_id": user_id,
            "business_id": business_id
        })
        
        messages = []
        if conversation and 'messages' in conversation:
            # Gestione del caso in cui i messaggi sono stringhe JSON o già liste
            try:
                if isinstance(conversation['messages'], str):
                    messages = json.loads(conversation['messages'])
                else:
                    messages = conversation['messages']
            except (json.JSONDecodeError, TypeError):
                messages = []
        
        messages.append({"role": "user", "content": incoming_msg, "timestamp": datetime.now().isoformat()})
        
        # LOG 4: Pronto a generare la risposta AI
        print("--- LOG 4: Contesto costruito. Chiamo OpenAI per la risposta. ---")
        
        context = memory_service.build_context(user_id, business_id, messages)

        response_text = get_ai_response(incoming_msg, business, context)
        
        # LOG 5: Risposta ricevuta da OpenAI
        print(f"--- LOG 5: Risposta da OpenAI ricevuta: '{response_text[:70]}...' ---")

        messages.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})

        # Aggiorna conversazione nel database usando upsert per creare se non esiste
        db.conversations.update_one(
            {"user_id": user_id, "business_id": business_id},
            {"$set": {
                "messages": json.dumps(messages),
                "last_interaction": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "user_id": user_id,
                "business_id": business_id
            }},
            upsert=True
        )

        # LOG 6: Pronto a inviare la risposta con Twilio
        print("--- LOG 6: Database aggiornato. Invio la risposta via Twilio. ---")

        resp = MessagingResponse()
        resp.message(response_text)
        
        print("--- LOG 7: Risposta inviata con successo! ---")
        return Response(str(resp), mimetype='text/xml')
        
    except Exception as e:
        # LOG 8: Errore critico nel blocco try/except
        print(f"--- LOG 8: ERRORE CRITICO! Eccezione catturata: {e} ---")
        import traceback
        traceback.print_exc()
        return Response(status=500)

@app.route('/health', methods=['GET'])
def health():
    """Endpoint per verificare lo stato del servizio"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Questa parte viene eseguita solo in locale, non su Railway con Gunicorn
    print(f"🚀 Server avviato in locale su porta {port}")
    app.run(host='0.0.0.0', port=port, debug=True)