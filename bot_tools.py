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
    try:
        # Validazione business
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato nel database."
        
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato. Contatta l'amministratore."

        # Validazione servizio
        selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
        if not selected_service:
            service_names = [s['name'] for s in services]
            return f"Servizio '{service_name}' non trovato. Servizi disponibili: {', '.join(service_names)}."

        # Validazione data
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return f"Formato data non valido: {date}. Usa YYYY-MM-DD."

        # Verifica data non nel passato
        today = datetime.now().date()
        request_date = datetime.strptime(date, '%Y-%m-%d').date()
        if request_date < today:
            return f"Non puoi prenotare per {date} (data passata). Scegli una data futura."

        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato."

        # Orari di lavoro
        booking_hours = business.get("booking_hours", "9-18")
        try:
            start_hour, end_hour = map(int, booking_hours.split("-"))
        except (ValueError, AttributeError):
            start_hour, end_hour = 9, 18

        # AGGIORNAMENTO: Controlla anche booking nel database locale
        confirmed_bookings = list(db.bookings.find({
            "business_id": business_id,
            "status": "confirmed"
        }))

        # Cerca slot
        slots = calendar_service.get_available_slots(
            date=date, 
            duration_minutes=selected_service['duration'], 
            start_hour=start_hour, 
            end_hour=end_hour
        )
        
        # FILTRO AGGIUNTIVO: Rimuovi slot che sono già prenotati nel database
        for booking in confirmed_bookings:
            try:
                booking_data = json.loads(booking.get("booking_data", "{}"))
                if booking_data.get("date") == date:
                    booked_time = booking_data.get("time")
                    if booked_time:
                        # Rimuovi slot che coincidono esattamente con booking esistenti
                        slots = [s for s in slots if s['start'] != booked_time]
            except Exception as e:
                print(f"⚠️ Errore controllo booking esistente: {e}")
        
        if not slots:
            return f"Nessun orario disponibile per {date}. Prova un'altra data."
        
        # Filtra slot futuri se è oggi
        if request_date == today:
            now = datetime.now()
            future_slots = []
            for slot in slots:
                # CORREZIONE CRITICA: Confronta datetime completi, non solo time
                slot_datetime = datetime.combine(
                    request_date,
                    datetime.strptime(slot['start'], '%H:%M').time()
                )
                # Solo slot almeno 10 minuti nel futuro (margine maggiore)
                if slot_datetime > now + timedelta(minutes=10):
                    future_slots.append(slot)
            slots = future_slots
            
        if not slots:
            return f"Nessun orario futuro disponibile per oggi. Prova domani."
        
        available_times = [s['start'] for s in slots]
        return json.dumps(available_times)
        
    except Exception as e:
        print(f"❌ Errore get_available_slots: {e}")
        import traceback
        traceback.print_exc()
        return "Errore temporaneo. Riprova."

def get_next_available_slot(business_id: str, service_name: str, **kwargs):
    """Trova il primo orario disponibile per un servizio (oggi o domani)"""
    try:
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato."
        
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato."

        selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
        if not selected_service:
            service_names = [s['name'] for s in services]
            return f"Servizio '{service_name}' non trovato. Disponibili: {', '.join(service_names)}."

        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato."

        booking_hours = business.get("booking_hours", "9-18")
        try:
            start_hour, end_hour = map(int, booking_hours.split("-"))
        except (ValueError, AttributeError):
            start_hour, end_hour = 9, 18

        # Controllo booking esistenti nel database
        confirmed_bookings = list(db.bookings.find({
            "business_id": business_id,
            "status": "confirmed"
        }))

        # Prova oggi
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()  # Datetime completo per confronto preciso
        
        slots = calendar_service.get_available_slots(
            date=today, 
            duration_minutes=selected_service['duration'], 
            start_hour=start_hour, 
            end_hour=end_hour
        )
        
        # Filtra slot già prenotati nel database
        for booking in confirmed_bookings:
            try:
                booking_data = json.loads(booking.get("booking_data", "{}"))
                if booking_data.get("date") == today:
                    booked_time = booking_data.get("time")
                    if booked_time:
                        slots = [s for s in slots if s['start'] != booked_time]
            except Exception as e:
                print(f"⚠️ Errore controllo booking: {e}")
        
        # CORREZIONE CRITICA: Filtra slot confrontando datetime completi
        if slots:
            future_slots = []
            for slot in slots:
                # Crea datetime completo per confronto preciso
                slot_datetime = datetime.combine(
                    datetime.strptime(today, '%Y-%m-%d').date(),
                    datetime.strptime(slot['start'], '%H:%M').time()
                )
                
                # Solo slot almeno 10 minuti nel futuro per sicurezza
                if slot_datetime > now + timedelta(minutes=10):
                    future_slots.append(slot)
            
            if future_slots:
                first_slot = future_slots[0]
                return json.dumps({
                    "date": today,
                    "time": first_slot['start'],
                    "message": f"Il primo orario disponibile è oggi alle {first_slot['start']}"
                })

        # Se oggi non va, prova domani
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        slots = calendar_service.get_available_slots(
            date=tomorrow, 
            duration_minutes=selected_service['duration'], 
            start_hour=start_hour, 
            end_hour=end_hour
        )
        
        # Filtra slot già prenotati domani
        for booking in confirmed_bookings:
            try:
                booking_data = json.loads(booking.get("booking_data", "{}"))
                if booking_data.get("date") == tomorrow:
                    booked_time = booking_data.get("time")
                    if booked_time:
                        slots = [s for s in slots if s['start'] != booked_time]
            except Exception as e:
                print(f"⚠️ Errore controllo booking domani: {e}")
        
        if slots:
            first_slot = slots[0]
            return json.dumps({
                "date": tomorrow,
                "time": first_slot['start'],
                "message": f"Il primo orario disponibile è domani alle {first_slot['start']}"
            })

        return "Non ci sono orari disponibili oggi o domani. Prova un'altra data."
        
    except Exception as e:
        print(f"❌ Errore get_next_available_slot: {e}")
        import traceback
        traceback.print_exc()
        return "Errore nella ricerca. Riprova."

def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str, **kwargs):
    """Crea o aggiorna un appuntamento"""
    try:
        # Validazioni base
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato."
        
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato."

        selected_service = next((s for s in services if s['name'].lower() == service_name.lower()), None)
        if not selected_service:
            service_names = [s['name'] for s in services]
            return f"Servizio '{service_name}' non trovato. Disponibili: {', '.join(service_names)}."

        # Validazioni data e ora
        try:
            appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time, '%H:%M').time()
            appointment_datetime = datetime.combine(appointment_date, appointment_time)
        except ValueError:
            return "Formato data/ora non valido. Usa YYYY-MM-DD e HH:MM."

        # VALIDAZIONE CRITICA: Non permettere prenotazioni passate
        now = datetime.now()
        if appointment_datetime <= now:
            return f"Non puoi prenotare per {date} alle {time} (è nel passato). Ora: {now.strftime('%H:%M')}."

        # Verifica orari di lavoro
        booking_hours = business.get("booking_hours", "9-18")
        try:
            start_hour, end_hour = map(int, booking_hours.split("-"))
            if not (start_hour <= appointment_time.hour < end_hour):
                return f"Orario {time} fuori dagli orari di lavoro ({start_hour}:00-{end_hour}:00)."
        except (ValueError, AttributeError):
            pass

        # CONTROLLO DOPPIO: Verifica che lo slot sia ancora disponibile
        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato."
            
        # Verifica disponibilità in tempo reale
        available_slots = calendar_service.get_available_slots(
            date=date,
            duration_minutes=selected_service['duration'],
            start_hour=start_hour,
            end_hour=end_hour
        )
        
        slot_available = any(slot['start'] == time for slot in available_slots)
        if not slot_available:
            return f"L'orario {time} non è più disponibile. Controlla gli orari liberi."

        # Cerca prenotazione esistente
        last_booking = db.bookings.find_one(
            {"user_id": user_id, "business_id": business_id, "status": "confirmed"}, 
            sort=[("confirmed_at", -1)]
        )
        
        if last_booking:
            # Aggiorna esistente
            event_id = calendar_service.update_appointment(
                event_id=last_booking['calendar_event_id'],
                new_date=date, 
                new_start_time=time, 
                duration_minutes=selected_service['duration']
            )
            action = "spostato"
        else:
            # Crea nuovo
            event_id = calendar_service.create_appointment(
                date=date, 
                start_time=time, 
                duration_minutes=selected_service['duration'],
                customer_name=user_name, 
                customer_phone=user_id, 
                service_type=service_name
            )
            action = "prenotato"

        if not event_id:
            return f"Errore nella creazione dell'appuntamento. Riprova."

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
                {"$set": {
                    "booking_data": json.dumps(booking_data),
                    "calendar_event_id": event_id,
                    "updated_at": datetime.now().isoformat()
                }}
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
            
        return f"✅ {service_name.title()} {action} per {date} alle {time}."
        
    except Exception as e:
        print(f"❌ Errore booking: {e}")
        import traceback
        traceback.print_exc()
        return "Errore nella prenotazione. Riprova."

def cancel_booking(business_id: str, user_id: str, **kwargs):
    """Cancella l'ultimo appuntamento di un utente"""
    try:
        last_booking = db.bookings.find_one(
            {"user_id": user_id, "business_id": business_id, "status": "confirmed"}, 
            sort=[("confirmed_at", -1)]
        )
        
        if not last_booking:
            return "Nessuna prenotazione da cancellare."
        
        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato per cancellazione."
        
        if calendar_service.cancel_appointment(last_booking['calendar_event_id']):
            db.bookings.update_one(
                {"_id": last_booking["_id"]}, 
                {"$set": {"status": "cancelled", "cancelled_at": datetime.now().isoformat()}}
            )
            
            # Dettagli per conferma
            booking_data = json.loads(last_booking.get('booking_data', '{}'))
            service = booking_data.get('service_type', 'Appuntamento')
            date = booking_data.get('date', '')
            time = booking_data.get('time', '')
            
            return f"✅ {service} del {date} alle {time} cancellato."
        else:
            return "Errore nella cancellazione. Contattaci direttamente."
            
    except Exception as e:
        print(f"❌ Errore cancellazione: {e}")
        return "Errore nella cancellazione. Riprova."

def get_business_info(business_id: str, **kwargs):
    """Recupera le informazioni generali sul business"""
    try:
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Informazioni business non trovate."
        
        services = _get_services(business)
        
        info = {
            "nome": business.get("business_name", "Non specificato"),
            "indirizzo": business.get("address", "Non specificato"),
            "orari_apertura": business.get("opening_hours", "Non specificati"),
            "descrizione": business.get("description", ""),
            "servizi_offerti": services or []
        }
        
        # Formatta servizi
        if services:
            services_text = []
            for service in services:
                duration = service.get('duration', 0)
                services_text.append(f"- {service.get('name', 'Servizio')} ({duration} min)")
            info["servizi_formattati"] = "\n".join(services_text)
        
        return json.dumps(info, default=str, ensure_ascii=False)
        
    except Exception as e:
        print(f"❌ Errore business info: {e}")
        return "Errore nel recuperare le informazioni."