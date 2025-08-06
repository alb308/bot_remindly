import os
import json
from pymongo import MongoClient
from datetime import datetime

class BusinessManager:
    def __init__(self):
        self.mongo_uri = os.environ.get("MONGO_URI")
        if not self.mongo_uri:
            raise Exception("ERRORE: Imposta la variabile MONGO_URI")
        
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client.get_database()
        self.businesses = self.db.businesses
        self.conversations = self.db.conversations
    
    def add_business(self, business_data):
        """Aggiungi un nuovo business"""
        try:
            # Aggiungi timestamp
            business_data.update({
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
            
            result = self.businesses.insert_one(business_data)
            print(f"✅ Business aggiunto con ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            print(f"❌ Errore nell'aggiungere business: {e}")
            return None
    
    def update_business(self, twilio_number, updates):
        """Aggiorna un business esistente"""
        try:
            updates["updated_at"] = datetime.now().isoformat()
            
            result = self.businesses.update_one(
                {"twilio_phone_number": twilio_number},
                {"$set": updates}
            )
            
            if result.modified_count > 0:
                print(f"✅ Business aggiornato per numero: {twilio_number}")
                return True
            else:
                print(f"⚠️  Nessun business trovato con numero: {twilio_number}")
                return False
        except Exception as e:
            print(f"❌ Errore nell'aggiornare business: {e}")
            return False
    
    def get_business(self, twilio_number):
        """Recupera un business dal numero Twilio"""
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if business:
                # Converti ObjectId in stringa per JSON serialization
                business["_id"] = str(business["_id"])
                return business
            return None
        except Exception as e:
            print(f"❌ Errore nel recuperare business: {e}")
            return None
    
    def list_businesses(self):
        """Lista tutti i business"""
        try:
            businesses = list(self.businesses.find())
            for business in businesses:
                business["_id"] = str(business["_id"])
            return businesses
        except Exception as e:
            print(f"❌ Errore nel listare business: {e}")
            return []
    
    def delete_business(self, twilio_number):
        """Elimina un business e le sue conversazioni"""
        try:
            # Prima trova l'ID del business
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if not business:
                print(f"⚠️  Business non trovato: {twilio_number}")
                return False
            
            business_id = str(business["_id"])
            
            # Elimina le conversazioni associate
            conv_result = self.conversations.delete_many({"business_id": business_id})
            print(f"🗑️  Eliminate {conv_result.deleted_count} conversazioni")
            
            # Elimina il business
            bus_result = self.businesses.delete_one({"twilio_phone_number": twilio_number})
            
            if bus_result.deleted_count > 0:
                print(f"✅ Business eliminato: {twilio_number}")
                return True
            return False
        except Exception as e:
            print(f"❌ Errore nell'eliminare business: {e}")
            return False
    
    def get_conversation_stats(self, twilio_number):
        """Ottieni statistiche conversazioni per un business"""
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if not business:
                return None
            
            business_id = str(business["_id"])
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
    """Interfaccia CLI per gestire i business"""
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
            
            # Orari (semplificato)
            hours = input("Orari apertura (es: Lun-Ven 9:00-18:00): ")
            if hours:
                business_data["opening_hours"] = {"general": hours}
            
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
                print(json.dumps(business, indent=2, ensure_ascii=False))
            else:
                print("Business non trovato")
        
        elif choice == "4":
            print("\n✏️  AGGIORNA BUSINESS")
            twilio_number = input("Numero Twilio da aggiornare: ")
            field = input("Campo da aggiornare: ")
            value = input("Nuovo valore: ")
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