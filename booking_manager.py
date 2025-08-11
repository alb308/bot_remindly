import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from thefuzz import fuzz

class BookingManager:
    def __init__(self, db_client):
        self.db = db_client
        self.bookings_collection = self.db.bookings
        self.pending_bookings = self.db.pending_bookings

    def extract_booking_intent(self, message: str) -> Dict:
        message_lower = message.lower()
        
        booking_keywords = [
            'prenotare', 'prenoto', 'appuntamento', 'prenotazione',
            'disponibilità', 'libero', 'orario', 'fissare'
        ]
        
        cancel_keywords = [
            'cancellare', 'cancello', 'disdire', 'annullare', 'rimandare'
        ]
        
        intent = None
        # Controlla se una delle parole chiave ha un'alta somiglianza parziale con il messaggio
        if any(fuzz.partial_ratio(k, message_lower) > 90 for k in booking_keywords):
            intent = 'book'
        elif any(fuzz.partial_ratio(k, message_lower) > 90 for k in cancel_keywords):
            intent = 'cancel'

        # ... il resto del file rimane identico ...
        date_patterns = [r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})',r'(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)',r'(oggi|domani|dopodomani)',r'(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)',r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',r'(today|tomorrow)']
        extracted_date = None
        for pattern in date_patterns:
            m = re.search(pattern, message_lower)
            if m:
                extracted_date = m.group(0)
                break
        time_patterns = [r'(\d{1,2})[:\.](\d{2})',r'alle\s+(\d{1,2})',r'at\s+(\d{1,2})',r'(\d{1,2})\s*(del\s+)?(mattino|pomeriggio|sera)',r'(\d{1,2})\s*(am|pm)',]
        extracted_time = None
        for pattern in time_patterns:
            m = re.search(pattern, message_lower)
            if m:
                extracted_time = m.group(0)
                break
        service_keywords = {'taglio': ['taglio', 'capelli', 'parrucchiere', 'haircut'],'consulenza': ['consulenza', 'visita', 'controllo', 'consultation'],'trattamento': ['trattamento', 'massaggio', 'treatment'],'pulizia': ['pulizia', 'cleaning', 'igiene'],'checkup': ['checkup', 'check-up', 'controllo generale']}
        extracted_service = None
        for service, keywords in service_keywords.items():
            if any(k in message_lower for k in keywords):
                extracted_service = service
                break
        return {'intent': intent,'date': extracted_date,'time': extracted_time,'service': extracted_service,'raw_message': message}

    def parse_datetime(self, date_str: str, time_str: str = None) -> Optional[datetime]:
        now = datetime.now()
        if date_str:
            date_lower = date_str.lower()
            if date_lower in ['oggi', 'today']:
                target_date = now.date()
            elif date_lower in ['domani', 'tomorrow']:
                target_date = (now + timedelta(days=1)).date()
            elif date_lower in ['dopodomani', 'day after tomorrow']:
                target_date = (now + timedelta(days=2)).date()
            else:
                try:
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                        try:
                            target_date = datetime.strptime(date_str, fmt).date()
                            break
                        except: continue
                    else: return None
                except: return None
        else:
            target_date = now.date()
        if time_str:
            time_lower = time_str.lower()
            numbers = re.findall(r'\d+', time_str)
            if numbers:
                hour = int(numbers[0])
                minute = int(numbers[1]) if len(numbers) > 1 else 0
                if 'pm' in time_lower or 'pomeriggio' in time_lower:
                    if hour < 12: hour += 12
                elif 'sera' in time_lower and hour < 18:
                    hour += 12
                try:
                    return datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
                except: return None
        return datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=0))