import os
import json
from datetime import datetime
# --- INIZIO CODICE AGGIUNTO ---
from dotenv import load_dotenv
load_dotenv() # Carica le variabili dal file .env
# --- FINE CODICE AGGIUNTO ---
from db_sqlite import SQLiteClient

class BusinessManager:
    def __init__(self):
        self.db = SQLiteClient
        self.businesses = self.db.businesses
        self.conversations = self.db.conversations
    
    def add_business(self, business_data):
        try:
            business_data.update({
                "created_at": datetime.now().isoformat(), 
                "updated_at": datetime.now().isoformat()
            })
            
            # Consenti lista di calendar ID oppure stringa
            cid = business_data.get("google_calendar_id")
            if isinstance(cid, str) and "," in cid:
                business_data["google_calendar_id"] = json.dumps([c.strip() for c in cid.split(",") if c.strip()])
            elif isinstance(cid, list):
                business_data["google_calendar_id"] = json.dumps(cid)
            
            # Converti dizionari in JSON strings
            if isinstance(business_data.get("opening_hours"), dict):
                business_data["opening_hours"] = json.dumps(business_data["opening_hours"])
            if isinstance(business_data.get("booking_hours"), dict):
                business_data["booking_hours"] = json.dumps(business_data["booking_hours"])
            if isinstance(business_data.get("services"), list):
                business_data["services"] = json.dumps(business_data["services"])
                
            result = self.businesses.insert_one(business_data)
            print(f"✅ Business aggiunto con ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            print(f"❌ Errore nell'aggiungere business: {e}")
            return None
    
    def update_business(self, twilio_number, updates):
        try:
            updates["updated_at"] = datetime.now().isoformat()
            
            # Gestisci calendar_id e altri campi JSON
            for field in ["google_calendar_id", "opening_hours", "booking_hours", "services"]:
                value = updates.get(field)
                if value and isinstance(value, (list, dict)):
                    updates[field] = json.dumps(value)
            
            self.businesses.update_one(
                {"twilio_phone_number": twilio_number}, 
                {"$set": updates}
            )
            print(f"✅ Business aggiornato per numero: {twilio_number}")
            return True
        except Exception as e:
            print(f"❌ Errore nell'aggiornare business: {e}")
            return False
    
    def get_business(self, twilio_number):
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if business:
                # Decodifica campi JSON per una facile lettura
                for field in ["google_calendar_id", "opening_hours", "booking_hours", "services"]:
                    value = business.get(field)
                    if value and isinstance(value, str):
                        try:
                            business[field] = json.loads(value)
                        except json.JSONDecodeError:
                            pass # Lascia il valore come stringa se non è JSON valido
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
        print("3. Aggiorna business")
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
            business_data["business_type"] = input("Tipo business: ")
            business_data["address"] = input("Indirizzo: ")
            business_data["google_calendar_id"] = input("ID Google Calendar: ")
            
            # --- NUOVA GESTIONE ORARI PRENOTAZIONE ---
            print("\n🕒 Orari di prenotazione (espressi in ore, formato 24h)")
            start_h = input("Ora di inizio (es: 9): ")
            end_h = input("Ora di fine (es: 18): ")
            business_data["booking_hours"] = f"{start_h}-{end_h}"
            
            # --- NUOVA GESTIONE SERVIZI ---
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
                # Usa default=str per gestire ObjectId e altri tipi non serializzabili
                print(json.dumps(business, indent=2, ensure_ascii=False, default=str))
            else:
                print("Business non trovato.")
                
        elif choice == "3":
            print("\n✏️ AGGIORNA BUSINESS")
            twilio_number = input("Numero Twilio da aggiornare: ")
            if not manager.get_business(twilio_number):
                print("Business non trovato.")
                continue
            
            field = input("Campo da aggiornare (es: business_name, services): ").strip()
            
            if field == "services":
                print("\n✂️ Inserisci la nuova lista di servizi (la vecchia verrà sovrascritta)")
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
                manager.update_business(twilio_number, {"services": services})
            else:
                value = input("Nuovo valore: ")
                manager.update_business(twilio_number, {field: value})

if __name__ == "__main__":
    main()