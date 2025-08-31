# calendar_service.py - Versione con controllo dinamico reale

import json
from datetime import datetime, timedelta, time as dtime
from google.oauth2.service_account import Credentials as ServiceCredentials
from googleapiclient.discovery import build
import pytz

class CalendarService:
    def __init__(self, calendar_id=None, service_account_key=None):
        if isinstance(calendar_id, list):
            self.calendar_ids = calendar_id
        elif calendar_id:
            self.calendar_ids = [calendar_id]
        else:
            self.calendar_ids = []
        self.service = None
        self.timezone = pytz.timezone('Europe/Rome')
        
        if service_account_key:
            self._init_service_account(service_account_key)

    def _init_service_account(self, service_account_key):
        try:
            creds_info = json.loads(service_account_key) if isinstance(service_account_key, str) and service_account_key.startswith('{') else service_account_key
            credentials = ServiceCredentials.from_service_account_info(
                creds_info, scopes=['https://www.googleapis.com/auth/calendar']
            )
            self.service = build('calendar', 'v3', credentials=credentials)
            print("✅ Google Calendar connesso")
        except Exception as e:
            print(f"❌ Errore connessione Google Calendar: {e}")
            self.service = None

    def get_working_hours_for_date(self, date_str):
        """
        Determina gli orari di lavoro effettivi per una data specifica
        controllando se ci sono eventi 'WORKING_HOURS' o 'CHIUSO' nel calendario
        """
        if not self.service or not self.calendar_ids:
            return None, None
            
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            start_of_day = self.timezone.localize(datetime.combine(target_date, dtime(0, 0)))
            end_of_day = self.timezone.localize(datetime.combine(target_date, dtime(23, 59, 59)))

            # Cerca eventi che definiscono orari di lavoro o chiusure
            events_result = self.service.events().list(
                calendarId=self.calendar_ids[0],
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            working_start = None
            working_end = None
            is_closed = False
            
            for event in events:
                if event.get('status') == 'cancelled':
                    continue
                    
                summary = event.get('summary', '').upper()
                
                # Controlla se il business è chiuso
                if any(keyword in summary for keyword in ['CHIUSO', 'CLOSED', 'FERIE', 'VACATION']):
                    print(f"🚫 Business chiuso il {date_str}: {event.get('summary')}")
                    is_closed = True
                    break
                
                # Controlla orari di lavoro personalizzati
                if any(keyword in summary for keyword in ['ORARI', 'WORKING_HOURS', 'APERTO', 'OPEN']):
                    start_dt = event['start'].get('dateTime', event['start'].get('date'))
                    end_dt = event['end'].get('dateTime', event['end'].get('date'))
                    
                    if 'T' in start_dt and 'T' in end_dt:  # Eventi con orario specifico
                        start_time = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(end_dt.replace('Z', '+00:00'))
                        
                        if start_time.tzinfo:
                            start_time = start_time.astimezone(self.timezone)
                            end_time = end_time.astimezone(self.timezone)
                        
                        working_start = start_time.time()
                        working_end = end_time.time()
                        print(f"📅 Orari personalizzati per {date_str}: {working_start} - {working_end}")
                        break
            
            if is_closed:
                return None, None
            
            return working_start, working_end
            
        except Exception as e:
            print(f"❌ Errore controllo orari di lavoro: {e}")
            return None, None

    def get_available_slots(self, date, duration_minutes=60, start_hour=9, end_hour=18, slot_interval=30):
        """
        Trova slot disponibili controllando dinamicamente Google Calendar
        """
        if not self.service or not self.calendar_ids:
            print("❌ Servizio calendar non disponibile")
            return []
            
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            # 1. CONTROLLA ORARI DI LAVORO DINAMICI
            dynamic_start, dynamic_end = self.get_working_hours_for_date(date)
            
            if dynamic_start is None and dynamic_end is None:
                # Business chiuso per la giornata
                print(f"🚫 Business chiuso il {date}")
                return []
            
            # Usa orari dinamici se disponibili, altrimenti fallback ai default
            if dynamic_start and dynamic_end:
                actual_start_hour = dynamic_start.hour
                actual_end_hour = dynamic_end.hour
                print(f"📅 Uso orari dinamici: {actual_start_hour}:00 - {actual_end_hour}:00")
            else:
                actual_start_hour = start_hour
                actual_end_hour = end_hour
                print(f"📅 Uso orari default: {actual_start_hour}:00 - {actual_end_hour}:00")
            
            # 2. DEFINISCI FINESTRA TEMPORALE
            work_start = self.timezone.localize(datetime.combine(target_date, dtime(hour=actual_start_hour)))
            work_end = self.timezone.localize(datetime.combine(target_date, dtime(hour=actual_end_hour)))
            
            # 3. RECUPERA TUTTI GLI EVENTI OCCUPATI (con margine esteso)
            query_start = work_start - timedelta(hours=1)
            query_end = work_end + timedelta(hours=1)
            
            events_result = self.service.events().list(
                calendarId=self.calendar_ids[0],
                timeMin=query_start.isoformat(),
                timeMax=query_end.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                maxResults=100
            ).execute()
            
            busy_events = events_result.get('items', [])
            print(f"📋 Eventi trovati per {date}: {len(busy_events)}")
            
            # 4. PROCESSA EVENTI OCCUPATI
            busy_intervals = []
            for event in busy_events:
                if event.get('status') == 'cancelled':
                    continue
                
                summary = event.get('summary', '')
                
                # Salta eventi di sistema (orari di lavoro, ecc.)
                if any(keyword in summary.upper() for keyword in ['ORARI', 'WORKING_HOURS', 'SISTEMA']):
                    continue
                    
                start_dt = event['start'].get('dateTime', event['start'].get('date'))
                end_dt = event['end'].get('dateTime', event['end'].get('date'))
                
                # Salta eventi all-day
                if 'T' not in start_dt:
                    continue
                
                try:
                    event_start = datetime.fromisoformat(start_dt.replace('Z', '+00:00'))
                    event_end = datetime.fromisoformat(end_dt.replace('Z', '+00:00'))
                    
                    if event_start.tzinfo:
                        event_start = event_start.astimezone(self.timezone)
                        event_end = event_end.astimezone(self.timezone)
                    
                    busy_intervals.append({
                        'start': event_start,
                        'end': event_end,
                        'summary': summary
                    })
                    print(f"🚫 Evento occupato: {summary} ({event_start.strftime('%H:%M')} - {event_end.strftime('%H:%M')})")
                    
                except Exception as e:
                    print(f"⚠️ Errore parsing evento: {e}")
                    continue
            
            # 5. GENERA SLOT CANDIDATI
            available_slots = []
            current_time = work_start
            slot_duration = timedelta(minutes=duration_minutes)
            slot_step = timedelta(minutes=slot_interval)
            
            while current_time + slot_duration <= work_end:
                slot_end = current_time + slot_duration
                
                # Controlla se questo slot è libero
                is_free = True
                for busy in busy_intervals:
                    # Aggiungi buffer di 5 minuti prima e dopo ogni evento
                    busy_start_buffered = busy['start'] - timedelta(minutes=5)
                    busy_end_buffered = busy['end'] + timedelta(minutes=5)
                    
                    # Controlla sovrapposizione
                    if (current_time < busy_end_buffered and slot_end > busy_start_buffered):
                        is_free = False
                        print(f"❌ Slot {current_time.strftime('%H:%M')} occupato da: {busy['summary']}")
                        break
                
                if is_free:
                    available_slots.append({
                        'start': current_time.strftime('%H:%M'),
                        'end': slot_end.strftime('%H:%M'),
                        'datetime': current_time.isoformat()
                    })
                    print(f"✅ Slot libero: {current_time.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}")
                
                current_time += slot_step
            
            print(f"📊 Slot totali disponibili per {date}: {len(available_slots)}")
            return available_slots
            
        except Exception as e:
            print(f"❌ Errore ricerca slot: {e}")
            import traceback
            traceback.print_exc()
            return []

    def create_appointment(self, date, start_time, duration_minutes, customer_name, customer_phone, service_type="Appuntamento", notes=""):
        if not self.service or not self.calendar_ids:
            return None
        try:
            start_dt = self.timezone.localize(datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M'))
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            # Verifica ultima volta che lo slot sia ancora libero
            verification_slots = self.get_available_slots(
                date=date,
                duration_minutes=duration_minutes,
                start_hour=start_dt.hour,
                end_hour=end_dt.hour + 1
            )
            
            slot_still_available = any(slot['start'] == start_time for slot in verification_slots)
            if not slot_still_available:
                print(f"❌ Slot {start_time} non più disponibile al momento della creazione")
                return None

            event = {
                'summary': f"{service_type} - {customer_name}",
                'description': f"Cliente: {customer_name}\nTelefono: {customer_phone}\nServizio: {service_type}\nNote: {notes}",
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Rome'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Rome'},
                'reminders': {
                    'useDefault': False, 
                    'overrides': [
                        {'method': 'popup', 'minutes': 60},
                        {'method': 'popup', 'minutes': 15}
                    ]
                }
            }
            
            created_event = self.service.events().insert(calendarId=self.calendar_ids[0], body=event).execute()
            event_id = created_event.get('id')
            
            print(f"✅ Appuntamento creato con ID: {event_id}")
            return event_id
            
        except Exception as e:
            print(f"❌ Errore creazione appuntamento: {e}")
            import traceback
            traceback.print_exc()
            return None

    def cancel_appointment(self, event_id):
        if not self.service or not self.calendar_ids:
            return False
        try:
            self.service.events().delete(calendarId=self.calendar_ids[0], eventId=event_id).execute()
            print(f"✅ Appuntamento {event_id} cancellato")
            return True
        except Exception as e:
            print(f"❌ Errore cancellazione: {e}")
            return False

    def check_business_hours_override(self, date_str):
        """
        Controlla se ci sono override specifici per gli orari di business per una data
        Ritorna: (is_open, start_time, end_time) o None se usa orari normali
        """
        try:
            working_start, working_end = self.get_working_hours_for_date(date_str)
            
            if working_start is None and working_end is None:
                # Business esplicitamente chiuso
                return False, None, None
            elif working_start and working_end:
                # Orari personalizzati
                return True, working_start, working_end
            else:
                # Usa orari normali (nessun override)
                return None, None, None
                
        except Exception as e:
            print(f"⚠️ Errore controllo override orari: {e}")
            return None, None, None