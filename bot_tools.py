import json
from datetime import datetime
from db_sqlite import SQLiteClient
from calendar_service import CalendarService
import os

# Inizializza i servizi una sola volta per efficienza
db = SQLiteClient
calendar_services = {}

def get_calendar_service(business_id):
    if business_id not in calendar_services:
        business = db.businesses.find_one({"_id": business_id})
        if business and business.get("google_calendar_id") and os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY"):
            calendar_id = business["google_calendar_id"]
            service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
            calendar_services[business_id] = CalendarService(calendar_id=calendar_id, service_account_key=service_account_key)
    return calendar_services.get(business_id)

def get_available_slots(business_id: str, service_name: str, date: str):
    """
    Trova gli orari disponibili per un servizio specifico in una data specifica.
    Usa questa funzione quando un utente chiede la disponibilità.
    'date' deve essere in formato 'YYYY-MM-DD'.
    """
    business = db.businesses.find_one({"_id": business_id})
    services_str = business.get("services", "[]")
    services = json.loads(services_str) if isinstance(services_str, str) else services_str
    
    selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
    if not selected_service:
        return f"Servizio '{service_name}' non trovato."

    calendar_service = get_calendar_service(business_id)
    if not calendar_service:
        return "Servizio calendario non configurato."

    bh = business.get("booking_hours", "9-18").split("-")
    slots = calendar_service.get_available_slots(date, duration_minutes=selected_service['duration'], start_hour=int(bh[0]), end_hour=int(bh[1]))
    
    if not slots:
        return f"Nessun orario disponibile per il {date} per il servizio {service_name}."
    
    return json.dumps([s['start'] for s in slots])

def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str):
    """
    Crea un nuovo appuntamento o aggiorna uno esistente se l'utente ne ha già uno per quella data.
    'date' deve essere in formato 'YYYY-MM-DD', 'time' in formato 'HH:MM'.
    """
    business = db.businesses.find_one({"_id": business_id})
    services_str = business.get("services", "[]")
    services = json.loads(services_str) if isinstance(services_str, str) else services_str

    selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
    if not selected_service:
        return f"Servizio '{service_name}' non trovato."

    calendar_service = get_calendar_service(business_id)
    if not calendar_service:
        return "Servizio calendario non configurato."

    # Controlla se esiste già una prenotazione da aggiornare
    last_booking = db.bookings.find_one({"user_id": user_id, "business_id": business_id, "status": "confirmed"}, sort=[("confirmed_at", -1)])
    
    if last_booking:
        # Aggiorna appuntamento esistente
        event_id = calendar_service.update_appointment(
            event_id=last_booking['calendar_event_id'],
            new_date=date, new_start_time=time, duration_minutes=selected_service['duration']
        )
    else:
        # Crea un nuovo appuntamento
        event_id = calendar_service.create_appointment(
            date=date, start_time=time, duration_minutes=selected_service['duration'],
            customer_name=user_name, customer_phone=user_id, service_type=service_name
        )

    if not event_id:
        return "Errore: impossibile creare o aggiornare l'appuntamento sul calendario."

    # Salva o aggiorna nel database
    booking_data = {"date": date, "time": time, "duration": selected_service['duration'], "service_type": service_name, "customer_name": user_name, "customer_phone": user_id}
    if last_booking:
        db.bookings.update_one({"_id": last_booking["_id"]}, {"$set": {"booking_data": json.dumps(booking_data)}})
    else:
        db.bookings.insert_one({
            "user_id": user_id, "business_id": business_id, "booking_data": json.dumps(booking_data),
            "status": "confirmed", "calendar_event_id": event_id, "created_at": datetime.now().isoformat(), "confirmed_at": datetime.now().isoformat()
        })
        
    return f"Appuntamento per {service_name} confermato per il {date} alle {time}."

def cancel_booking(business_id: str, user_id: str):
    """
    Cancella l'ultimo appuntamento confermato di un utente.
    Usa questa funzione quando l'utente esprime l'intenzione di annullare, disdire o che ha un imprevisto.
    """
    last_booking = db.bookings.find_one({"user_id": user_id, "business_id": business_id, "status": "confirmed"}, sort=[("confirmed_at", -1)])
    if not last_booking:
        return "Non ho trovato nessuna prenotazione attiva da cancellare."
    
    calendar_service = get_calendar_service(business_id)
    if calendar_service.cancel_appointment(last_booking['calendar_event_id']):
        db.bookings.update_one({"_id": last_booking["_id"]}, {"$set": {"status": "cancelled"}})
        return "Appuntamento cancellato con successo."
    else:
        return "Errore durante la cancellazione dell'appuntamento."

def get_business_info(business_id: str):
    """
    Recupera le informazioni generali sul business come orari, descrizione, indirizzo e lista dei servizi.
    Usa questa funzione se l'utente fa una domanda generica sul business.
    """
    business = db.businesses.find_one({"_id": business_id})
    info = {
        "nome": business.get("business_name"),
        "indirizzo": business.get("address"),
        "orari": business.get("opening_hours"),
        "descrizione": business.get("description"),
        "servizi": business.get("services")
    }
    return json.dumps(info, default=str)