import os
import json
import re
from datetime import datetime, timedelta
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

# --- Inizializzazione Servizi ---
# Assicurati che le variabili d'ambiente critiche siano impostate
if not os.getenv("MONGO_URI") or not os.getenv("OPENAI_API_KEY"):
    raise Exception("ERRORE CRITICO: Assicurati che MONGO_URI e OPENAI_API_KEY siano impostate.")

db = SQLiteClient
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
booking_manager = BookingManager(db)
memory_service = MemoryService(db, os.getenv("OPENAI_API_KEY"))

# Cache per i servizi calendar per evitare di ricrearli a ogni richiesta
calendar_services = {}

def get_calendar_service(business_id):
    """
    Ottiene o crea un'istanza del CalendarService per un business specifico.
    Usa una cache per non reinizializzare il servizio a ogni messaggio.
    """
    if business_id not in calendar_services:
        business = db.businesses.find_one({"_id": business_id})
        if business and business.get("google_calendar_id") and os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY"):
            calendar_id = business["google_calendar_id"]
            service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
            calendar_services[business_id] = CalendarService(
                calendar_id=calendar_id,
                service_account_key=service_account_key
            )
    return calendar_services.get(business_id)

def get_ai_response(user_message, business_context, conversation_context=""):
    """
    Genera una risposta intelligente usando OpenAI, basandosi sul contesto
    del business e della conversazione.
    """
    system_prompt = f"""
    Sei l'assistente virtuale di {business_context.get('business_name', 'questo business')}.
    Informazioni sul business:
    - Tipo: {business_context.get('business_type', 'N/A')}
    - Indirizzo: {business_context.get('address', 'N/A')}
    - Orari: {business_context.get('opening_hours', 'N/A')}
    - Servizi: {business_context.get('services', 'N/A')}
    - Descrizione: {business_context.get('description', 'N/A')}
    {conversation_context}
    Rispondi in modo professionale ma amichevole. Mantieni le risposte concise e utili.
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
        return "Mi dispiace, si è verificato un problema tecnico. Riprova tra poco."

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Endpoint principale che riceve i messaggi da Twilio e gestisce la logica.
    """
    try:
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        user_name = request.values.get('ProfileName', 'Cliente')

        print(f"--- Messaggio ricevuto da {from_number}: '{incoming_msg}' ---")

        business = db.businesses.find_one({"twilio_phone_number": to_number})
        if not business:
            print(f"--- ERRORE! Business non trovato per {to_number} ---")
            return Response(status=200)

        business_id = business['_id']
        user_id = from_number
        
        conversation = db.conversations.find_one({"user_id": user_id, "business_id": business_id})
        messages = []
        if conversation and 'messages' in conversation:
            try:
                messages = json.loads(conversation['messages']) if isinstance(conversation['messages'], str) else conversation['messages']
            except (json.JSONDecodeError, TypeError):
                messages = []
        
        last_bot_message = messages[-1]['content'] if (messages and messages[-1]['role'] == 'assistant') else ""
        
        booking_intent = booking_manager.extract_booking_intent(incoming_msg)
        is_booking_confirmation = "orari disponibili" in last_bot_message.lower() and re.search(r'\d{1,2}[:.]?\d{0,2}', incoming_msg)
        is_booking_request = booking_intent.get("intent") == "book" or booking_intent.get("date") is not None

        response_text = ""

        if is_booking_confirmation:
            print("--- Rilevata conferma di prenotazione ---")
            match = re.search(r'(\d{1,2})[:.]?(\d{0,2})', incoming_msg)
            if match:
                hour, minute = match.group(1), match.group(2) or "00"
                selected_time = f"{hour.zfill(2)}:{minute.zfill(2)}"
                print(f"Orario selezionato: {selected_time}")
                calendar_service = get_calendar_service(business_id)
                if calendar_service:
                    booking_date_str = last_bot_message.split("disponibili ")[-1].split(":")[0].strip()
                    if "oggi" in booking_date_str:
                        booking_date = datetime.now().strftime('%Y-%m-%d')
                    else:
                        try:
                            # Tenta di parsare la data dal messaggio del bot. Es. "per il 12/08"
                            parsed_date_obj = datetime.strptime(booking_date_str.replace("per il ", ""), "%d/%m")
                            booking_date = parsed_date_obj.replace(year=datetime.now().year).strftime('%Y-%m-%d')
                        except ValueError:
                            booking_date = datetime.now().strftime('%Y-%m-%d')
                    
                    event_id = calendar_service.create_appointment(date=booking_date, start_time=selected_time, duration_minutes=60, customer_name=user_name, customer_phone=from_number, service_type="Appuntamento")
                    
                    if event_id:
                        response_text = f"Perfetto! Il tuo appuntamento è confermato per le {selected_time}. A presto!"
                        # --- CODICE AGGIUNTO PER SALVARE LA PRENOTAZIONE ---
                        booking_record = {
                            "user_id": user_id, "business_id": business_id,
                            "booking_data": json.dumps({
                                "date": booking_date, "time": selected_time, "duration": 60,
                                "customer_name": user_name, "customer_phone": from_number,
                                "service_type": "Appuntamento"
                            }),
                            "status": "confirmed", "calendar_event_id": event_id,
                            "created_at": datetime.now().isoformat(), "confirmed_at": datetime.now().isoformat()
                        }
                        db.bookings.insert_one(booking_record)
                        print(f"✅ Prenotazione salvata nel DB con event_id: {event_id}")
                        # --- FINE CODICE AGGIUNTO ---
                    else:
                        response_text = "Mi dispiace, si è verificato un errore nel fissare l'appuntamento."
                else:
                    response_text = "Il servizio di calendario non è configurato."
            else:
                response_text = "Non ho capito l'orario."

        # --- NUOVO BLOCCO PER LA MODIFICA ---
        elif booking_intent.get("intent") == "modify":
            print("--- Rilevato intento di modifica ---")
            last_booking = db.bookings.find_one({"user_id": user_id, "business_id": business_id, "status": "confirmed"}, sort=[("confirmed_at", -1)])
            
            if not last_booking:
                response_text = "Non ho trovato una tua prenotazione recente da modificare. Vuoi crearne una nuova?"
            else:
                match = re.search(r'(\d{1,2})[:.]?(\d{0,2})', incoming_msg)
                if match:
                    hour, minute = match.group(1), match.group(2) or "00"
                    new_time = f"{hour.zfill(2)}:{minute.zfill(2)}"
                    print(f"Nuovo orario richiesto: {new_time}")

                    calendar_service = get_calendar_service(business_id)
                    booking_data = json.loads(last_booking['booking_data'])
                    event_id = last_booking['calendar_event_id']

                    updated_event_id = calendar_service.update_appointment(
                        event_id=event_id,
                        new_date=booking_data['date'],
                        new_start_time=new_time,
                        duration_minutes=booking_data.get('duration', 60)
                    )

                    if updated_event_id:
                        response_text = f"Fatto! Ho spostato il tuo appuntamento alle {new_time}."
                        booking_data['time'] = new_time
                        db.bookings.update_one(
                            {"_id": last_booking["_id"]},
                            {"$set": {"booking_data": json.dumps(booking_data)}}
                        )
                    else:
                        response_text = f"Mi dispiace, non è stato possibile spostare l'appuntamento alle {new_time}. Potrebbe essere un orario non disponibile."
                else:
                    response_text = "Non ho capito a che ora vorresti spostare l'appuntamento."
        # --- FINE BLOCCO MODIFICA ---

        elif is_booking_request and business.get("booking_enabled"):
            print("--- Rilevato intento di prenotazione ---")
            calendar_service = get_calendar_service(business_id)
            if calendar_service:
                parsed_date = booking_manager.parse_datetime(booking_intent.get('date'))
                target_date_str = parsed_date.strftime('%Y-%m-%d') if parsed_date else datetime.now().strftime('%Y-%m-%d')
                
                bh = business.get("booking_hours", "9-18-60").split("-")
                start_h, end_h, dur = int(bh[0]), int(bh[1]), int(bh[2])
                slots = calendar_service.get_available_slots(target_date_str, duration_minutes=dur, start_hour=start_h, end_hour=end_h)
                
                if slots:
                    date_display = "oggi" if target_date_str == datetime.now().strftime('%Y-%m-%d') else f"per il {datetime.strptime(target_date_str, '%Y-%m-%d').strftime('%d/%m')}"
                    
                    # --- MODIFICA: Rimossa la limitazione [slots[:5]] ---
                    response_text = f"Certamente! Ecco gli orari disponibili {date_display}:\n" + "\n".join([f"• {s['start']}" for s in slots])
                    response_text += "\n\nQuale preferisci?"
                else:
                    response_text = "Mi dispiace, non ci sono slot disponibili per la data richiesta."
            else:
                response_text = "Il servizio di prenotazione non è al momento disponibile."
        
        else:
            print("--- Nessun intento specifico rilevato, uso l'AI generica ---")
            context = memory_service.build_context(user_id, business_id, messages)
            memory_service.upsert_customer_profile(user_id, business_id, messages, incoming_msg)
            response_text = get_ai_response(incoming_msg, business, context)
        
        messages.append({"role": "user", "content": incoming_msg, "timestamp": datetime.now().isoformat()})
        messages.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})
        db.conversations.update_one({"user_id": user_id, "business_id": business_id}, {"$set": {"messages": json.dumps(messages), "last_interaction": datetime.now().isoformat()}}, upsert=True)


        print(f"--- Risposta inviata: '{response_text[:70]}...' ---")
        resp = MessagingResponse()
        resp.message(response_text)
        return Response(str(resp), mimetype='text/xml')
        
    except Exception as e:
        print(f"--- ERRORE CRITICO E IMPREVISTO NEL WEBHOOK: {e} ---")
        import traceback
        traceback.print_exc()
        resp = MessagingResponse()
        resp.message("Mi scuso, si è verificato un errore interno. Il team è stato notificato.")
        return Response(str(resp), mimetype='text/xml')

@app.route('/health', methods=['GET'])
def health():
    """Endpoint per verificare che il servizio sia attivo."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Server avviato in modalità di sviluppo locale su http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)