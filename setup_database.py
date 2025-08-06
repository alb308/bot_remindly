import os
from pymongo import MongoClient
from datetime import datetime

# Script per configurare il database MongoDB con gli indici ottimali

MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    raise Exception("ERRORE: Imposta la variabile MONGO_URI")

client = MongoClient(MONGO_URI)
db = client.get_database()

print("🚀 Configurazione database in corso...")

# 1. Configura collezione businesses
businesses = db.businesses
print("📊 Configurazione collezione 'businesses'...")

# Crea indici per businesses
businesses.create_index("twilio_phone_number", unique=True)
businesses.create_index("business_name")
businesses.create_index("created_at")

print("✅ Indici creati per 'businesses'")

# 2. Configura collezione conversations
conversations = db.conversations
print("💬 Configurazione collezione 'conversations'...")

# Crea indici composti per conversations
conversations.create_index([("user_id", 1), ("business_id", 1)], unique=True)
conversations.create_index("last_interaction")
conversations.create_index("business_id")
conversations.create_index("created_at")

# Indice TTL per cancellare automaticamente conversazioni vecchie (opzionale)
# conversations.create_index("last_interaction", expireAfterSeconds=2592000)  # 30 giorni

print("✅ Indici creati per 'conversations'")

# 3. Inserisci un business di esempio (se non esiste)
example_business = {
    "business_name": "Esempio Ristorante",
    "twilio_phone_number": "whatsapp:+1234567890",  # SOSTITUISCI CON IL TUO NUMERO TWILIO
    "business_type": "ristorante",
    "address": "Via Roma 123, Milano",
    "phone": "+39 02 1234567",
    "email": "info@esempio.com",
    "opening_hours": {
        "lunedi-venerdi": "19:00-24:00",
        "sabato-domenica": "12:00-15:00, 19:00-24:00"
    },
    "services": ["cena", "asporto", "delivery"],
    "specialties": ["pizza napoletana", "cucina italiana"],
    "description": "Ristorante tradizionale italiano nel cuore di Milano",
    "website": "www.esempio.com",
    "created_at": datetime.now().isoformat(),
    "updated_at": datetime.now().isoformat()
}

# Controlla se esiste già un business con questo numero
if not businesses.find_one({"twilio_phone_number": example_business["twilio_phone_number"]}):
    result = businesses.insert_one(example_business)
    print(f"✅ Business di esempio creato con ID: {result.inserted_id}")
else:
    print("⚠️  Business di esempio già esistente")

print("\n🎉 Setup database completato!")
print("\n📋 Prossimi passi:")
print("1. Aggiorna il numero Twilio nell'esempio con il tuo numero reale")
print("2. Aggiungi i tuoi business tramite MongoDB Compass o script personalizzati")
print("3. Testa il webhook con il tuo numero WhatsApp configurato")

# 4. Mostra struttura database
print(f"\n📊 Statistiche database:")
print(f"   • Businesses: {businesses.count_documents({})}")
print(f"   • Conversations: {conversations.count_documents({})}")

client.close()