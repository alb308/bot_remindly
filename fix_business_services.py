import json
import os
from datetime import datetime
from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# Carica variabili d'ambiente
load_dotenv()

# Connessione MongoDB
def get_db_connection():
    uri = os.getenv("MONGO_URI")
    if not uri:
        raise Exception("ERRORE: La variabile MONGO_URI non è impostata nel file .env")
    
    try:
        server_api = ServerApi('1')
        client = MongoClient(uri, server_api=server_api)
        client.admin.command('ping')
        print("Connessione a MongoDB stabilita con successo!")
        return client.remindly
    except Exception as e:
        raise Exception(f"Impossibile connettersi a MongoDB: {e}")

def fix_business_services():
    db = get_db_connection()
    
    # Il tuo business ID dall'errore
    business_id = ObjectId('689907c6edf0f675c34a5eee')
    
    # Servizi per un salone (modifica secondo le tue esigenze)
    services = [
        {"name": "taglio", "duration": 30},
        {"name": "taglio e piega", "duration": 45},
        {"name": "colore", "duration": 90},
        {"name": "taglio uomo", "duration": 20},
        {"name": "barba", "duration": 15},
        {"name": "shampoo e piega", "duration": 35}
    ]
    
    try:
        # Prima verifica se il business esiste
        business = db.businesses.find_one({"_id": business_id})
        if not business:
            print(f"Business con ID {business_id} non trovato!")
            return
        
        print(f"Business trovato: {business.get('business_name', 'N/A')}")
        print(f"Servizi attuali: {business.get('services', 'N/A')}")
        
        # Aggiorna il business con i servizi corretti
        result = db.businesses.update_one(
            {"_id": business_id},
            {
                "$set": {
                    "services": json.dumps(services),
                    "booking_hours": "9-20",  # Orario 9:00-20:00
                    "opening_hours": "Lun-Sab 9:00-20:00",
                    "updated_at": datetime.now().isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            print("\nBusiness aggiornato con successo!")
            
            # Verifica il risultato
            updated_business = db.businesses.find_one({"_id": business_id})
            print(f"\nDettagli aggiornati:")
            print(f"Nome: {updated_business.get('business_name')}")
            print(f"Servizi: {updated_business.get('services')}")
            print(f"Orari prenotazione: {updated_business.get('booking_hours')}")
            print(f"Orari apertura: {updated_business.get('opening_hours')}")
            
            # Test parsing servizi
            services_str = updated_business.get('services')
            try:
                parsed_services = json.loads(services_str)
                print(f"\nTest parsing servizi: OK")
                for service in parsed_services:
                    print(f"  - {service['name']} ({service['duration']} min)")
            except Exception as e:
                print(f"Test parsing servizi: ERRORE - {e}")
                
        else:
            print("Nessuna modifica effettuata. Verifica l'ID del business.")
            
    except Exception as e:
        print(f"Errore durante l'aggiornamento: {e}")

def list_all_businesses():
    """Lista tutti i business per verificare gli ID"""
    db = get_db_connection()
    businesses = list(db.businesses.find())
    
    print(f"Trovati {len(businesses)} business:\n")
    for i, business in enumerate(businesses, 1):
        print(f"{i}. ID: {business['_id']}")
        print(f"   Nome: {business.get('business_name', 'N/A')}")
        print(f"   Phone: {business.get('twilio_phone_number', 'N/A')}")
        print(f"   Calendar ID: {business.get('google_calendar_id', 'N/A')}")
        print(f"   Servizi: {business.get('services', 'N/A')}")
        print(f"   Orari: {business.get('booking_hours', 'N/A')}")
        print()

def fix_specific_business():
    """Permette di scegliere un business specifico da sistemare"""
    db = get_db_connection()
    businesses = list(db.businesses.find())
    
    if not businesses:
        print("Nessun business trovato nel database!")
        return
    
    print("Business disponibili:")
    for i, business in enumerate(businesses, 1):
        print(f"{i}. {business.get('business_name', 'N/A')} (ID: {business['_id']})")
    
    try:
        choice = int(input(f"\nScegli business (1-{len(businesses)}): ")) - 1
        if 0 <= choice < len(businesses):
            selected_business = businesses[choice]
            business_id = selected_business['_id']
            
            print(f"\nHai scelto: {selected_business.get('business_name', 'N/A')}")
            
            # Servizi predefiniti (modifica secondo necessità)
            services = [
                {"name": "taglio", "duration": 30},
                {"name": "taglio e piega", "duration": 45},
                {"name": "colore", "duration": 90},
                {"name": "taglio uomo", "duration": 20},
                {"name": "barba", "duration": 15}
            ]
            
            print("\nServizi che verranno configurati:")
            for service in services:
                print(f"  - {service['name']} ({service['duration']} min)")
            
            confirm = input("\nConfermi? (s/n): ").lower()
            if confirm == 's':
                # Aggiorna il business
                result = db.businesses.update_one(
                    {"_id": business_id},
                    {
                        "$set": {
                            "services": json.dumps(services),
                            "booking_hours": "9-20",
                            "opening_hours": "Lun-Sab 9:00-20:00",
                            "updated_at": datetime.now().isoformat()
                        }
                    }
                )
                
                if result.modified_count > 0:
                    print("Business aggiornato con successo!")
                else:
                    print("Nessuna modifica effettuata.")
            else:
                print("Operazione annullata.")
        else:
            print("Scelta non valida.")
    except ValueError:
        print("Input non valido.")

def main():
    print("=== FIX BUSINESS SERVICES ===\n")
    
    try:
        print("1. Lista tutti i business")
        print("2. Fix business specifico (ID hardcoded)")
        print("3. Scegli business da menu")
        print("0. Esci")
        
        choice = input("\nScegli opzione: ").strip()
        
        if choice == "0":
            print("Uscita.")
        elif choice == "1":
            list_all_businesses()
        elif choice == "2":
            fix_business_services()
        elif choice == "3":
            fix_specific_business()
        else:
            print("Scelta non valida")
            
    except KeyboardInterrupt:
        print("\nOperazione interrotta.")
    except Exception as e:
        print(f"Errore: {e}")

if __name__ == "__main__":
    main()