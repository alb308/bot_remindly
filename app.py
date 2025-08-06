import os
import json
import re
from datetime import datetime, timedelta
from flask import Flask, request
from openai import OpenAI
from twilio.twiml.messaging_response import MessagingResponse
from pymongo import MongoClient
import hashlib

# Import dei nuovi moduli
from calendar_service import CalendarService
from booking_manager import (
    BookingManager, 
    format_available_slots, 
    format_booking_confirmation, 
    format_booking_success
)

# --- CONFIGURAZIONE E CONNESSIONE AL DATABASE ---

app = Flask(__name__)

# Carica le chiavi API e la stringa di connessione al DB dalle variabili d'ambiente di Railway
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI")
GOOGLE_SERVICE_ACCOUNT_KEY = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")  # JSON del service account

if not OPENAI_API_KEY or not MONGO_URI:
    raise Exception("ERRORE: Assicurati di aver impostato le variabili OPENAI_API_KEY e MONGO_URI su Railway.")

# Inizializza i client
openai_client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database()
businesses_collection = db.businesses
conversations_collection = db.conversations

# Inizializza gestore prenotazioni
booking_manager = BookingManager(db)

print("Connessione a MongoDB stabilita.")

# --- FUNZIONI DI UTILITÀ ---

def get_user_id(from_number):
    """Crea un ID univoco per l'utente basato sul numero di telefono"""
    return hashlib.sha256(from_number.encode()).hexdigest()[:16]

def get_conversation_history(user_id, business_id, limit=10):
    """Recupera la cronologia della conversazione limitata agli ultimi N messaggi"""
    try:
        conversation = conversations_collection.find_one({
            "user_id": user_id,
            "business_id": business_id
        })
        
        if not conversation:
            return []
        
        messages = conversation.get("messages", [])[-limit:]
        cutoff_date = datetime.now() - timedelta(days=7)
        recent_messages = [
            msg for msg in messages 
            if datetime.fromisoformat(msg["timestamp"]) > cutoff_date
        ]
        
        return recent_messages
    except Exception as e:
        print(f"ERRORE nel recuperare cronologia: {e}")
        return []

def save_message(user_id, business_id, role, content):
    """Salva un messaggio nella cronologia della conversazione"""
    try:
        message_data = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        conversations_collection.update_one(
            {
                "user_id": user_id,
                "business_id": business_id
            },
            {
                "$push": {
                    "messages": {
                        "$each": [message_data],
                        "$slice": -50
                    }
                },
                "$set": {
                    "last_interaction": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                },
                "$setOnInsert": {
                    "created_at": datetime.now().isoformat()
                }
            },
            upsert=True
        )
    except Exception as e:
        print(f"ERRORE nel salvare messaggio: {e}")

def get_calendar_service(business_profile):
    """Inizializza il servizio calendar per il business"""
    if not GOOGLE_SERVICE_ACCOUNT_KEY:
        return None
    
    calendar_id = business_profile.get('google_calendar_id')
    if not calendar_id:
        return None
    
    return CalendarService(calendar_id, GOOGLE_SERVICE_ACCOUNT_KEY)

def extract_customer_info(conversation_history, current_message):
    """Estrae informazioni del cliente dalla conversazione"""
    # Cerca il nome nelle conversazioni precedenti o nel messaggio corrente
    name_patterns = [
        r'mi chiamo (\w+)',
        r'sono (\w+)',
        r'il mio nome è (\w+)',
    ]
    
    all_messages = [msg['content'] for msg in conversation_history] + [current_message]
    
    customer_name = None
    for message in all_messages:
        for pattern in name_patterns:
            match = re.search(pattern, message.lower())
            if match:
                customer_name = match.group(1).title()
                break
        if customer_name:
            break
    
    return customer_name or "Cliente"

def handle_booking_flow(user_id, business_id, business_profile, conversation_history, message, from_number):
    """Gestisce il flusso delle prenotazioni"""
    calendar_service = get_calendar_service(business_profile)
    if not calendar_service:
        return "Mi dispiace, il sistema di prenotazioni non è attualmente disponibile."
    
    # Analizza intent del messaggio
    booking_intent = booking_manager.extract_booking_intent(message)
    
    # Controlla se c'è una prenotazione pendente
    pending_booking = db.pending_bookings.find_one({
        'user_id': user_id,
        'business_id': business_id,
        'status': 'pending_confirmation'
    })
    
    # Gestisci conferma di prenotazione pendente
    if pending_booking:
        message_lower = message.lower().strip()
        if any(word in message_lower for word in ['sì', 'si', 'yes', 'conferma', 'va bene', 'ok']):
            success, result = booking_manager.confirm_booking(
                str(pending_booking['_id']), 
                calendar_service
            )
            if success:
                return format_booking_success(pending_booking['booking_data'])
            else:
                return f"Mi dispiace, si è verificato un problema: {result}"
        
        elif any(word in message_lower for word in ['no', 'annulla', 'cancella', 'non va bene']):
            # Cancella prenotazione pendente
            db.pending_bookings.delete_one({'_id': pending_booking['_id']})
            return "Prenotazione annullata. Posso aiutarti con altro?"
        
        # Se il messaggio contiene un numero (selezione slot)
        elif message_lower.isdigit():
            slot_number = int(message_lower)
            # Qui gestiremo la selezione dello slot (implementato sotto)
            pass
    
    # Gestisci nuova richiesta di prenotazione
    if booking_intent['intent'] == 'book' and booking_intent['confidence'] > 0.5:
        # Estrai e normalizza data e ora
        normalized_date = booking_manager.normalize_date(booking_intent['date'])
        normalized_time = booking_manager.normalize_time(booking_intent['time'])
        
        # Se manca la data, chiedi di specificarla
        if not normalized_date:
            return """
📅 *Prenotazione*

Per quale giorno vorresti prenotare?
Puoi dirmi:
• Una data specifica (es: 15/03/2024)
• Un giorno relativo (es: domani, dopodomani)
• Un giorno della settimana (es: lunedì, martedì)
            """.strip()
        
        # Mostra slot disponibili
        business_hours = business_profile.get('booking_hours', {})
        start_hour = business_hours.get('start', 9)
        end_hour = business_hours.get('end', 18)
        duration = business_hours.get('default_duration', 60)
        
        available_slots = calendar_service.get_available_slots(
            normalized_date, 
            duration_minutes=duration,
            start_hour=start_hour,
            end_hour=end_hour
        )
        
        if not available_slots:
            return f"Mi dispiace, non ci sono slot disponibili per {normalized_date}. Prova con un'altra data."
        
        # Se è specificato anche l'orario, controlla se è disponibile
        if normalized_time:
            requested_slot = None
            for slot in available_slots:
                if slot['start'] == normalized_time:
                    requested_slot = slot
                    break
            
            if requested_slot:
                # Crea prenotazione pendente
                customer_name = extract_customer_info(conversation_history, message)
                booking_data = {
                    'date': normalized_date,
                    'time': normalized_time,
                    'duration': duration,
                    'service_type': booking_intent['service_type'],
                    'customer_name': customer_name,
                    'customer_phone': from_number,
                    'notes': f"Prenotazione via WhatsApp"
                }
                
                pending_id = booking_manager.create_pending_booking(
                    user_id, business_id, booking_data
                )
                
                return format_booking_confirmation(booking_data)
            else:
                return f"L'orario {normalized_time} non è disponibile per {normalized_date}. " + \
                       format_available_slots(available_slots, normalized_date)
        
        else:
            # Mostra slot disponibili per selezione
            return format_available_slots(available_slots, normalized_date)
    
    # Gestisci selezione slot numerica
    if message.strip().isdigit():
        slot_number = int(message.strip())
        
        # Cerca l'ultima richiesta di slot nella conversazione
        for msg in reversed(conversation_history):
            if "Orari disponibili" in msg.get('content', ''):
                # Rigenera gli slot per quella data
                # (In produzione, salveresti gli slot in una sessione temporanea)
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', msg['content'])
                if date_match:
                    date = date_match.group(1)
                    business_hours = business_profile.get('booking_hours', {})
                    available_slots = calendar_service.get_available_slots(
                        date,
                        duration_minutes=business_hours.get('default_duration', 60),
                        start_hour=business_hours.get('start', 9),
                        end_hour=business_hours.get('end', 18)
                    )
                    
                    if 1 <= slot_number <= len(available_slots):
                        selected_slot = available_slots[slot_number - 1]
                        
                        customer_name = extract_customer_info(conversation_history, message)
                        booking_data = {
                            'date': date,
                            'time': selected_slot['start'],
                            'duration': business_hours.get('default_duration', 60),
                            'service_type': 'Appuntamento',
                            'customer_name': customer_name,
                            'customer_phone': from_number,
                            'notes': f"Prenotazione via WhatsApp - Slot {slot_number}"
                        }
                        
                        pending_id = booking_manager.create_pending_booking(
                            user_id, business_id, booking_data
                        )
                        
                        return format_booking_confirmation(booking_data)
                break
    
    # Gestisci richieste di cancellazione
    if booking_intent['intent'] == 'cancel':
        user_bookings = booking_manager.get_user_bookings(user_id, business_id)
        if not user_bookings:
            return "Non ho trovato prenotazioni attive a tuo nome."
        
        upcoming_bookings = [
            b for b in user_bookings 
            if datetime.strptime(b['booking_data']['date'], '%Y-%m-%d').date() >= datetime.now().date()
        ]
        
        if not upcoming_bookings:
            return "Non hai prenotazioni future da cancellare."
        
        # Mostra prenotazioni cancellabili
        message = "🗑️ *Le tue prenotazioni:*\n\n"
        for i, booking in enumerate(upcoming_bookings[:5], 1):
            data = booking['booking_data']
            message += f"{i}. {data['date']} alle {data['time']} - {data['service_type']}\n"
        
        message += "\n💬 Rispondi con 'CANCELLA X' dove X è il numero della prenotazione da cancellare."
        return message
    
    # Gestisci comando di cancellazione specifico
    cancel_match = re.search(r'cancella\s+(\d+)', message.lower())
    if cancel_match:
        booking_number = int(cancel_match.group(1))
        user_bookings = booking_manager.get_user_bookings(user_id, business_id)
        upcoming_bookings = [
            b for b in user_bookings 
            if datetime.strptime(b['booking_data']['date'], '%Y-%m-%d').date() >= datetime.now().date()
        ]
        
        if 1 <= booking_number <= len(upcoming_bookings):
            booking_to_cancel = upcoming_bookings[booking_number - 1]
            success, result = booking_manager.cancel_booking(
                str(booking_to_cancel['_id']), 
                calendar_service
            )
            
            if success:
                data = booking_to_cancel['booking_data']
                return f"✅ Prenotazione del {data['date']} alle {data['time']} cancellata con successo."
            else:
                return f"Mi dispiace, si è verificato un problema: {result}"
        else:
            return "Numero prenotazione non valido."
    
    return None  # Nessun intent di prenotazione rilevato

def build_conversation_messages(business_info, conversation_history, current_message):
    """Costruisce l'array di messaggi per l'API di OpenAI con supporto prenotazioni"""
    
    # Informazioni sulle prenotazioni per il prompt
    booking_info = ""
    if business_info.get('google_calendar_id'):
        booking_hours = business_info.get('booking_hours', {})
        booking_info = f"""
SISTEMA PRENOTAZIONI ATTIVO:
- Orari: {booking_hours.get('start', 9)}:00 - {booking_hours.get('end', 18)}:00
- Durata standard: {booking_hours.get('default_duration', 60)} minuti
- Per prenotare: i clienti possono chiedere disponibilità per una data specifica
- Servizi disponibili: {', '.join(business_info.get('services', ['Appuntamento generico']))}
        """
    
    system_prompt = f"""
Sei un assistente virtuale professionale per {business_info.get('business_name', 'questa attività')}.

INFORMAZIONI SULL'ATTIVITÀ:
{json.dumps({k: v for k, v in business_info.items() if k not in ['_id', 'google_calendar_id']}, indent=2, ensure_ascii=False)}

{booking_info}

ISTRUZIONI COMPORTAMENTALI:
- Mantieni un tono professionale ma cordiale
- Ricorda le informazioni dalla conversazione precedente quando rilevanti
- Se non conosci una informazione specifica, indirizza il cliente a contattare direttamente l'attività
- Non inventare mai informazioni non presenti nei dati forniti
- Rispondi sempre in italiano
- Non usare emoji eccetto quando strettamente necessario per chiarezza
- Mantieni le risposte concise ma complete

GESTIONE PRENOTAZIONI:
- Se il cliente chiede di prenotare, il sistema gestirà automaticamente il processo
- Tu fornisci solo informazioni generali sui servizi e orari
- Non cercare di gestire tu le prenotazioni, lascia che sia il sistema a farlo
- Puoi incoraggiare i clienti a specificare la data e il tipo di servizio desiderato

PRIVACY: Non riferire mai esplicitamente ai messaggi precedenti, usa le informazioni in modo naturale.
    """
    
    messages = [{"role": "system", "content": system_prompt}]
    
    # Aggiungi cronologia recente
    for msg in conversation_history[-6:]:
        if msg["role"] in ["user", "assistant"]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    # Aggiungi messaggio corrente
    messages.append({"role": "user", "content": current_message})
    
    return messages

def get_smart_response(business_info, conversation_history, current_message):
    """Genera una risposta intelligente usando OpenAI con contesto"""
    try:
        messages = build_conversation_messages(business_info, conversation_history, current_message)
        
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=300,
            presence_penalty=0.1,
            frequency_penalty=0.1
        )
        
        return completion.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"ERRORE API OpenAI: {e}")
        return "Mi scuso, si è verificato un problema tecnico. La preghiamo di riprovare più tardi."

# --- WEBHOOK PER WHATSAPP (TWILIO) ---

@app.route("/whatsapp-webhook", methods=["POST"])
def whatsapp_reply():
    """Webhook multi-tenant intelligente con sistema di prenotazioni"""
    twiml_response = MessagingResponse()

    # 1. Estrai informazioni dalla richiesta
    incoming_msg = request.values.get("Body", "").strip()
    recipient_number = request.values.get("To", "").strip()
    from_number = request.values.get("From", "").strip()

    if not incoming_msg or not recipient_number or not from_number:
        return str(twiml_response)

    # 2. Cerca il profilo del business nel database
    try:
        business_profile = businesses_collection.find_one({"twilio_phone_number": recipient_number})
    except Exception as e:
        print(f"ERRORE DB: Impossibile interrogare il database: {e}")
        twiml_response.message("Si è verificato un errore interno. Riprova più tardi.")
        return str(twiml_response)

    if not business_profile:
        print(f"ATTENZIONE: Nessun business trovato per il numero Twilio {recipient_number}")
        twiml_response.message("Questo numero WhatsApp non è attualmente configurato per un servizio di assistenza.")
        return str(twiml_response)

    # 3. Prepara dati per l'elaborazione
    business_id = str(business_profile["_id"])
    user_id = get_user_id(from_number)
    business_info = {k: v for k, v in business_profile.items() if k != "_id"}
    
    # 4. Recupera cronologia conversazione
    conversation_history = get_conversation_history(user_id, business_id)
    
    # 5. Prima controlla se è una richiesta di prenotazione
    booking_response = handle_booking_flow(
        user_id, business_id, business_profile, 
        conversation_history, incoming_msg, from_number
    )
    
    if booking_response:
        ai_response = booking_response
    else:
        # 6. Genera risposta intelligente normale
        ai_response = get_smart_response(business_info, conversation_history, incoming_msg)
    
    # 7. Salva messaggi nella cronologia
    save_message(user_id, business_id, "user", incoming_msg)
    save_message(user_id, business_id, "assistant", ai_response)
    
    # 8. Invia risposta
    twiml_response.message(ai_response)
    
    print(f"Conversazione elaborata per business: {business_info.get('business_name', 'N/A')}")
    
    return str(twiml_response)

# --- ENDPOINT PER GESTIONE DATI ---

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint per verificare lo stato del servizio"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.route("/stats/<business_id>", methods=["GET"])
def get_conversation_stats(business_id):
    """Endpoint per statistiche conversazioni"""
    try:
        total_conversations = conversations_collection.count_documents({"business_id": business_id})
        recent_conversations = conversations_collection.count_documents({
            "business_id": business_id,
            "last_interaction": {"$gte": (datetime.now() - timedelta(days=7)).isoformat()}
        })
        
        total_bookings = db.bookings.count_documents({"business_id": business_id})
        pending_bookings = db.pending_bookings.count_documents({"business_id": business_id})
        
        return {
            "business_id": business_id,
            "total_conversations": total_conversations,
            "recent_conversations_7d": recent_conversations,
            "total_bookings": total_bookings,
            "pending_bookings": pending_bookings
        }
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/bookings/<business_id>", methods=["GET"])
def get_business_bookings(business_id):
    """Endpoint per vedere prenotazioni del business"""
    try:
        bookings = list(db.bookings.find({
            "business_id": business_id,
            "status": "confirmed"
        }).sort("booking_data.date", 1))
        
        # Converti ObjectId in stringa
        for booking in bookings:
            booking["_id"] = str(booking["_id"])
        
        return {"bookings": bookings}
    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)