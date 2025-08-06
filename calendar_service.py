import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pytz

class CalendarService:
    def __init__(self, calendar_id=None, service_account_key=None):
        """
        Inizializza il servizio Google Calendar
        
        Args:
            calendar_id: ID del calendario Google
            service_account_key: JSON del service account o path al file
        """
        self.calendar_id = calendar_id
        self.service = None
        self.timezone = pytz.timezone('Europe/Rome')  # Timezone italiana
        
        if service_account_key:
            self._init_service_account(service_account_key)
    
    def _init_service_account(self, service_account_key):
        """Inizializza usando Service Account"""
        try:
            # Se è una stringa JSON, parsala
            if isinstance(service_account_key, str):
                if service_account_key.startswith('{'):
                    # JSON string
                    creds_info = json.loads(service_account_key)
                else:
                    # File path
                    with open(service_account_key, 'r') as f:
                        creds_info = json.load(f)
            else:
                creds_info = service_account_key
            
            credentials = ServiceCredentials.from_service_account_info(
                creds_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            
            self.service = build('calendar', 'v3', credentials=credentials)
            print("✅ Servizio Google Calendar inizializzato con Service Account")
            
        except Exception as e:
            print(f"❌ Errore nell'inizializzare Google Calendar: {e}")
            self.service = None
    
    def get_available_slots(self, date, duration_minutes=60, start_hour=9, end_hour=18):
        """
        Trova slot disponibili per una data specifica
        
        Args:
            date: Data in formato YYYY-MM-DD
            duration_minutes: Durata appuntamento in minuti
            start_hour: Ora inizio ricerca (24h format)
            end_hour: Ora fine ricerca (24h format)
            
        Returns:
            Lista di slot disponibili
        """
        if not self.service or not self.calendar_id:
            return []
        
        try:
            # Parse della data
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            # Crea range temporale per la giornata
            start_time = self.timezone.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=start_hour))
            )
            end_time = self.timezone.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=end_hour))
            )
            
            # Ottieni eventi esistenti
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Genera slot possibili ogni 30 minuti
            available_slots = []
            current_time = start_time
            slot_duration = timedelta(minutes=duration_minutes)
            
            while current_time + slot_duration <= end_time:
                slot_end = current_time + slot_duration
                
                # Controlla se lo slot è libero
                is_free = True
                for event in events:
                    event_start = datetime.fromisoformat(
                        event['start'].get('dateTime', event['start'].get('date'))
                    )
                    event_end = datetime.fromisoformat(
                        event['end'].get('dateTime', event['end'].get('date'))
                    )
                    
                    # Se c'è sovrapposizione, lo slot non è disponibile
                    if (current_time < event_end and slot_end > event_start):
                        is_free = False
                        break
                
                if is_free:
                    available_slots.append({
                        'start': current_time.strftime('%H:%M'),
                        'end': slot_end.strftime('%H:%M'),
                        'datetime': current_time.isoformat()
                    })
                
                current_time += timedelta(minutes=30)  # Slot ogni 30 minuti
            
            return available_slots
            
        except Exception as e:
            print(f"❌ Errore nel recuperare slot disponibili: {e}")
            return []
    
    def create_appointment(self, date, start_time, duration_minutes, customer_name, 
                          customer_phone, service_type="Appuntamento", notes=""):
        """
        Crea un nuovo appuntamento
        
        Args:
            date: Data in formato YYYY-MM-DD
            start_time: Ora in formato HH:MM
            duration_minutes: Durata in minuti
            customer_name: Nome cliente
            customer_phone: Telefono cliente
            service_type: Tipo servizio
            notes: Note aggiuntive
            
        Returns:
            ID dell'evento creato o None se errore
        """
        if not self.service or not self.calendar_id:
            return None
        
        try:
            # Parse datetime
            start_datetime = datetime.strptime(f"{date} {start_time}", '%Y-%m-%d %H:%M')
            start_datetime = self.timezone.localize(start_datetime)
            end_datetime = start_datetime + timedelta(minutes=duration_minutes)
            
            # Crea evento
            event = {
                'summary': f"{service_type} - {customer_name}",
                'description': f"""
Cliente: {customer_name}
Telefono: {customer_phone}
Servizio: {service_type}
Note: {notes}
                """.strip(),
                'start': {
                    'dateTime': start_datetime.isoformat(),
                    'timeZone': 'Europe/Rome',
                },
                'end': {
                    'dateTime': end_datetime.isoformat(),
                    'timeZone': 'Europe/Rome',
                },
                'attendees': [
                    {'email': f"{customer_phone}@whatsapp.local", 'displayName': customer_name}
                ],
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 60},  # Promemoria 1 ora prima
                        {'method': 'popup', 'minutes': 15},  # Promemoria 15 min prima
                    ],
                },
            }
            
            created_event = self.service.events().insert(
                calendarId=self.calendar_id, 
                body=event
            ).execute()
            
            print(f"✅ Appuntamento creato: {created_event.get('id')}")
            return created_event.get('id')
            
        except Exception as e:
            print(f"❌ Errore nella creazione appuntamento: {e}")
            return None
    
    def cancel_appointment(self, event_id):
        """Cancella un appuntamento"""
        if not self.service or not self.calendar_id:
            return False
        
        try:
            self.service.events().delete(
                calendarId=self.calendar_id, 
                eventId=event_id
            ).execute()
            
            print(f"✅ Appuntamento cancellato: {event_id}")
            return True
            
        except Exception as e:
            print(f"❌ Errore nella cancellazione: {e}")
            return False
    
    def get_upcoming_appointments(self, days_ahead=7):
        """Ottieni prossimi appuntamenti"""
        if not self.service or not self.calendar_id:
            return []
        
        try:
            now = datetime.now(self.timezone)
            future = now + timedelta(days=days_ahead)
            
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat(),
                timeMax=future.isoformat(),
                maxResults=20,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            appointments = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                appointments.append({
                    'id': event['id'],
                    'title': event.get('summary', 'Senza titolo'),
                    'start': start,
                    'description': event.get('description', ''),
                })
            
            return appointments
            
        except Exception as e:
            print(f"❌ Errore nel recuperare appuntamenti: {e}")
            return []

def test_calendar_service():
    """Funzione di test per il servizio calendar"""
    # Sostituisci con i tuoi dati reali
    calendar_id = "your-calendar-id@group.calendar.google.com"
    service_account_file = "path/to/service-account.json"
    
    calendar = CalendarService(calendar_id, service_account_file)
    
    # Test: trova slot disponibili per domani
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    slots = calendar.get_available_slots(tomorrow)
    
    print(f"Slot disponibili per {tomorrow}:")
    for slot in slots[:5]:  # Prime 5 slot
        print(f"  {slot['start']} - {slot['end']}")
    
    # Test: crea appuntamento (commentato per sicurezza)
    # event_id = calendar.create_appointment(
    #     date=tomorrow,
    #     start_time="10:00",
    #     duration_minutes=60,
    #     customer_name="Mario Rossi",
    #     customer_phone="+39123456789",
    #     service_type="Consulenza",
    #     notes="Primo appuntamento via WhatsApp"
    # )

if __name__ == "__main__":
    test_calendar_service()