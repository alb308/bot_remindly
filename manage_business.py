import os
import json
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from database import db_connection

class BusinessManager:
    def __init__(self):
        self.db = db_connection
        self.businesses = self.db.businesses
        self.conversations = self.db.conversations
    
    def add_business(self, business_data):
        try:
            business_data.update({
                "created_at": datetime.now().isoformat(), 
                "updated_at": datetime.now().isoformat()
            })
            
            if isinstance(business_data.get("services"), list):
                business_data["services"] = json.dumps(business_data["services"])
                
            result = self.businesses.insert_one(business_data)
            print(f"✅ Business aggiunto con ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Errore nell'aggiungere business: {e}")
            return None
    
    def get_business(self, twilio_number):
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if business:
                services_str = business.get("services")
                if services_str and isinstance(services_str, str):
                    try: business["services"] = json.loads(services_str)
                    except json.JSONDecodeError: pass
                return business
            return None
        except Exception as e:
            print(f"❌ Errore nel recuperare business: {e}")
            return None

def main():
    manager = BusinessManager()
    
    while True:
        print("\n" + "="*50)
        print("🏢 GESTORE BUSINESS - WHATSAPP BOT")
        print("="*50)
        print("1. Aggiungi nuovo business")
        print("2. Visualizza business")
        print("0. Esci")
        
        choice = input("\nScegli un'opzione: ").strip()
        
        if choice == "0":
            print("👋 Arrivederci!")
            break
            
        elif choice == "1":
            print("\n📝 AGGIUNGI NUOVO BUSINESS")
            business_data = {}
            business_data["business_name"] = input("Nome business: ")
            business_data["twilio_phone_number"] = input("Numero Twilio (es: whatsapp:+1234567890): ")
            business_data["business_type"] = input("Tipo business (es: parrucchiere): ")
            business_data["address"] = input("Indirizzo: ")
            business_data["google_calendar_id"] = input("ID Google Calendar: ")
            
            print("\n🕒 Orari di prenotazione (espressi in ore, formato 24h)")
            start_h = input("Ora di inizio (es: 9): ")
            end_h = input("Ora di fine (es: 18): ")
            business_data["booking_hours"] = f"{start_h}-{end_h}"
            
            print("\n✂️ Servizi offerti")
            services = []
            while True:
                service_name = input(f"Nome servizio {len(services)+1} (lascia vuoto per terminare): ").strip()
                if not service_name:
                    break
                duration = input(f"Durata di '{service_name}' in minuti: ").strip()
                if service_name and duration.isdigit():
                    services.append({"name": service_name, "duration": int(duration)})
                else:
                    print("Nome o durata non validi.")
            business_data["services"] = services
            
            business_data["description"] = input("Descrizione breve del business: ")
            business_data["opening_hours"] = input("Orari di apertura testuali (es: Lun-Ven 9:00-18:00): ")
            
            manager.add_business(business_data)
            
        elif choice == "2":
            twilio_number = input("Numero Twilio del business da visualizzare: ")
            business = manager.get_business(twilio_number)
            if business:
                print(json.dumps(business, indent=2, ensure_ascii=False, default=str))
            else:
                print("Business non trovato.")

if __name__ == "__main__":
    main()