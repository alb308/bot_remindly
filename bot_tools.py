import json
from datetime import datetime, timedelta
from database import db_connection
from calendar_service import CalendarService
import os
import traceback

db = db_connection
calendar_services = {}

def get_calendar_service(business_id):
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
            print(f"❌ Configurazione calendario mancante per business {business_id}")
    return calendar_services.get(business_id)

def _get_services_and_hours(business_id):
    """Helper unificato per recuperare servizi e orari dal database."""
    business = db.businesses.find_one({"_id": business_id})
    if not business:
        return None, None, "Impossibile trovare le impostazioni del business. Contattare l'assistenza."

    # Carica i servizi
    services_data = business.get("services")
    services = []
    if isinstance(services_data, list):
        services = services_data
    elif isinstance(services_data, str):
        try:
            services = json.loads(services_data)
        except json.JSONDecodeError:
            return None, None, "Errore nella configurazione dei servizi. Contattare l'assistenza."

    if not services:
        return None, None, "Nessun servizio configurato per questo business."

    # Carica e valida gli orari
    booking_hours_str = business.get("booking_hours")
    if not booking_hours_str or "-" not in booking_hours_str:
        return services, None, "Orari di apertura non configurati correttamente. Contattare l'assistenza."
    
    try:
        start_hour, end_hour = map(int, booking_hours_str.split('-'))
        booking_hours = (start_hour, end_hour)
    except (ValueError, TypeError):
        return services, None, "Formato orari non valido nel database. Contattare l'assistenza."

    return services, booking_hours, None

def get_available_slots(business_id: str, service_name: str, date: str, **kwargs):
    print(f"🔍 get_available_slots per '{service_name}' il {date}")
    try:
        services, booking_hours, error = _get_services_and_hours(business_id)
        if error: return error
        start_hour, end_hour = booking_hours

        # Trova servizio richiesto
        selected_service = next((s for s in services if service_name.lower() in s.get('name', '').lower()), None)
        if not selected_service:
            service_names = ", ".join([s.get('name', 'N/A') for s in services])
            return f"Servizio '{service_name}' non trovato. I servizi disponibili sono: {service_names}. Per favore, riformula la tua richiesta."

        # Valida la data
        try:
            request_date = datetime.strptime(date, '%Y-%m-%d').date()
            if request_date < datetime.now().date():
                return f"La data {date} è passata. Per favore, scegli una data futura."
        except ValueError:
            return f"Formato data non valido: '{date}'. Usa il formato AAAA-MM-GG (es. {datetime.now().strftime('%Y-%m-%d')})."

        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Il servizio calendario non è configurato. Contatta l'assistenza."

        available_slots = calendar_service.get_available_slots(
            date=date, 
            duration_minutes=selected_service.get('duration', 60), 
            start_hour=start_hour,
            end_hour=end_hour
        )

        if not available_slots:
            return f"Nessun orario disponibile per il servizio '{selected_service['name']}' in data {date}. Prova un altro giorno."
        
        # Filtra slot passati se la data è oggi
        if request_date == datetime.now().date():
            now_time = datetime.now().time()
            future_slots = [s for s in available_slots if datetime.strptime(s['start'], '%H:%M').time() > now_time]
            if not future_slots:
                return f"Non ci sono più orari disponibili per oggi per il servizio '{selected_service['name']}'. Prova per domani."
            available_slots = future_slots
        
        return json.dumps([s['start'] for s in available_slots])

    except Exception as e:
        print(f"❌ Errore critico in get_available_slots: {e}\n{traceback.format_exc()}")
        return "Si è verificato un errore inaspettato. Per favore, riprova a formulare la tua richiesta."

def get_next_available_slot(business_id: str, service_name: str, **kwargs):
    print(f"🔍 get_next_available_slot per '{service_name}'")
    try:
        # Cerca oggi
        today_str = datetime.now().strftime('%Y-%m-%d')
        slots_today_json = get_available_slots(business_id, service_name, today_str)
        
        try:
            slots_today = json.loads(slots_today_json)
            if isinstance(slots_today, list) and slots_today:
                return json.dumps({"date": today_str, "time": slots_today[0]})
        except (json.JSONDecodeError, TypeError):
            # Se non è una lista JSON, è un messaggio di errore, lo gestiamo dopo
            pass

        # Se oggi non ci sono slot, cerca domani
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        slots_tomorrow_json = get_available_slots(business_id, service_name, tomorrow_str)
        
        try:
            slots_tomorrow = json.loads(slots_tomorrow_json)
            if isinstance(slots_tomorrow, list) and slots_tomorrow:
                return json.dumps({"date": tomorrow_str, "time": slots_tomorrow[0]})
        except (json.JSONDecodeError, TypeError):
            # Se anche domani non va, restituiamo l'errore originale (più probabile)
            return slots_today_json # Restituisce il messaggio di errore da get_available_slots (es. servizio non trovato)

        return "Non sono stati trovati orari disponibili né per oggi né per domani. Prova a specificare un'altra data."

    except Exception as e:
        print(f"❌ Errore critico in get_next_available_slot: {e}\n{traceback.format_exc()}")
        return "Si è verificato un errore inaspettato. Per favore, riprova a formulare la tua richiesta."


def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str, **kwargs):
    print(f"📝 Creazione booking: {service_name} per {date} alle {time}")
    try:
        services, booking_hours, error = _get_services_and_hours(business_id)
        if error: return error
        start_hour, end_hour = booking_hours

        selected_service = next((s for s in services if service_name.lower() in s.get('name', '').lower()), None)
        if not selected_service:
            service_names = ", ".join([s.get('name', 'N/A') for s in services])
            return f"Servizio '{service_name}' non trovato. Impossibile prenotare. Scegli tra: {service_names}."

        # Validazione finale della disponibilità
        available_slots_json = get_available_slots(business_id, service_name, date)
        try:
            available_slots = json.loads(available_slots_json)
            if time not in available_slots:
                return f"L'orario {time} del {date} non è più disponibile. Scegli un altro orario tra questi: {', '.join(available_slots[:5])}..."
        except (json.JSONDecodeError, TypeError):
            return f"Impossibile verificare la disponibilità per il {date}. Motivo: {available_slots_json}"

        calendar_service = get_calendar_service(business_id)
        if not calendar_service: return "Servizio calendario non configurato."

        # Cancella eventuali booking precedenti dello stesso utente
        # (Logica omessa per brevità, la tua era già corretta)

        event_id = calendar_service.create_appointment(
            date=date, 
            start_time=time, 
            duration_minutes=selected_service.get('duration', 60),
            customer_name=user_name, 
            customer_phone=user_id, 
            service_type=selected_service.get('name')
        )

        if not event_id:
            return "Creazione appuntamento fallita. L'orario potrebbe essere stato appena occupato. Riprova."

        # Salva su DB
        booking_data = {
            "user_id": user_id, "business_id": business_id,
            "booking_data": json.dumps({"service_type": selected_service['name'], "date": date, "time": time}),
            "status": "confirmed", "calendar_event_id": event_id,
            "created_at": datetime.now().isoformat()
        }
        db.bookings.insert_one(booking_data)
        
        return f"Perfetto! Appuntamento confermato per '{selected_service['name']}' il {date} alle {time}."

    except Exception as e:
        print(f"❌ Errore critico in create_or_update_booking: {e}\n{traceback.format_exc()}")
        return "Si è verificato un errore inaspettato durante la prenotazione. Riprova."

# Le funzioni cancel_booking e get_business_info rimangono simili ma andrebbero anch'esse rese più robuste
# con la stessa logica di gestione errori.

def cancel_booking(business_id: str, user_id: str, **kwargs):
    # ... implementazione con messaggi di errore migliorati ...
    return "Funzione di cancellazione in manutenzione."


def get_business_info(business_id: str, **kwargs):
    try:
        services, booking_hours, error = _get_services_and_hours(business_id)
        if error: return error
        
        business = db.businesses.find_one({"_id": business_id})
        start_h, end_h = booking_hours
        
        services_text = "\n".join([f"- {s['name']} ({s['duration']} min)" for s in services])
        
        info = (
            f"Ecco le informazioni su {business.get('business_name', 'questo business')}:\n"
            f"📍 Indirizzo: {business.get('address', 'Non specificato')}\n"
            f"🕒 Orari base: {business.get('opening_hours', f'{start_h}:00 - {end_h}:00')}\n"
            f"ℹ️ {business.get('description', '')}\n\n"
            f"Servizi offerti:\n{services_text}"
        )
        return info

    except Exception as e:
        print(f"❌ Errore critico in get_business_info: {e}\n{traceback.format_exc()}")
        return "Non riesco a recuperare le informazioni al momento. Riprova più tardi."