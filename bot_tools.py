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
            print(f"❌ Configurazione calendario mancante per business {business_id}")
    return calendar_services.get(business_id)

def _get_services(business):
    """Funzione helper robusta per caricare i servizi in modo sicuro."""
    if not business:
        print("❌ Business non fornito a _get_services")
        return []
        
    services_data = business.get("services")
    
    if isinstance(services_data, list):
        print(f"✅ Servizi caricati come lista: {len(services_data)} servizi")
        return services_data
    
    if isinstance(services_data, str) and services_data.strip():
        try:
            parsed_services = json.loads(services_data)
            print(f"✅ Servizi parsati da JSON: {len(parsed_services)} servizi")
            return parsed_services
        except json.JSONDecodeError as e:
            print(f"❌ Errore parsing servizi: {e}")
            return []
    
    print(f"❌ Services data non valido: {type(services_data)}")
    return []

def get_next_available_slot(business_id: str, service_name: str, **kwargs):
    """Trova il primo orario disponibile con controllo dinamico del calendario"""
    print(f"🔍 get_next_available_slot per '{service_name}'")
    
    try:
        # VALIDAZIONE BUSINESS
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato nel database."
        
        print(f"✅ Business: {business.get('business_name')}")
        
        # VALIDAZIONE SERVIZI
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato."

        # RICERCA SERVIZIO
        selected_service = None
        service_name_lower = service_name.lower().strip()
        
        for s in services:
            if service_name_lower in s.get('name', '').lower():
                selected_service = s
                break
        
        if not selected_service and services:
            selected_service = services[0]
            print(f"⚠️ Uso primo servizio: {selected_service.get('name')}")
        
        if not selected_service:
            service_names = [s.get('name', 'N/A') for s in services]
            return f"Nessun servizio utilizzabile. Configurati: {', '.join(service_names)}"

        print(f"✅ Servizio: {selected_service.get('name')} ({selected_service.get('duration')}min)")

        # CALENDARIO
        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario Google non configurato."

        # ORARI DEFAULT (usati solo come fallback)
        booking_hours = business.get("booking_hours", "9-18")
        try:
            default_start, default_end = map(int, booking_hours.split("-"))
        except (ValueError, AttributeError):
            default_start, default_end = 9, 18

        # CERCA OGGI CON CONTROLLO DINAMICO
        today = datetime.now().strftime('%Y-%m-%d')
        now = datetime.now()
        print(f"🔍 Cerco slot OGGI ({today})")
        
        try:
            # Il sistema ora controlla dinamicamente Google Calendar per orari effettivi
            slots_today = calendar_service.get_available_slots(
                date=today, 
                duration_minutes=selected_service.get('duration', 60), 
                start_hour=default_start,  # Usato solo come fallback
                end_hour=default_end,      # Usato solo come fallback
                slot_interval=30
            )
            
            print(f"📅 Slot disponibili oggi: {len(slots_today)}")
            
            # Filtra solo slot futuri (almeno 15 minuti avanti)
            future_slots_today = []
            for slot in slots_today:
                try:
                    slot_datetime = datetime.combine(
                        datetime.strptime(today, '%Y-%m-%d').date(),
                        datetime.strptime(slot['start'], '%H:%M').time()
                    )
                    
                    if slot_datetime > now + timedelta(minutes=15):
                        future_slots_today.append(slot)
                except Exception as e:
                    print(f"⚠️ Errore parsing slot: {e}")
            
            print(f"✅ Slot futuri oggi: {len(future_slots_today)}")
            
            if future_slots_today:
                first_slot = future_slots_today[0]
                result = {
                    "date": today,
                    "time": first_slot['start'],
                    "message": f"Primo orario disponibile: oggi alle {first_slot['start']}"
                }
                print(f"✅ TROVATO oggi: {json.dumps(result)}")
                return json.dumps(result)
        
        except Exception as e:
            print(f"❌ Errore ricerca oggi: {e}")

        # CERCA DOMANI CON CONTROLLO DINAMICO
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        print(f"🔍 Cerco slot DOMANI ({tomorrow})")
        
        try:
            slots_tomorrow = calendar_service.get_available_slots(
                date=tomorrow, 
                duration_minutes=selected_service.get('duration', 60), 
                start_hour=default_start,
                end_hour=default_end,
                slot_interval=30
            )
            
            print(f"📅 Slot disponibili domani: {len(slots_tomorrow)}")
            
            if slots_tomorrow:
                first_slot = slots_tomorrow[0]
                result = {
                    "date": tomorrow,
                    "time": first_slot['start'],
                    "message": f"Primo orario disponibile: domani ({tomorrow}) alle {first_slot['start']}"
                }
                print(f"✅ TROVATO domani: {json.dumps(result)}")
                return json.dumps(result)
        
        except Exception as e:
            print(f"❌ Errore ricerca domani: {e}")

        # NESSUN SLOT TROVATO
        return "Non ci sono orari disponibili oggi o domani. Prova a specificare una data futura o contattaci direttamente."
        
    except Exception as e:
        error_msg = f"❌ Errore in get_next_available_slot: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg

def get_available_slots(business_id: str, service_name: str, date: str, **kwargs):
    """Trova orari disponibili per una data specifica usando controllo dinamico"""
    print(f"🔍 get_available_slots per '{service_name}' il {date}")
    
    try:
        # VALIDAZIONI BASE
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato."
        
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato."

        # RICERCA SERVIZIO
        selected_service = None
        service_name_lower = service_name.lower().strip()
        
        for s in services:
            if service_name_lower in s.get('name', '').lower():
                selected_service = s
                break
        
        if not selected_service and services:
            selected_service = services[0]
        
        if not selected_service:
            service_names = [s.get('name', 'N/A') for s in services]
            return f"Servizio non trovato. Disponibili: {', '.join(service_names)}"

        # VALIDAZIONE DATA
        try:
            request_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return f"Formato data non valido: {date}. Usa YYYY-MM-DD."

        if request_date < datetime.now().date():
            return f"Non puoi prenotare per {date} (data passata)."

        # CALENDARIO
        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato."

        # ORARI DEFAULT (fallback)
        booking_hours = business.get("booking_hours", "9-18")
        try:
            default_start, default_end = map(int, booking_hours.split("-"))
        except (ValueError, AttributeError):
            default_start, default_end = 9, 18

        # CONTROLLA SE IL BUSINESS È APERTO PER QUESTA DATA
        try:
            is_open, custom_start, custom_end = calendar_service.check_business_hours_override(date)
            
            if is_open is False:
                return f"Il business è chiuso il {date}."
            
            # Se ci sono orari personalizzati, usali
            if custom_start and custom_end:
                print(f"📅 Uso orari personalizzati per {date}: {custom_start} - {custom_end}")
                actual_start = custom_start.hour
                actual_end = custom_end.hour
            else:
                actual_start = default_start
                actual_end = default_end
                
        except Exception as e:
            print(f"⚠️ Errore controllo orari personalizzati: {e}")
            actual_start = default_start
            actual_end = default_end

        # CERCA SLOT DISPONIBILI (sistema dinamico)
        available_slots = calendar_service.get_available_slots(
            date=date, 
            duration_minutes=selected_service.get('duration', 60), 
            start_hour=actual_start,
            end_hour=actual_end,
            slot_interval=30
        )
        
        print(f"📊 Slot totali trovati: {len(available_slots)}")
        
        if not available_slots:
            return f"Nessun orario disponibile per {date}. Il calendario potrebbe essere pieno o il business chiuso."
        
        # FILTRA SLOT FUTURI SE È OGGI
        if request_date == datetime.now().date():
            now = datetime.now()
            future_slots = []
            
            for slot in available_slots:
                try:
                    slot_datetime = datetime.combine(
                        request_date,
                        datetime.strptime(slot['start'], '%H:%M').time()
                    )
                    if slot_datetime > now + timedelta(minutes=15):
                        future_slots.append(slot)
                except:
                    continue
                    
            available_slots = future_slots
            
            if not available_slots:
                return "Nessun orario futuro disponibile per oggi."
        
        # RISULTATO
        available_times = [s['start'] for s in available_slots]
        print(f"✅ Orari finali per {date}: {available_times}")
        return json.dumps(available_times)
        
    except Exception as e:
        print(f"❌ Errore get_available_slots: {e}")
        return "Errore nella ricerca orari. Riprova."

def create_or_update_booking(business_id: str, user_id: str, user_name: str, service_name: str, date: str, time: str, **kwargs):
    """Crea booking con validazione dinamica finale"""
    print(f"📝 Creazione booking: {service_name} per {date} alle {time}")
    
    try:
        # VALIDAZIONI
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            return "Business non trovato."
        
        services = _get_services(business)
        if not services:
            return "Nessun servizio configurato."

        # SERVIZIO
        selected_service = None
        service_name_lower = service_name.lower().strip()
        
        for s in services:
            if service_name_lower in s.get('name', '').lower():
                selected_service = s
                break
        
        if not selected_service and services:
            selected_service = services[0]
        
        if not selected_service:
            return f"Servizio non trovato."

        # VALIDAZIONE TEMPORALE
        try:
            appointment_date = datetime.strptime(date, '%Y-%m-%d').date()
            appointment_time = datetime.strptime(time, '%H:%M').time()
            appointment_datetime = datetime.combine(appointment_date, appointment_time)
        except ValueError:
            return "Formato data/ora non valido."

        if appointment_datetime <= datetime.now() + timedelta(minutes=5):
            return f"Non puoi prenotare per {date} alle {time} (troppo vicino o passato)."

        calendar_service = get_calendar_service(business_id)
        if not calendar_service:
            return "Calendario non configurato."
            
        # CANCELLA PRENOTAZIONI PRECEDENTI
        try:
            existing_bookings = list(db.bookings.find({
                "user_id": user_id, 
                "business_id": business_id, 
                "status": "confirmed"
            }))
            
            cancelled_count = 0
            for old_booking in existing_bookings:
                try:
                    old_event_id = old_booking.get('calendar_event_id')
                    if old_event_id and calendar_service.cancel_appointment(old_event_id):
                        db.bookings.update_one(
                            {"_id": old_booking["_id"]}, 
                            {"$set": {
                                "status": "cancelled_by_new_booking", 
                                "cancelled_at": datetime.now().isoformat()
                            }}
                        )
                        cancelled_count += 1
                except Exception as e:
                    print(f"⚠️ Errore cancellazione: {e}")
        except Exception as e:
            cancelled_count = 0

        # CREA APPUNTAMENTO (con validazione finale integrata)
        event_id = calendar_service.create_appointment(
            date=date, 
            start_time=time, 
            duration_minutes=selected_service.get('duration', 60),
            customer_name=user_name, 
            customer_phone=user_id, 
            service_type=selected_service.get('name', service_name)
        )

        if not event_id:
            return "Errore nella creazione dell'appuntamento. L'orario potrebbe non essere più disponibile."

        # SALVA DATABASE
        booking_data = {
            "date": date, 
            "time": time, 
            "duration": selected_service.get('duration', 60), 
            "service_type": selected_service.get('name', service_name), 
            "customer_name": user_name, 
            "customer_phone": user_id
        }
        
        try:
            db.bookings.insert_one({
                "user_id": user_id, 
                "business_id": business_id, 
                "booking_data": json.dumps(booking_data),
                "status": "confirmed", 
                "calendar_event_id": event_id, 
                "created_at": datetime.now().isoformat(), 
                "confirmed_at": datetime.now().isoformat()
            })
            print(f"✅ Booking salvato con event_id: {event_id}")
        except Exception as e:
            print(f"⚠️ Errore salvataggio booking: {e}")
        
        # MESSAGGIO CONFERMA
        service_display_name = selected_service.get('name', service_name).title()
        if cancelled_count > 0:
            return f"Prenotazione precedente cancellata. {service_display_name} confermato per {date} alle {time}."
        else:
            return f"{service_display_name} prenotato per {date} alle {time}."
        
    except Exception as e:
        print(f"❌ Errore booking: {e}")
        import traceback
        traceback.print_exc()
        return "Errore nella prenotazione. Riprova."

def cancel_booking(business_id: str, user_id: str, **kwargs):
    """Cancella l'ultimo appuntamento di un utente"""
    print(f"🗑️ Cancellazione booking per user {user_id}")
    
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
        
        print(f"ℹ️ Info business recuperate: {info['nome']}")
        return json.dumps(info, default=str, ensure_ascii=False)
        
    except Exception as e:
        print(f"❌ Errore business info: {e}")
        return "Errore nel recuperare le informazioni."