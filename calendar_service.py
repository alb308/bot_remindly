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

            body = {
                "timeMin": start_time.isoformat(),
                "timeMax": end_time.isoformat(),
                "items": [{"id": cid} for cid in self.calendar_ids]
            }
            resp = self.service.freebusy().query(body=body).execute()
            
            busy_intervals = []
            for cid in self.calendar_ids:
                busy_intervals.extend(resp.get("calendars", {}).get(cid, {}).get("busy", []))

            def overlaps(s, e, busy_list):
                for b in busy_list:
                    bs = datetime.fromisoformat(b["start"])
                    be = datetime.fromisoformat(b["end"])
                    if s < be and e > bs:
                        return True
                return False

            slots = []
            cur = start_time
            step = timedelta(minutes=30)
            dur = timedelta(minutes=duration_minutes)
            while cur + dur <= end_time:
                e = cur + dur
                if not overlaps(cur, e, busy_intervals):
                    slots.append({'start': cur.strftime('%H:%M'), 'end': e.strftime('%H:%M'), 'datetime': cur.isoformat()})
                cur += step
            return slots
        except Exception as e:
            print(f"❌ Errore slot: {e}")
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
            return created_event.get('id')
        except Exception as e:
            print(f"❌ Errore creazione evento: {e}")
            return None

    # --- NUOVA FUNZIONE ---
    def get_appointment(self, event_id):
        if not self.service:
            return None
        try:
            return self.service.events().get(calendarId=self.calendar_ids[0], eventId=event_id).execute()
        except Exception as e:
            print(f"❌ Errore nel recuperare evento {event_id}: {e}")
            return None

    # --- NUOVA FUNZIONE ---
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
            return updated_event.get('id')
        except Exception as e:
            print(f"❌ Errore aggiornamento evento: {e}")
            return None


    def cancel_appointment(self, event_id):
        if not self.service or not self.calendar_ids:
            return False
        try:
            self.service.events().delete(calendarId=self.calendar_ids[0], eventId=event_id).execute()
            return True
        except Exception as e:
            print(f"❌ Errore cancellazione evento: {e}")
            return False