import json
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials as ServiceCredentials
from googleapiclient.discovery import build
import pytz

class CalendarService:
    """
    Supporta uno o più calendar_id (lista o stringa).
    FreeBusy per calcolare disponibilità. Crea/cancella eventi.
    """
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
            if isinstance(service_account_key, str) and service_account_key.startswith('{'):
                creds_info = json.loads(service_account_key)
            elif isinstance(service_account_key, str):
                with open(service_account_key, 'r') as f:
                    creds_info = json.load(f)
            else:
                creds_info = service_account_key
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
            from datetime import time as dtime
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            start_time = self.timezone.localize(datetime.combine(target_date, dtime(hour=start_hour)))
            end_time = self.timezone.localize(datetime.combine(target_date, dtime(hour=end_hour)))

            body = {
                "timeMin": start_time.isoformat(),
                "timeMax": end_time.isoformat(),
                "items": [{"id": cid} for cid in self.calendar_ids]
            }
            resp = self.service.freebusy().query(body=body).execute()
            busy_intervals = []
            for cid in self.calendar_ids:
                busy_intervals += resp.get("calendars", {}).get(cid, {}).get("busy", [])

            def overlaps(s, e):
                for b in busy_intervals:
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
                if not overlaps(cur, e):
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
                'attendees': [{'email': f"{customer_phone}@whatsapp.local", 'displayName': customer_name}],
                'reminders': {'useDefault': False, 'overrides': [{'method':'popup','minutes':60},{'method':'popup','minutes':15}]}
            }
            created_event = self.service.events().insert(calendarId=self.calendar_ids[0], body=event).execute()
            return created_event.get('id')
        except Exception as e:
            print(f"❌ Errore creazione evento: {e}")
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
