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
        # Cache per eventi recenti
        self._recent_bookings = []
        if service_account_key:
            self._init_service_account(service_account_key)

    def _init_service_account(self, service_account_key):
        try:
            creds_info = json.loads(service_account_key) if isinstance(service_account_key, str) and service_account_key.startswith('{') else service_account_key
            credentials = ServiceCredentials.from_service_account_info(
                creds_info, scopes=['https://www.googleapis.com/auth/calendar']
            )
            self.service = build('calendar', 'v3', credentials=credentials)
            print("✅ Google Calendar pronto")
        except Exception as e:
            print(f"❌ Errore init Google Calendar: {e}")
            self.service = None

    def get_available_slots(self, date, duration_minutes=60, start_hour=9, end_hour=18):
        if not self.service or not self.calendar_ids:
            return []
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            start_time = self.timezone.localize(datetime.combine(target_date, dtime(hour=start_hour)))
            
            if end_hour == 24:
                end_time = self.timezone.localize(datetime.combine(target_date, dtime(23, 59, 59)))
            else:
                end_time = self.timezone.localize(datetime.combine(target_date, dtime(hour=end_hour)))

            # SOLUZIONE 1: Forza refresh con updatedMin per vedere eventi recenti
            updated_min = (datetime.utcnow() - timedelta(minutes=10)).isoformat() + 'Z'
            
            events_result = self.service.events().list(
                calendarId=self.calendar_ids[0], 
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                updatedMin=updated_min,  # NUOVO: forza refresh eventi recenti
                singleEvents=True,
                orderBy='startTime',
                maxResults=100  # NUOVO: aumenta limite eventi
            ).execute()
            
            busy_events = events_result.get('items', [])
            
            # Formattiamo gli eventi occupati
            busy_intervals = []
            for event in busy_events:
                # Salta eventi cancellati o con status diverso da 'confirmed'
                if event.get('status') == 'cancelled':
                    continue
                    
                start_dt = event['start'].get('dateTime', event['start'].get('date'))
                end_dt = event['end'].get('dateTime', event['end'].get('date'))
                
                # Gestione eventi all-day
                if 'T' not in start_dt:
                    continue  # Salta eventi all-day
                    
                busy_intervals.append({
                    'start': start_dt,
                    'end': end_dt
                })

            # SOLUZIONE 2: Aggiungi anche i booking dalla cache locale
            for recent_booking in self._recent_bookings:
                if recent_booking['date'] == date:
                    # Converti in formato datetime per compatibilità
                    booking_start = self.timezone.localize(
                        datetime.strptime(f"{recent_booking['date']} {recent_booking['time']}", '%Y-%m-%d %H:%M')
                    )
                    booking_end = booking_start + timedelta(minutes=recent_booking['duration'])
                    
                    busy_intervals.append({
                        'start': booking_start.isoformat(),
                        'end': booking_end.isoformat()
                    })

            def overlaps(s, e, busy_list):
                for b in busy_list:
                    try:
                        bs = datetime.fromisoformat(b["start"].replace('Z', '+00:00'))
                        be = datetime.fromisoformat(b["end"].replace('Z', '+00:00'))
                        
                        # Converti a timezone locale se necessario
                        if bs.tzinfo:
                            bs = bs.astimezone(self.timezone)
                            be = be.astimezone(self.timezone)
                        else:
                            bs = self.timezone.localize(bs.replace(tzinfo=None))
                            be = self.timezone.localize(be.replace(tzinfo=None))
                            
                        # Controllo overlap con margine di sicurezza (5 minuti)
                        margin = timedelta(minutes=5)
                        if s < (be + margin) and e > (bs - margin):
                            return True
                    except Exception as parse_error:
                        print(f"⚠️ Errore parsing data: {parse_error}")
                        continue
                return False

            slots = []
            cur = start_time
            step = timedelta(minutes=30)  # Slot ogni 30 minuti
            dur = timedelta(minutes=duration_minutes)
            
            while cur + dur <= end_time:
                e = cur + dur
                if not overlaps(cur, e, busy_intervals):
                    slots.append({
                        'start': cur.strftime('%H:%M'), 
                        'end': e.strftime('%H:%M'), 
                        'datetime': cur.isoformat()
                    })
                cur += step
                
            return slots
            
        except Exception as e:
            print(f"❌ Errore slot: {e}")
            import traceback
            traceback.print_exc()
            return []

    def create_appointment(self, date, start_time, duration_minutes, customer_name, customer_phone, service_type="Appuntamento", notes=""):
        if not self.service or not self.calendar_ids:
            return None
        try:
            start_dt = self.timezone.localize(datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M'))
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            event = {
                'summary': f"{service_type} - {customer_name}",
                'description': f"Cliente: {customer_name}\nTelefono: {customer_phone}\nServizio: {service_type}\nNote: {notes}",
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Rome'},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Rome'},
                'reminders': {'useDefault': False, 'overrides': [{'method':'popup','minutes':60},{'method':'popup','minutes':15}]}
            }
            
            created_event = self.service.events().insert(calendarId=self.calendar_ids[0], body=event).execute()
            event_id = created_event.get('id')
            
            # SOLUZIONE 3: Aggiungi alla cache locale immediatamente
            if event_id:
                self._recent_bookings.append({
                    'date': date,
                    'time': start_time,
                    'duration': duration_minutes,
                    'event_id': event_id,
                    'created_at': datetime.now()
                })
                
                # Pulisci cache vecchia (mantieni solo ultimi 20 booking o ultima ora)
                now = datetime.now()
                self._recent_bookings = [
                    b for b in self._recent_bookings 
                    if (now - b['created_at']).total_seconds() < 3600  # Ultima ora
                ][-20:]  # Ultimi 20
                
                print(f"✅ Evento creato e aggiunto alla cache: {event_id}")
            
            return event_id
            
        except Exception as e:
            print(f"❌ Errore creazione evento: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_appointment(self, event_id):
        if not self.service:
            return None
        try:
            return self.service.events().get(calendarId=self.calendar_ids[0], eventId=event_id).execute()
        except Exception as e:
            print(f"❌ Errore nel recuperare evento {event_id}: {e}")
            return None

    def update_appointment(self, event_id, new_date, new_start_time, duration_minutes):
        if not self.service:
            return None
        try:
            event = self.get_appointment(event_id)
            if not event:
                return None

            start_dt = self.timezone.localize(datetime.strptime(f"{new_date} {new_start_time}", '%Y-%m-%d %H:%M'))
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            event['start']['dateTime'] = start_dt.isoformat()
            event['end']['dateTime'] = end_dt.isoformat()

            updated_event = self.service.events().update(
                calendarId=self.calendar_ids[0], eventId=event_id, body=event
            ).execute()
            
            # Aggiorna anche la cache locale
            for booking in self._recent_bookings:
                if booking.get('event_id') == event_id:
                    booking['date'] = new_date
                    booking['time'] = new_start_time
                    booking['duration'] = duration_minutes
                    break
            
            return updated_event.get('id')
            
        except Exception as e:
            print(f"❌ Errore aggiornamento evento: {e}")
            return None

    def cancel_appointment(self, event_id):
        if not self.service or not self.calendar_ids:
            return False
        try:
            self.service.events().delete(calendarId=self.calendar_ids[0], eventId=event_id).execute()
            
            # Rimuovi dalla cache locale
            self._recent_bookings = [
                b for b in self._recent_bookings 
                if b.get('event_id') != event_id
            ]
            
            return True
        except Exception as e:
            print(f"❌ Errore cancellazione evento: {e}")
            return False