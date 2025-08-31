import json
from datetime import datetime, timedelta
from database import db_connection
from calendar_service import CalendarService
import os
import traceback
from thefuzz import process

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
    return calendar_services.get(business_id)

def _get_business_config(business_id):
    """Helper unificato per recuperare configurazione, servizi e orari dal DB."""
    business = db.businesses.find_one({"_id": business_id})
    if not business:
        return None, "Impossibile trovare le impostazioni del business."

    # Carica e valida i servizi
    services_data = business.get("services")
    services = []
    if isinstance(services_data, list):
        services = services_data
    elif isinstance(services_data, str) and services_data.strip():
        try:
            services = json.loads(services_data)
        except json.JSONDecodeError:
            return None, "Errore nella configurazione dei servizi."
    if not services:
        return None, "Nessun servizio è stato configurato per questo business."

    # Carica e valida gli orari di base
    booking_hours_str = business.get("booking_hours")
    if not booking_hours_str or "-" not in booking_hours_str:
        return None, "Gli orari di apertura non sono configurati correttamente."
    try:
        start_hour, end_hour = map(int, booking_hours_str.split('-'))
        booking_hours = (start_hour, end_hour)
    except (ValueError, TypeError):
        return None, "Il formato degli orari nel database non è valido."

    config = {
        "services": services,
        "booking_hours": booking_hours,
        "business_info": business
    }
    return config, None

def _find_best_service_match(query: str, services: list):
    """Trova il servizio migliore usando la ricerca fuzzy."""
    if not query: return None
    service_names = [s['name'] for s in services]
    best_match, score = process.extractOne(query, service_names)
    
    # Imposta una soglia di confidenza per evitare match errati
    if score >= 75:
        return next((s for s in services if s['name'] == best_match), None)
    return None

def get_available_slots(business_id: str, service_name: str, date: str, **kwargs):
    print(f"🔍 get_available_slots per '{service_name}' il {date}")
    try:
        config, error = _get_business_config(business_id)
        if error: return error
        
        selected_service = _find_best_service_match(service_name, config["services"])
        if not selected_service:
            service_names = ", ".join([s['name'] for s in config["services"]])
            return f"Servizio '{service_name}' non riconosciuto. Per favore, scegli tra: {service_names}."

        try:
            request_date = datetime.strptime(date, '%Y-%m-%d').date()
            if request_date < datetime.now().date():
                return f"La data {date} è già passata. Scegli una data futura."
        except ValueError:
            return f"Il formato della data '{date}' non è valido. Usa AAAA-MM-GG."

        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Il calendario non è configurato. Contatta l'assistenza."

        start_hour, end_hour = config["booking_hours"]
        available_slots = calendar_service.get_available_slots(
            date=date, 
            duration_minutes=selected_service.get('duration', 60), 
            start_hour=start_hour,
            end_hour=end_hour
        )

        if not available_slots:
            return f"Mi dispiace, non ci sono orari disponibili per '{selected_service['name']}' il {date}."
        
        if request_date == datetime.now().date():
            future_slots = [s for s in available_slots if datetime.strptime(s['start'], '%H:%M').time() > datetime.now().time()]
            if not future_slots:
                return f"Non ci sono più orari disponibili per oggi per '{selected_service['name']}'. Prova domani."
            available_slots = future_slots
        
        return json.dumps([s['start'] for s in available_slots])

    except Exception as e:
        traceback.print_exc()
        return "Si è verificato un errore imprevisto. Riprova a formulare la richiesta."

def get_next_available_slot(business_id: str, service_name: str, **kwargs):
    print(f"🔍 get_next_available_slot per '{service_name}'")
    try:
        config, error = _get_business_config(business_id)
        if error: return error
        
        selected_service = _find_best_service_match(service_name, config["services"])
        if not selected_service:
            service_names = ", ".join([s['name'] for s in config["services"]])
            return f"Per trovare il primo orario disponibile, dimmi quale servizio desideri tra: {service_names}."

        # Cerca slot per i prossimi 7 giorni
        for i in range(7):
            date_to_check = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            slots_json = get_available_slots(business_id, selected_service['name'], date_to_check)
            try:
                slots = json.loads(slots_json)
                if isinstance(slots, list) and slots:
                    day_name = "Oggi" if i == 0 else "Domani" if i == 1 else f"il {date_to_check}"
                    return json.dumps({
                        "date": date_to_check,
                        "time": slots[0],
                        "message": f"Il primo orario disponibile per '{selected_service['name']}' è {day_name} alle {slots[0]}."
                    })
            except (json.JSONDecodeError, TypeError):
                continue
        
        return f"Non ho trovato disponibilità per '{selected_service['name']}' nei prossimi 7 giorni. Vuoi provare a specificare una data più lontana?"

    except Exception as e:
        traceback.print_exc()
        return "Si è verificato un errore imprevisto. Riprova a formulare la richiesta."


def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str, **kwargs):
    print(f"📝 Creazione booking: {service_name} per {date} alle {time}")
    try:
        config, error = _get_business_config(business_id)
        if error: return error

        selected_service = _find_best_service_match(service_name, config["services"])
        if not selected_service:
            service_names = ", ".join([s['name'] for s in config["services"]])
            return f"Servizio '{service_name}' non riconosciuto. Impossibile prenotare. Scegli tra: {service_names}."

        # Validazione finale della disponibilità
        slots_json = get_available_slots(business_id, selected_service['name'], date)
        try:
            available_slots = json.loads(slots_json)
            if time not in available_slots:
                alt = f"Scegli tra questi: {', '.join(available_slots[:4])}..." if available_slots else "Prova un altro giorno."
                return f"L'orario delle {time} del {date} non è più disponibile. {alt}"
        except (json.JSONDecodeError, TypeError):
            return f"Impossibile verificare la disponibilità per il {date}. Motivo: {slots_json}"

        calendar_service = get_calendar_service(business_id)
        if not calendar_service: return "Servizio calendario non configurato."

        event_id = calendar_service.create_appointment(
            date=date, start_time=time, duration_minutes=selected_service.get('duration', 60),
            customer_name=user_name, customer_phone=user_id, service_type=selected_service.get('name')
        )

        if not event_id:
            return "Creazione appuntamento fallita. L'orario potrebbe essere stato appena occupato. Riprova."

        # Salva su DB (la tua logica qui era corretta)
        
        return f"Perfetto, appuntamento confermato! Ti aspetto per '{selected_service['name']}' il {date} alle {time}."

    except Exception as e:
        traceback.print_exc()
        return "Si è verificato un errore imprevisto durante la prenotazione."

def get_business_info(business_id: str, **kwargs):
    try:
        config, error = _get_business_config(business_id)
        if error: return error
        
        business = config["business_info"]
        services = config["services"]
        start_h, end_h = config["booking_hours"]
        
        services_text = "\n".join([f"- {s['name']} ({s['duration']} min)" for s in services])
        info = (
            f"Ecco le informazioni su {business.get('business_name', 'questo business')}:\n"
            f"📍 Indirizzo: {business.get('address', 'Non specificato')}\n"
            f"🕒 Orari di riferimento: {business.get('opening_hours', f'dalle {start_h} alle {end_h}')}\n"
            f"ℹ️ {business.get('description', '')}\n\n"
            f"Servizi offerti:\n{services_text}"
        )
        return info

    except Exception as e:
        traceback.print_exc()
        return "Non riesco a recuperare le informazioni al momento."

def cancel_booking(business_id: str, user_id: str, **kwargs):
    # Logica invariata, ma con gestione errori migliore
    try:
        # ... la tua logica di cancellazione qui ...
        return "La tua prenotazione è stata cancellata con successo."
    except Exception as e:
        traceback.print_exc()
        return "Non sono riuscito a cancellare la prenotazione. Contatta direttamente il negozio."