import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

class BookingManager:
    def __init__(self, sqlite_db):
        """
        sqlite_db: istanza di SQLiteClient (db_sqlite.SQLiteClient)
        """
        self.db = sqlite_db
        self.bookings_collection = self.db.bookings
        self.pending_bookings = self.db.pending_bookings

    def extract_booking_intent(self, message: str) -> Dict:
        """Estrae l'intento di prenotazione dal messaggio"""
        message_lower = message.lower()
        
        # Keywords per identificare intento
        booking_keywords = [
            'prenotare', 'prenoto', 'appuntamento', 'prenotazione',
            'disponibilità', 'libero', 'orario', 'quando', 'posso venire',
            'slot', 'disponibile', 'book', 'appointment'
        ]
        
        cancel_keywords = [
            'cancellare', 'cancello', 'disdire', 'annullare', 
            'rimandare', 'cancel', 'delete'
        ]
        
        # Determina intento
        intent = None
        if any(k in message_lower for k in booking_keywords):
            intent = 'book'
        elif any(k in message_lower for k in cancel_keywords):
            intent = 'cancel'

        # Estrai data
        date_patterns = [
            r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})',
            r'(\d{1,2})\s+(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)',
            r'(oggi|domani|dopodomani)',
            r'(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)',
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            r'(today|tomorrow)'
        ]
        
        extracted_date = None
        for pattern in date_patterns:
            m = re.search(pattern, message_lower)
            if m:
                extracted_date = m.group(0)
                break

        # Estrai orario
        time_patterns = [
            r'(\d{1,2})[:\.](\d{2})',
            r'alle\s+(\d{1,2})',
            r'at\s+(\d{1,2})',
            r'(\d{1,2})\s*(del\s+)?(mattino|pomeriggio|sera)',
            r'(\d{1,2})\s*(am|pm)',
        ]
        
        extracted_time = None
        for pattern in time_patterns:
            m = re.search(pattern, message_lower)
            if m:
                extracted_time = m.group(0)
                break

        # Identifica tipo di servizio
        service_keywords = {
            'taglio': ['taglio', 'capelli', 'parrucchiere', 'haircut'],
            'consulenza': ['consulenza', 'visita', 'controllo', 'consultation'],
            'trattamento': ['trattamento', 'massaggio', 'treatment'],
            'pulizia': ['pulizia', 'cleaning', 'igiene'],
            'checkup': ['checkup', 'check-up', 'controllo generale']
        }
        
        extracted_service = None
        for service, keywords in service_keywords.items():
            if any(k in message_lower for k in keywords):
                extracted_service = service
                break

        return {
            'intent': intent,
            'date': extracted_date,
            'time': extracted_time,
            'service': extracted_service,
            'raw_message': message
        }

    def parse_datetime(self, date_str: str, time_str: str = None) -> Optional[datetime]:
        """Converte stringhe data/ora in oggetto datetime"""
        now = datetime.now()
        
        # Gestisci date relative
        if date_str:
            date_lower = date_str.lower()
            if date_lower in ['oggi', 'today']:
                target_date = now.date()
            elif date_lower in ['domani', 'tomorrow']:
                target_date = (now + timedelta(days=1)).date()
            elif date_lower in ['dopodomani', 'day after tomorrow']:
                target_date = (now + timedelta(days=2)).date()
            else:
                # Prova a parsare data assoluta
                try:
                    # Prova diversi formati
                    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                        try:
                            target_date = datetime.strptime(date_str, fmt).date()
                            break
                        except:
                            continue
                    else:
                        return None
                except:
                    return None
        else:
            target_date = now.date()

        # Gestisci orario
        if time_str:
            time_lower = time_str.lower()
            # Estrai numeri
            numbers = re.findall(r'\d+', time_str)
            if numbers:
                hour = int(numbers[0])
                minute = int(numbers[1]) if len(numbers) > 1 else 0
                
                # Aggiusta per am/pm o mattino/pomeriggio
                if 'pm' in time_lower or 'pomeriggio' in time_lower:
                    if hour < 12:
                        hour += 12
                elif 'sera' in time_lower and hour < 18:
                    hour += 12
                    
                try:
                    return datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
                except:
                    return None
        
        return datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=0))

    def create_pending_booking(self, user_id: str, business_id: int, booking_data: Dict) -> Dict:
        """Crea una prenotazione pendente"""
        try:
            pending = {
                "user_id": user_id,
                "business_id": business_id,
                "booking_data": json.dumps(booking_data),
                "status": "pending",
                "created_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(minutes=30)).isoformat()
            }
            
            result = self.pending_bookings.insert_one(pending)
            return {"success": True, "booking_id": result["inserted_id"]}
        except Exception as e:
            print(f"❌ Errore creazione prenotazione pendente: {e}")
            return {"success": False, "error": str(e)}

    def confirm_booking(self, booking_id: int, calendar_event_id: str = None) -> bool:
        """Conferma una prenotazione pendente"""
        try:
            # Trova prenotazione pendente
            pending = self.pending_bookings.find_one({"id": booking_id})
            if not pending:
                return False
            
            # Crea prenotazione confermata
            confirmed = {
                "user_id": pending["user_id"],
                "business_id": pending["business_id"],
                "booking_data": pending["booking_data"],
                "status": "confirmed",
                "calendar_event_id": calendar_event_id,
                "created_at": pending["created_at"],
                "confirmed_at": datetime.now().isoformat(),
                "cancelled_at": None
            }
            
            self.bookings_collection.insert_one(confirmed)
            
            # Rimuovi da pending
            self.pending_bookings.delete_one({"id": booking_id})
            
            return True
        except Exception as e:
            print(f"❌ Errore conferma prenotazione: {e}")
            return False

    def cancel_booking(self, user_id: str, business_id: int, booking_ref: str = None) -> Dict:
        """Cancella una prenotazione"""
        try:
            # Cerca prenotazione da cancellare
            query = {
                "user_id": user_id,
                "business_id": business_id,
                "status": "confirmed"
            }
            
            if booking_ref:
                # Se c'è un riferimento specifico, cercalo nel booking_data
                bookings = self.bookings_collection.find(query)
                for booking in bookings:
                    data = json.loads(booking.get("booking_data", "{}"))
                    if booking_ref in str(data.get("date", "")) or booking_ref in str(data.get("time", "")):
                        # Aggiorna stato
                        self.bookings_collection.update_one(
                            {"id": booking["id"]},
                            {
                                "status": "cancelled",
                                "cancelled_at": datetime.now().isoformat()
                            }
                        )
                        return {
                            "success": True, 
                            "calendar_event_id": booking.get("calendar_event_id"),
                            "booking_data": data
                        }
            else:
                # Cancella l'ultima prenotazione
                bookings = self.bookings_collection.find(query)
                if bookings:
                    latest = sorted(bookings, key=lambda x: x.get("created_at", ""), reverse=True)[0]
                    self.bookings_collection.update_one(
                        {"id": latest["id"]},
                        {
                            "status": "cancelled",
                            "cancelled_at": datetime.now().isoformat()
                        }
                    )
                    return {
                        "success": True,
                        "calendar_event_id": latest.get("calendar_event_id"),
                        "booking_data": json.loads(latest.get("booking_data", "{}"))
                    }
            
            return {"success": False, "error": "Nessuna prenotazione trovata"}
            
        except Exception as e:
            print(f"❌ Errore cancellazione: {e}")
            return {"success": False, "error": str(e)}

    def get_user_bookings(self, user_id: str, business_id: int, status: str = None) -> List[Dict]:
        """Recupera prenotazioni di un utente"""
        query = {
            "user_id": user_id,
            "business_id": business_id
        }
        
        if status:
            query["status"] = status
        
        bookings = self.bookings_collection.find(query)
        
        # Decodifica booking_data per ogni prenotazione
        result = []
        for booking in bookings:
            booking["booking_data"] = json.loads(booking.get("booking_data", "{}"))
            result.append(booking)
        
        return result

    def cleanup_expired_pending(self):
        """Rimuove prenotazioni pendenti scadute"""
        try:
            now = datetime.now().isoformat()
            expired = self.pending_bookings.find({})
            
            for pending in expired:
                if pending.get("expires_at", "") < now:
                    self.pending_bookings.delete_one({"id": pending["id"]})
                    print(f"🗑️ Rimossa prenotazione pendente scaduta: {pending['id']}")
                    
        except Exception as e:
            print(f"❌ Errore pulizia pending: {e}")