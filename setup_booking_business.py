from datetime import datetime
from db_sqlite import SQLiteClient

db = SQLiteClient("remindly.db")

def setup_booking_business():
    print("🏢 CONFIGURAZIONE BUSINESS CON PRENOTAZIONI")
    print("=" * 50)

    business_data = {}
    business_data["business_name"] = input("Nome del business: ")
    business_data["business_type"] = input("Tipo di business (es: parrucchiere, medico, consulente): ")
    business_data["twilio_phone_number"] = input("Numero Twilio WhatsApp (es: whatsapp:+1234567890): ")
    business_data["address"] = input("Indirizzo: ")
    business_data["phone"] = input("Telefono principale: ")
    business_data["email"] = input("Email: ")
    business_data["website"] = input("Sito web (opzionale): ")

    business_data["google_calendar_id"] = input("ID del Google Calendar: ")

    print("\n🕐 ORARI DI PRENOTAZIONE:")
    start_hour = int(input("Ora inizio (formato 24h, es: 9): "))
    end_hour = int(input("Ora fine (formato 24h, es: 18): "))
    duration = int(input("Durata standard appuntamento (minuti, es: 60): "))
    business_data["booking_hours"] = f"{start_hour}-{end_hour}-{duration}"

    print("\n🔧 SERVIZI OFFERTI:")
    print("Inserisci i servizi uno per uno (premi Invio vuoto per terminare):")
    services = []
    while True:
        service = input(f"Servizio {len(services) + 1}: ").strip()
        if not service:
            break
        services.append(service)
    business_data["services"] = ",".join(services)

    business_data["opening_hours"] = input("Orari di apertura (es: Lun-Ven 9:00-18:00): ")
    business_data["description"] = input("Descrizione del business: ")

    business_data["created_at"] = datetime.now().isoformat()
    business_data["updated_at"] = datetime.now().isoformat()
    business_data["booking_enabled"] = 1

    if db.businesses.find_one({"twilio_phone_number": business_data["twilio_phone_number"]}):
        print(f"⚠️ Business già esistente per {business_data['twilio_phone_number']}")
    else:
        db.businesses.insert_one(business_data)
        print(f"✅ Business '{business_data['business_name']}' creato con successo!")

if __name__ == "__main__":
    setup_booking_business()
