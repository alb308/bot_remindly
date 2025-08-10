import os
import json
from datetime import datetime
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
from dotenv import load_dotenv
from db_sqlite import SQLiteClient
from booking_manager import BookingManager
from calendar_service import CalendarService
from memory import MemoryService

# Carica variabili d'ambiente
load_dotenv()

app = Flask(__name__)

# Inizializzazione servizi
db = SQLiteClient("remindly.db")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
booking_manager = BookingManager(db)
memory_service = MemoryService(db, os.getenv("OPENAI_API_KEY"))

# Cache per i servizi calendar
calendar_services = {}

def get_calendar_service(business_id):
    """Ottiene o crea un servizio calendar per un business specifico"""
    if business_id not in calendar_services:
        business = db.businesses.find_one({"id": business_id})
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
        print(f"Errore OpenAI: {e}")
        return "Mi dispiace, c'è stato un problema. Riprova tra poco."

@app.route('/webhook', methods=['POST'])
def webhook():
    """Endpoint principale per ricevere messaggi WhatsApp"""
    try:
        # Estrai dati dal messaggio
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', '')
        
        print(f"📱 Messaggio ricevuto da {from_number}: {incoming_msg}")
        
        # Trova il business associato al numero
        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business:
            print(f"⚠️ Business non trovato per {to_number}")
            resp = MessagingResponse()
            resp.message("Mi dispiace, questo numero non è configurato.")
            return Response(str(resp), mimetype='text/xml')
        
        business_id = business['id']
        user_id = from_number
        
        # Recupera o crea conversazione
        conversation = db.conversations.find_one({
            "user_id": user_id,
            "business_id": business_id
        })
        
        if not conversation:
            # Nuova conversazione
            conversation_data = {
                "user_id": user_id,
                "business_id": business_id,
                "messages": json.dumps([]),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "last_interaction": datetime.now().isoformat()
            }
            result = db.conversations.insert_one(conversation_data)
            conversation = db.conversations.find_one({"id": result["inserted_id"]})
        
        # Carica storico messaggi
        messages = json.loads(conversation.get("messages", "[]"))
        
        # Aggiungi messaggio utente
        messages.append({
            "role": "user",
            "content": incoming_msg,
            "timestamp": datetime.now().isoformat()
        })
        
        # Gestione prenotazioni se abilitato
        response_text = ""
        if business.get("booking_enabled") and business.get("google_calendar_id"):
            # Analizza intento di prenotazione
            booking_intent = booking_manager.extract_booking_intent(incoming_msg)
            
            if booking_intent.get("intent") == "book":
                # Gestisci richiesta di prenotazione
                calendar_service = get_calendar_service(business_id)
                if calendar_service:
                    # Esempio: mostra slot disponibili per oggi
                    today = datetime.now().strftime("%Y-%m-%d")
                    slots = calendar_service.get_available_slots(today)
                    
                    if slots:
                        response_text = f"Ecco gli orari disponibili per oggi:\n"
                        for slot in slots[:5]:  # Mostra max 5 slot
                            response_text += f"• {slot['start']} - {slot['end']}\n"
                        response_text += "\nQuale preferisci?"
                    else:
                        response_text = "Mi dispiace, non ci sono slot disponibili per oggi."
            
            elif booking_intent.get("intent") == "cancel":
                # Gestisci cancellazione
                response_text = "Per cancellare un appuntamento, indicami data e ora."
        
        # Se non c'è una risposta specifica per prenotazioni, usa AI
        if not response_text:
            # Costruisci contesto memoria
            context = memory_service.build_context(user_id, business_id, messages)
            
            # Estrai e salva info cliente
            memory_service.upsert_customer_profile(user_id, business_id, messages, incoming_msg)
            
            # Genera risposta AI
            response_text = get_ai_response(incoming_msg, business, context)
            
            # Riassumi se necessario
            memory_service.summarize_if_needed(user_id, business_id)
        
        # Aggiungi risposta all'storico
        messages.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now().isoformat()
        })
        
        # Aggiorna conversazione nel database
        db.conversations.update_one(
            {"id": conversation["id"]},
            {
                "messages": json.dumps(messages),
                "last_interaction": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        )
        
        # Invia risposta via Twilio
        resp = MessagingResponse()
        resp.message(response_text)
        
        print(f"✅ Risposta inviata: {response_text[:100]}...")
        return Response(str(resp), mimetype='text/xml')
        
    except Exception as e:
        print(f"❌ Errore nel webhook: {e}")
        import traceback
        traceback.print_exc()
        
        resp = MessagingResponse()
        resp.message("Si è verificato un errore. Riprova più tardi.")
        return Response(str(resp), mimetype='text/xml')

@app.route('/health', methods=['GET'])
def health():
    """Endpoint per verificare lo stato del servizio"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200

@app.route('/stats', methods=['GET'])
def stats():
    """Endpoint per statistiche"""
    try:
        total_businesses = db.businesses.count_documents()
        total_conversations = db.conversations.count_documents()
        total_customers = db.customers.count_documents()
        total_bookings = db.bookings.count_documents()
        
        return {
            "businesses": total_businesses,
            "conversations": total_conversations,
            "customers": total_customers,
            "bookings": total_bookings,
            "timestamp": datetime.now().isoformat()
        }, 200
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Server avviato su porta {port}")
    print(f"📱 Webhook disponibile su: http://localhost:{port}/webhook")
    app.run(host='0.0.0.0', port=port, debug=True)