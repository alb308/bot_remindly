import os
import json
from datetime import datetime
from db_sqlite import SQLiteClient

class BusinessManager:
    def __init__(self):
        self.db = SQLiteClient("remindly.db")
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
                
            result = self.businesses.insert_one(business_data)
            print(f"✅ Business aggiunto con ID: {result['inserted_id']}")
            return result['inserted_id']
        except Exception as e:
            print(f"❌ Errore nell'aggiungere business: {e}")
            return None
    
    def update_business(self, twilio_number, updates):
        try:
            updates["updated_at"] = datetime.now().isoformat()
            
            # Gestisci calendar_id
            cid = updates.get("google_calendar_id")
            if cid:
                if isinstance(cid, str) and "," in cid:
                    updates["google_calendar_id"] = json.dumps([c.strip() for c in cid.split(",") if c.strip()])
                elif isinstance(cid, list):
                    updates["google_calendar_id"] = json.dumps(cid)
            
            # Converti dizionari in JSON strings
            if isinstance(updates.get("opening_hours"), dict):
                updates["opening_hours"] = json.dumps(updates["opening_hours"])
            if isinstance(updates.get("booking_hours"), dict):
                updates["booking_hours"] = json.dumps(updates["booking_hours"])
                
            self.businesses.update_one(
                {"twilio_phone_number": twilio_number}, 
                updates
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
                # Decodifica JSON fields se necessario
                if business.get("google_calendar_id") and business["google_calendar_id"].startswith("["):
                    try:
                        business["google_calendar_id"] = json.loads(business["google_calendar_id"])
                    except:
                        pass
                if business.get("opening_hours") and business["opening_hours"].startswith("{"):
                    try:
                        business["opening_hours"] = json.loads(business["opening_hours"])
                    except:
                        pass
                if business.get("booking_hours") and business["booking_hours"].startswith("{"):
                    try:
                        business["booking_hours"] = json.loads(business["booking_hours"])
                    except:
                        pass
                return business
            return None
        except Exception as e:
            print(f"❌ Errore nel recuperare business: {e}")
            return None
    
    def list_businesses(self):
        try:
            businesses = self.businesses.find()
            for b in businesses:
                # Decodifica JSON fields
                if b.get("google_calendar_id") and b["google_calendar_id"].startswith("["):
                    try:
                        b["google_calendar_id"] = json.loads(b["google_calendar_id"])
                    except:
                        pass
            return businesses
        except Exception as e:
            print(f"❌ Errore nel listare business: {e}")
            return []
    
    def delete_business(self, twilio_number):
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if not business:
                print(f"⚠️  Business non trovato: {twilio_number}")
                return False
            
            business_id = business["id"]
            
            # Elimina conversazioni associate
            conversations = self.conversations.find({"business_id": business_id})
            for conv in conversations:
                self.conversations.delete_one({"id": conv["id"]})
            print(f"🗑️  Eliminate {len(conversations)} conversazioni")
            
            # Elimina business
            self.businesses.delete_one({"twilio_phone_number": twilio_number})
            print(f"✅ Business eliminato: {twilio_number}")
            return True
        except Exception as e:
            print(f"❌ Errore nell'eliminare business: {e}")
            return False
    
    def get_conversation_stats(self, twilio_number):
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if not business:
                return None
            
            business_id = business["id"]
            total_conv = self.conversations.count_documents({"business_id": business_id})
            
            return {
                "business_name": business.get("business_name", "N/A"), 
                "total_conversations": total_conv, 
                "business_id": business_id
            }
        except Exception as e:
            print(f"❌ Errore nel recuperare statistiche: {e}")
            return None

def main():
    manager = BusinessManager()
    
    while True:
        print("\n" + "="*50)
        print("🏢 GESTORE BUSINESS - WHATSAPP BOT")
        print("="*50)
        print("1. Aggiungi nuovo business")
        print("2. Lista business")
        print("3. Visualizza business")
        print("4. Aggiorna business")
        print("5. Elimina business")
        print("6. Statistiche conversazioni")
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
            business_data["phone"] = input("Telefono: ")
            business_data["email"] = input("Email: ")
            business_data["description"] = input("Descrizione: ")
            business_data["website"] = input("Sito web (opzionale): ") or None
            
            cid = input("ID Google Calendar (più ID separati da virgola, opzionale): ").strip()
            if cid:
                business_data["google_calendar_id"] = cid
                
            hours = input("Orari apertura (es: Lun-Ven 9:00-18:00, opzionale): ")
            if hours:
                business_data["opening_hours"] = hours
                
            bh = input("Orari prenotazione (es: 9-18-60 -> start-end-duration): ").strip()
            if bh:
                try:
                    s, e, d = bh.split("-")
                    business_data["booking_hours"] = f"{s}-{e}-{d}"
                except Exception:
                    pass
                    
            services = input("Servizi (separati da virgola, opzionale): ").strip()
            if services:
                business_data["services"] = services
                
            business_data["booking_enabled"] = 1 if input("Abilita prenotazioni? (s/n): ").lower() == 's' else 0
            
            manager.add_business(business_data)
            
        elif choice == "2":
            print("\n📋 LISTA BUSINESS")
            businesses = manager.list_businesses()
            if businesses:
                for i, business in enumerate(businesses, 1):
                    print(f"{i}. {business.get('business_name', 'N/A')} - {business.get('twilio_phone_number', 'N/A')}")
            else:
                print("Nessun business trovato")
                
        elif choice == "3":
            print("\n👀 VISUALIZZA BUSINESS")
            twilio_number = input("Numero Twilio: ")
            business = manager.get_business(twilio_number)
            if business:
                print(json.dumps(business, indent=2, ensure_ascii=False, default=str))
            else:
                print("Business non trovato")
                
        elif choice == "4":
            print("\n✏️  AGGIORNA BUSINESS")
            twilio_number = input("Numero Twilio da aggiornare: ")
            
            print("Campi disponibili: business_name, business_type, address, phone, email, ")
            print("                   website, description, google_calendar_id, opening_hours, ")
            print("                   booking_hours, services, booking_enabled")
            
            field = input("Campo da aggiornare: ")
            value = input("Nuovo valore: ")
            
            # Gestisci campi speciali
            if field == "booking_enabled":
                value = 1 if value.lower() in ['true', '1', 'si', 's'] else 0
                
            manager.update_business(twilio_number, {field: value})
            
        elif choice == "5":
            print("\n🗑️  ELIMINA BUSINESS")
            twilio_number = input("Numero Twilio da eliminare: ")
            confirm = input(f"Confermi eliminazione di {twilio_number}? (si/no): ")
            if confirm.lower() == "si":
                manager.delete_business(twilio_number)
                
        elif choice == "6":
            print("\n📊 STATISTICHE CONVERSAZIONI")
            twilio_number = input("Numero Twilio: ")
            stats = manager.get_conversation_stats(twilio_number)
            if stats:
                print(json.dumps(stats, indent=2, ensure_ascii=False))
            else:
                print("Business non trovato o errore nel recupero statistiche")

if __name__ == "__main__":
    main()