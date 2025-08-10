import os
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client as TwilioClient
from db_sqlite import SQLiteClient
import pytz
from dotenv import load_dotenv

load_dotenv()

TZ = pytz.timezone("Europe/Rome")

class ReminderScheduler:
    """
    - Reminder automatici 60 minuti prima dell'appuntamento
    - Follow-up 2 ore dopo l'orario stimato di fine
    """
    def __init__(self):
        self.db = SQLiteClient("remindly.db")
        self.twilio = TwilioClient(
            os.environ["TWILIO_ACCOUNT_SID"], 
            os.environ["TWILIO_AUTH_TOKEN"]
        )
        self.scheduler = BackgroundScheduler(timezone="Europe/Rome")

    def start(self):
        """Avvia lo scheduler con i job periodici"""
        # Pianifica job per reminder e follow-up
        self.scheduler.add_job(
            self.send_upcoming_reminders, 
            "interval", 
            minutes=5, 
            id="reminders60", 
            replace_existing=True
        )
        self.scheduler.add_job(
            self.send_followups, 
            "interval", 
            minutes=15, 
            id="followups", 
            replace_existing=True
        )
        self.scheduler.start()
        print("⏰ ReminderScheduler avviato")

    def stop(self):
        """Ferma lo scheduler"""
        self.scheduler.shutdown()
        print("⏰ ReminderScheduler fermato")

    def send_whatsapp(self, to: str, body: str, from_number: str):
        """Invia messaggio WhatsApp via Twilio"""
        try:
            self.twilio.messages.create(
                from_=from_number, 
                to=to, 
                body=body
            )
            print(f"📤 Messaggio inviato a {to}")
            return True
        except Exception as e:
            print(f"❌ Errore invio WhatsApp a {to}: {e}")
            return False

    def send_upcoming_reminders(self):
        """Invia reminder 60 minuti prima dell'appuntamento"""
        try:
            now = datetime.now(TZ)
            target_from = (now + timedelta(minutes=60)).replace(second=0, microsecond=0)
            target_to = target_from + timedelta(minutes=5)
            
            print(f"🔍 Controllo reminder per appuntamenti tra {target_from.strftime('%H:%M')} e {target_to.strftime('%H:%M')}")

            # Cerca appuntamenti confermati
            bookings = self.db.bookings.find({"status": "confirmed"})
            
            for booking in bookings:
                try:
                    # Salta se già inviato reminder
                    if booking.get("reminder_sent") == "true":
                        continue
                    
                    # Decodifica booking_data da JSON
                    booking_data = json.loads(booking.get("booking_data", "{}"))
                    
                    if not booking_data.get("date") or not booking_data.get("time"):
                        continue
                    
                    date = booking_data["date"]
                    time = booking_data["time"]
                    
                    # Parsing data e ora
                    try:
                        # Prova formato con timezone aware
                        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                        start_dt = TZ.localize(start_dt)
                    except ValueError:
                        # Prova altri formati
                        try:
                            start_dt = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
                            start_dt = TZ.localize(start_dt)
                        except:
                            print(f"⚠️ Formato data/ora non riconosciuto: {date} {time}")
                            continue
                    
                    # Verifica se è nell'intervallo di tempo per il reminder
                    if target_from <= start_dt < target_to:
                        # Recupera informazioni business
                        business_id = booking.get("business_id")
                        if not business_id:
                            continue
                        
                        business = self.db.businesses.find_one({"id": business_id})
                        if not business:
                            continue
                        
                        from_num = business.get("twilio_phone_number")
                        to = booking_data.get("customer_phone")
                        
                        if not from_num or not to:
                            print(f"⚠️ Mancano numeri telefono per booking {booking['id']}")
                            continue
                        
                        # Prepara messaggio
                        customer_name = booking_data.get("customer_name", "Cliente")
                        service_type = booking_data.get("service_type", "Appuntamento")
                        business_name = business.get("business_name", "noi")
                        
                        message = f"📅 Ciao {customer_name}! Ti ricordiamo il tuo {service_type} presso {business_name} oggi alle {time}.\n"
                        message += f"📍 {business.get('address', '')}\n"
                        message += "Se devi cancellare, rispondi 'CANCELLA'."
                        
                        # Invia messaggio
                        if self.send_whatsapp(to, message, from_num):
                            # Segna reminder come inviato
                            self.db.bookings.update_one(
                                {"id": booking["id"]},
                                {"reminder_sent": "true"}
                            )
                            print(f"✅ Reminder inviato per booking {booking['id']}")
                            
                except Exception as e:
                    print(f"❌ Errore processamento booking {booking.get('id')}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Errore generale in send_upcoming_reminders: {e}")

    def send_followups(self):
        """Invia follow-up 2 ore dopo la fine stimata dell'appuntamento"""
        try:
            now = datetime.now(TZ)
            window_start = now - timedelta(hours=2, minutes=15)
            window_end = now - timedelta(hours=2)
            
            print(f"🔍 Controllo follow-up per appuntamenti finiti tra {window_start.strftime('%H:%M')} e {window_end.strftime('%H:%M')}")
            
            bookings = self.db.bookings.find({"status": "confirmed"})
            
            for booking in bookings:
                try:
                    # Salta se già inviato follow-up
                    if booking.get("followup_sent") == "true":
                        continue
                    
                    # Decodifica booking_data
                    booking_data = json.loads(booking.get("booking_data", "{}"))
                    
                    date = booking_data.get("date")
                    time = booking_data.get("time")
                    duration = booking_data.get("duration", 60)
                    
                    if not date or not time:
                        continue
                    
                    # Parsing data e ora
                    try:
                        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
                        start_dt = TZ.localize(start_dt)
                        end_dt = start_dt + timedelta(minutes=duration)
                    except ValueError:
                        try:
                            start_dt = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
                            start_dt = TZ.localize(start_dt)
                            end_dt = start_dt + timedelta(minutes=duration)
                        except:
                            print(f"⚠️ Formato data/ora non riconosciuto: {date} {time}")
                            continue
                    
                    # Verifica se l'appuntamento è nella finestra per follow-up
                    if window_start <= end_dt <= window_end:
                        # Recupera informazioni business
                        business_id = booking.get("business_id")
                        if not business_id:
                            continue
                        
                        business = self.db.businesses.find_one({"id": business_id})
                        if not business:
                            continue
                        
                        from_num = business.get("twilio_phone_number")
                        to = booking_data.get("customer_phone")
                        
                        if not from_num or not to:
                            print(f"⚠️ Mancano numeri telefono per booking {booking['id']}")
                            continue
                        
                        # Prepara messaggio follow-up
                        customer_name = booking_data.get("customer_name", "")
                        business_name = business.get("business_name", "noi")
                        
                        if customer_name:
                            message = f"👋 Ciao {customer_name}! "
                        else:
                            message = "👋 Ciao! "
                            
                        message += f"Grazie per la tua visita presso {business_name}!\n"
                        message += "Come è andata? Rispondi con un voto da 1 a 5 ⭐\n"
                        message += "Il tuo feedback è importante per noi!"
                        
                        # Invia messaggio
                        if self.send_whatsapp(to, message, from_num):
                            # Segna follow-up come inviato
                            self.db.bookings.update_one(
                                {"id": booking["id"]},
                                {"followup_sent": "true"}
                            )
                            print(f"✅ Follow-up inviato per booking {booking['id']}")
                            
                except Exception as e:
                    print(f"❌ Errore processamento booking {booking.get('id')}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Errore generale in send_followups: {e}")

    def test_immediate_reminder(self):
        """Metodo di test per inviare un reminder immediato"""
        print("🧪 Test reminder immediato...")
        
        # Crea un appuntamento fittizio per test
        test_booking_data = {
            "date": datetime.now(TZ).strftime("%Y-%m-%d"),
            "time": (datetime.now(TZ) + timedelta(minutes=61)).strftime("%H:%M"),
            "customer_name": "Test Cliente",
            "customer_phone": "whatsapp:+393333333333",  # Numero di test
            "service_type": "Test Service",
            "duration": 60
        }
        
        # Trova un business di test
        businesses = self.db.businesses.find()
        if not businesses:
            print("❌ Nessun business trovato per il test")
            return
            
        business = businesses[0]
        print(f"📋 Uso business: {business.get('business_name')}")
        
        # Crea booking di test
        test_booking = {
            "user_id": test_booking_data["customer_phone"],
            "business_id": business["id"],
            "booking_data": json.dumps(test_booking_data),
            "status": "confirmed",
            "created_at": datetime.now().isoformat(),
            "confirmed_at": datetime.now().isoformat()
        }
        
        result = self.db.bookings.insert_one(test_booking)
        print(f"✅ Booking di test creato con ID: {result['inserted_id']}")
        
        # Forza invio reminder
        self.send_upcoming_reminders()
        
        print("🧪 Test completato")

# Singleton per lo scheduler
scheduler_singleton = None

def get_scheduler():
    """Ottiene l'istanza singleton dello scheduler"""
    global scheduler_singleton
    if scheduler_singleton is None:
        scheduler_singleton = ReminderScheduler()
    return scheduler_singleton

def main():
    """Main function per test e esecuzione standalone"""
    print("🚀 Avvio ReminderScheduler...")
    
    scheduler = get_scheduler()
    
    # Chiedi se eseguire test
    test_mode = input("Vuoi eseguire un test immediato? (s/n): ").lower() == 's'
    
    if test_mode:
        scheduler.test_immediate_reminder()
    else:
        scheduler.start()
        
        try:
            print("⏰ Scheduler in esecuzione. Premi Ctrl+C per fermare.")
            # Mantieni lo scheduler in esecuzione
            import time
            while True:
                time.sleep(60)
                # Status update ogni minuto
                now = datetime.now(TZ)
                print(f"⏰ [{now.strftime('%H:%M:%S')}] Scheduler attivo...")
                
        except KeyboardInterrupt:
            print("\n⏹️ Arresto scheduler...")
            scheduler.stop()
            print("✅ Scheduler fermato correttamente")

if __name__ == "__main__":
    main()