import json
from datetime import datetime, timedelta
from database import db_connection
from calendar_service import CalendarService
import os

db = db_connection
calendar_services = {}

def get_calendar_service(business_id):
    """Ottiene o crea il servizio calendario per un business"""
    if business_id not in calendar_services:
        business = db.businesses.find_one({"_id": business_id})
        if business and business.get("google_calendar_id") and os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY"):
            calendar_id = business["google_calendar_id"]
            service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
            calendar_services[business_id] = CalendarService(
                calendar_id=calendar_id, 
                service_account_key=service_account_key
            )
        else:
            print(f"⚠️ Configurazione calendario mancante per business {business_id}")
    return calendar_services.get(business_id)

def _get_services(business):
    """Funzione helper robusta per caricare i servizi in modo sicuro."""
    if not business:
        return []
        
    services_data = business.get("services")
    
    # Se è già una lista, restituiscila
    if isinstance(services_data, list):
        return services_data
    
    # Se è una stringa, prova a parsarla
    if isinstance(services_data, str) and services_data.strip():
        try:
            return json.loads(services_data)
        except json.JSONDecodeError as e:
            print(f"⚠️ Errore parsing servizi: {e} - Contenuto: '{services_data[:50]}'")
            return []
    
    # Se è None, stringa vuota, o altro tipo
    print(f"⚠️ Services data non valido: {type(services_data)} - {services_data}")
    return []

def get_available_slots(business_id: str, service_name: str, date: str, **kwargs):
    """Trova gli orari disponibili per un servizio in una data"""
    # Validazione business
    business = db.businesses.find_one({"_id": business_id})
    if not business:
        return "Errore: business non trovato nel database."
    
    services = _get_services(business)
    if not services:
        return "Errore: non ci sono servizi configurati per questo business nel database. Contatta l'amministratore."

    # Validazione servizio
    selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
    if not selected_service:
        service_names = [s['name'] for s in services]
        return f"Servizio '{service_name}' non trovato. I servizi disponibili sono: {', '.join(service_names)}."

    # Validazione data
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return f"Formato data non valido: {date}. Usa il formato YYYY-MM-DD (es: 2024-03-15)."

    # Verifica che la data non sia nel passato
    today = datetime.now().date()
    request_date = datetime.strptime(date, '%Y-%m-%d').date()
    if request_date < today:
        return f"Non puoi prenotare per il {date} perché è nel passato. Scegli una data futura."

    calendar_service = get_calendar_service(business_id)
    if not calendar_service:
        return "Servizio calendario non configurato. Contatta l'amministratore per risolvere il problema."

    # Ottieni orari di lavoro
    booking_hours = business.get("booking_hours", "9-18")
    try:
        start_hour, end_hour = map(int, booking_hours.split("-"))
    except (ValueError, AttributeError):
        start_hour, end_hour = 9, 18

    # Cerca slot disponibili
    try:
        slots = calendar_service.get_available_slots(
            date=date, 
            duration_minutes=selected_service['duration'], 
            start_hour=start_hour, 
            end_hour=end_hour
        )
    except Exception as e:
        print(f"❌ Errore calendar service: {e}")
        return "Errore temporaneo nel controllo disponibilità. Riprova tra poco."
    
    if not slots:
        return f"Nessun orario disponibile per il {date} per il servizio {service_name}. Prova un'altra data."
    
    # Restituisci solo gli orari di inizio
    available_times = [s['start'] for s in slots]
    return json.dumps(available_times)

def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str, **kwargs):
    """Crea o aggiorna un appuntamento"""
    # Validazione business
    business = db.businesses.find_one({"_id": business_id})
    if not business:
        return "Errore: business non trovato nel database."
    
    services = _get_services(business)
    if not services:
        return "Errore: non ci sono servizi configurati per questo business nel database."

    # Validazione servizio
    selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
    if not selected_service:
        service_names = [s['name'] for s in services]
        return f"Servizio '{service_name}' non trovato. I servizi disponibili sono: {', '.join(service_names)}."

    # Validazioni data e ora
    try:
        datetime.strptime(date, '%Y-%m-%d')
        datetime.strptime(time, '%H:%M')
    except ValueError:
        return "Formato data o ora non valido. Usa YYYY-MM-DD per la data e HH:MM per l'ora."

    # Verifica che la data non sia nel passato
    today = datetime.now().date()
    request_date = datetime.strptime(date, '%Y-%m-%d').date()
    if request_date < today:
        return f"Non puoi prenotare per il {date} perché è nel passato."

    calendar_service = get_calendar_service(business_id)
    if not calendar_service:
        return "Servizio calendario non configurato."

    # Cerca prenotazione esistente
    last_booking = db.bookings.find_one(
        {"user_id": user_id, "business_id": business_id, "status": "confirmed"}, 
        sort=[("confirmed_at", -1)]
    )
    
    try:
        if last_booking:
            # Aggiorna appuntamento esistente
            event_id = calendar_service.update_appointment(
                event_id=last_booking['calendar_event_id'],
                new_date=date, 
                new_start_time=time, 
                duration_minutes=selected_service['duration']
            )
            action = "aggiornato"
        else:
            # Crea nuovo appuntamento
            event_id = calendar_service.create_appointment(
                date=date, 
                start_time=time, 
                duration_minutes=selected_service['duration'],
                customer_name=user_name, 
                customer_phone=user_id, 
                service_type=service_name
            )
            action = "creato"

        if not event_id:
            # Se fallisce, verifica se l'orario è ancora disponibile
            slots = calendar_service.get_available_slots(
                date=date, 
                duration_minutes=selected_service['duration']
            )
            available_times = [s['start'] for s in slots] if slots else []
            
            if available_times:
                return f"L'orario {time} non è più disponibile. Gli orari liberi per il {date} sono: {', '.join(available_times[:5])}. Vuoi prenotare uno di questi?"
            else:
                return f"Non ci sono più orari disponibili per il {date}. Prova un'altra data."

        # Salva nel database
        booking_data = {
            "date": date, 
            "time": time, 
            "duration": selected_service['duration'], 
            "service_type": service_name, 
            "customer_name": user_name, 
            "customer_phone": user_id
        }
        
        if last_booking:
            db.bookings.update_one(
                {"_id": last_booking["_id"]}, 
                {"$set": {"booking_data": json.dumps(booking_data)}}
            )
        else:
            db.bookings.insert_one({
                "user_id": user_id, 
                "business_id": business_id, 
                "booking_data": json.dumps(booking_data),
                "status": "confirmed", 
                "calendar_event_id": event_id, 
                "created_at": datetime.now().isoformat(), 
                "confirmed_at": datetime.now().isoformat()
            })
            
        return f"✅ Appuntamento per {service_name} {action} per il {date} alle {time}."
        
    except Exception as e:
        print(f"❌ Errore creazione/aggiornamento booking: {e}")
        return "Errore temporaneo nella prenotazione. Riprova tra poco."

def cancel_booking(business_id: str, user_id: str, **kwargs):
    """Cancella l'ultimo appuntamento di un utente"""
    last_booking = db.bookings.find_one(
        {"user_id": user_id, "business_id": business_id, "status": "confirmed"}, 
        sort=[("confirmed_at", -1)]
    )
    
    if not last_booking:
        return "Non ho trovato nessuna prenotazione attiva da cancellare."
    
    calendar_service = get_calendar_service(business_id)
    if not calendar_service:
        return "Servizio calendario non configurato per la cancellazione."
    
    try:
        if calendar_service.cancel_appointment(last_booking['calendar_event_id']):
            db.bookings.update_one(
                {"_id": last_booking["_id"]}, 
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now().isoformat()}}
            )
            
            # Recupera dettagli per messaggio di conferma
            booking_data = json.loads(last_booking.get('booking_data', '{}'))
            service = booking_data.get('service_type', 'Appuntamento')
            date = booking_data.get('date', '')
            time = booking_data.get('time', '')
            
            return f"✅ {service} del {date} alle {time} cancellato con successo."
        else:
            return "Errore durante la cancellazione dell'appuntamento. Contattaci direttamente."
    except Exception as e:
        print(f"❌ Errore cancellazione: {e}")
        return "Errore temporaneo nella cancellazione. Riprova o contattaci direttamente."

def get_business_info(business_id: str, **kwargs):
    """Recupera le informazioni generali sul business"""
    business = db.businesses.find_one({"_id": business_id})
    if not business:
        return "Errore: informazioni business non trovate."
    
    services = _get_services(business)
    
    info = {
        "nome": business.get("business_name", "Non specificato"),
        "indirizzo": business.get("address", "Non specificato"),
        "orari_apertura": business.get("opening_hours", "Non specificati"),
        "descrizione": business.get("description", ""),
        "servizi_offerti": services or []
    }
    
    # Formatta i servizi in modo più leggibile
    if services:
        services_text = []
        for service in services:
            duration = service.get('duration', 0)
            services_text.append(f"- {service.get('name', 'Servizio')} ({duration} min)")
        info["servizi_formattati"] = "\n".join(services_text)
    
    return json.dumps(info, default=str, ensure_ascii=False)