from datetime import datetime
from db_sqlite import SQLiteClient

print("🚀 Configurazione database SQLite...")

# Inizializza connessione e crea tabelle se non esistono
db = SQLiteClient("remindly.db")

# Business di esempio
example_business = {
    "business_name": "Esempio Ristorante",
    "business_type": "ristorante",
    "twilio_phone_number": "whatsapp:+1234567890",
    "address": "Via Roma 123, Milano",
    "phone": "+39 02 1234567",
    "email": "info@esempio.com",
    "website": "www.esempio.com",
    "google_calendar_id": "",
    "booking_hours": "",
    "services": "cena,asporto,delivery",
    "opening_hours": "lun-ven 19-24",
    "description": "Ristorante tradizionale",
    "created_at": datetime.now().isoformat(),
    "updated_at": datetime.now().isoformat(),
    "booking_enabled": 1
}

# Inserisce l'esempio solo se non esiste già
if not db.businesses.find_one({"twilio_phone_number": example_business["twilio_phone_number"]}):
    db.businesses.insert_one(example_business)
    print("✅ Business di esempio creato")
else:
    print("⚠️  Business di esempio già esistente")

print("🎉 Setup completato!")
