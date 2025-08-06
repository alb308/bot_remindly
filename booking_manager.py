import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from calendar_service import CalendarService

class BookingManager:
    def __init__(self, mongo_db):
        """
        Gestore delle prenotazioni per WhatsApp Bot
        
        Args:
            mongo_db: Database MongoDB
        """
        self.db = mongo_db
        self.bookings_collection = self.db.bookings
        self.pending_bookings = self.db.pending_bookings
        
    def extract_booking_intent(self, message: str) -> Dict:
        """
        Analizza il messaggio per identificare intenti di prenotazione
        
        Returns:
            Dict con intent, date, time, service_type estratti
        """
        message_lower = message.lower()
        
        # Keywords per identificare intent di prenotazione
        booking_keywords = [
            'prenotare', 'prenoto', 'appuntamento', 'prenotazione',
            'disponibilità', 'libero', 'orario', 'quando', 'posso venire',
            'slot', 'disponibile'
        ]
        
        # Keywords per cancellazione
        cancel_keywords = [
            'cancellare', 'cancello', 'disdire', 'annullare', 'rimandare'
        ]
        
        intent = None
        if any(keyword in message_lower for keyword in booking_keywords):
            intent = 'book'
        elif any(keyword in message_lower for keyword in cancel_keywords):
            intent = 'cancel'
        
        # Estrai data (pattern comuni italiani)
        date_patterns = [
            r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})',  # 12/03/2024
            r'(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)',
            r'(oggi|domani|dopodomani)',
            r'(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)'
        ]
        
        extracted_date = None
        for pattern in date_patterns:
            match = re.search(pattern, message_lower)
            if match:
                extracted_date = match.group(0)
                break
        
        # Estrai ora
        time_patterns = [
            r'(\d{1,2})[:\.](\d{2})',  # 14:30, 14.30
            r'alle\s+(\d{1,2})',       # alle 14
            r'(\d{1,2})\s*(del\s+)?(mattino|pomeriggio|sera)',
        ]
        
        extracted_time = None
        for pattern in time_patterns:
            match = re.search(pattern, message_lower)
            if match:
                extracted_time = match.group(0)
                break
        
        # Estrai tipo servizio (personalizzabile per business)
        service_keywords = {
            'taglio': ['taglio', 'capelli', 'parrucchiere'],
            'consulenza': ['consulenza', 'visita', 'controllo'],
            'trattamento': ['trattamento', 'massaggio', 'estetica'],
            'appuntamento generico': ['appuntamento', 'incontro']
        }
        
        service_type = None
        for service, keywords in service_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                service_type = service
                break
        
        return {
            'intent': intent,
            'date': extracted_date,
            'time': extracted_time,
            'service_type': service_type or 'appuntamento generico',
            'confidence': 0.8 if intent else 0.0
        }
    
    def normalize_date(self, date_str: str) -> Optional[str]:
        """
        Converte date in formato naturale a YYYY-MM-DD
        """
        if not date_str:
            return None
        
        date_str = date_str.lower().strip()
        today = datetime.now().date()
        
        # Gestione date relative
        if date_str == 'oggi':
            return today.strftime('%Y-%m-%d')
        elif date_str == 'domani':
            return (today + timedelta(days=1)).strftime('%Y-%m-%d')
        elif date_str == 'dopodomani':
            return (today + timedelta(days=2)).strftime('%Y-%m-%d')
        
        # Giorni della settimana
        days_map = {
            'lunedì': 0, 'martedì': 1, 'mercoledì': 2, 'giovedì': 3,
            'venerdì': 4, 'sabato': 5, 'domenica': 6
        }
        
        if date_str in days_map:
            target_weekday = days_map[date_str]
            current_weekday = today.weekday()
            days_ahead = (target_weekday - current_weekday) % 7
            if days_ahead == 0:  # Se è oggi, prendi la prossima settimana
                days_ahead = 7
            target_date = today + timedelta(days=days_ahead)
            return target_date.strftime('%Y-%m-%d')
        
        # Pattern DD/MM/YYYY o DD-MM-YYYY
        date_match = re.match(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})', date_str)
        if date_match:
            day, month, year = date_match.groups()
            if len(year) == 2:
                year = '20' + year
            try:
                parsed_date = datetime(int(year), int(month), int(day)).date()
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                return None
        
        return None
    
    def normalize_time(self, time_str: str) -> Optional[str]:
        """
        Converte orari in formato naturale a HH:MM
        """
        if not time_str:
            return None
        
        time_str = time_str.lower().strip()
        
        # Pattern HH:MM o HH.MM
        time_match = re.search(r'(\d{1,2})[:\.](\d{2})', time_str)
        if time_match:
            hour, minute = time_match.groups()
            return f"{int(hour):02d}:{minute}"
        
        # Pattern "alle XX"
        hour_match = re.search(r'alle\s+(\d{1,2})', time_str)
        if hour_match:
            hour = int(hour_match.group(1))
            return f"{hour:02d}:00"
        
        # Pattern "XX del mattino/pomeriggio/sera"
        period_match = re.search(r'(\d{1,2})\s*(del\s+)?(mattino|pomeriggio|sera)', time_str)
        if period_match:
            hour = int(period_match.group(1))
            period = period_match.group(3)
            
            if period == 'mattino' and hour <= 12:
                return f"{hour:02d}:00"
            elif period == 'pomeriggio' and hour <= 12:
                return f"{hour + 12:02d}:00"
            elif period == 'sera' and hour <= 12:
                return f"{hour + 12:02d}:00"
        
        return None
    
    def create_pending_booking(self, user_id: str, business_id: str, 
                             booking_data: Dict) -> str:
        """
        Crea una prenotazione in attesa di conferma
        """
        pending_booking = {
            'user_id': user_id,
            'business_id': business_id,
            'status': 'pending_confirmation',
            'booking_data': booking_data,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=15)).isoformat()
        }
        
        result = self.pending_bookings.insert_one(pending_booking)
        return str(result.inserted_id)
    
    def confirm_booking(self, pending_id: str, calendar_service: CalendarService) -> Tuple[bool, str]:
        """
        Conferma una prenotazione pendente e la crea nel calendario
        """
        try:
            pending = self.pending_bookings.find_one({'_id': pending_id})
            if not pending:
                return False, "Prenotazione non trovata"
            
            if datetime.fromisoformat(pending['expires_at']) < datetime.now():
                return False, "Prenotazione scaduta"
            
            booking_data = pending['booking_data']
            
            # Crea evento nel calendario
            event_id = calendar_service.create_appointment(
                date=booking_data['date'],
                start_time=booking_data['time'],
                duration_minutes=booking_data.get('duration', 60),
                customer_name=booking_data['customer_name'],
                customer_phone=booking_data['customer_phone'],
                service_type=booking_data['service_type'],
                notes=booking_data.get('notes', '')
            )
            
            if not event_id:
                return False, "Errore nella creazione dell'appuntamento"
            
            # Salva prenotazione confermata
            confirmed_booking = {
                **pending,
                'status': 'confirmed',
                'calendar_event_id': event_id,
                'confirmed_at': datetime.now().isoformat()
            }
            
            self.bookings_collection.insert_one(confirmed_booking)
            self.pending_bookings.delete_one({'_id': pending_id})
            
            return True, event_id
            
        except Exception as e:
            return False, f"Errore: {str(e)}"
    
    def get_user_bookings(self, user_id: str, business_id: str) -> List[Dict]:
        """
        Recupera prenotazioni dell'utente
        """
        try:
            bookings = list(self.bookings_collection.find({
                'user_id': user_id,
                'business_id': business_id,
                'status': 'confirmed'
            }).sort('booking_data.date', 1))
            
            return bookings
        except Exception as e:
            print(f"Errore nel recuperare prenotazioni: {e}")
            return []
    
    def cancel_booking(self, booking_id: str, calendar_service: CalendarService) -> Tuple[bool, str]:
        """
        Cancella una prenotazione
        """
        try:
            booking = self.bookings_collection.find_one({'_id': booking_id})
            if not booking:
                return False, "Prenotazione non trovata"
            
            # Cancella dal calendario
            if 'calendar_event_id' in booking:
                calendar_service.cancel_appointment(booking['calendar_event_id'])
            
            # Aggiorna status
            self.bookings_collection.update_one(
                {'_id': booking_id},
                {
                    '$set': {
                        'status': 'cancelled',
                        'cancelled_at': datetime.now().isoformat()
                    }
                }
            )
            
            return True, "Prenotazione cancellata con successo"
            
        except Exception as e:
            return False, f"Errore nella cancellazione: {str(e)}"

# Funzioni helper per messaggi WhatsApp
def format_available_slots(slots: List[Dict], date: str) -> str:
    """Formatta slot disponibili per messaggio WhatsApp"""
    if not slots:
        return f"Mi dispiace, non ci sono slot disponibili per il {date}."
    
    message = f"🗓️ *Orari disponibili per {date}:*\n\n"
    for i, slot in enumerate(slots[:8], 1):  # Max 8 slot
        message += f"{i}. {slot['start']} - {slot['end']}\n"
    
    message += "\n💬 Rispondi con il numero dello slot che preferisci!"
    return message

def format_booking_confirmation(booking_data: Dict) -> str:
    """Formatta messaggio di conferma prenotazione"""
    return f"""
✅ *Conferma Prenotazione*

📅 Data: {booking_data['date']}
🕐 Orario: {booking_data['time']}
👤 Nome: {booking_data['customer_name']}
🔧 Servizio: {booking_data['service_type']}

Confermi questa prenotazione? 
Rispondi *SÌ* per confermare o *NO* per annullare.
    """.strip()

def format_booking_success(booking_data: Dict) -> str:
    """Formatta messaggio di prenotazione confermata"""
    return f"""
🎉 *Prenotazione Confermata!*

📅 {booking_data['date']} alle {booking_data['time']}
🔧 {booking_data['service_type']}

Ti aspettiamo! Riceverai un promemoria automatico.

Per modifiche o cancellazioni, contattaci direttamente.
    """.strip()