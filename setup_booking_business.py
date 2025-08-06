import os
from pymongo import MongoClient
from datetime import datetime

# Script per configurare un business con sistema di prenotazioni

MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    raise Exception("ERRORE: Imposta la variabile MONGO_URI")

client = MongoClient(MONGO_URI)
db = client.get_database()
businesses = db.businesses

def setup_booking_business():
    """Configura un business con sistema di prenotazioni"""
    
    print("🏢 CONFIGURAZIONE BUSINESS CON PRENOTAZIONI")
    print("=" * 50)
    
    # Informazioni base del business
    business_data = {}
    
    print("\n📋 INFORMAZIONI GENERALI:")
    business_data["business_name"] = input("Nome del business: ")
    business_data["business_type"] = input("Tipo di business (es: parrucchiere, medico, consulente): ")
    business_data["twilio_phone_number"] = input("Numero Twilio WhatsApp (es: whatsapp:+1234567890): ")
    
    # Informazioni di contatto
    print("\n📞 CONTATTI:")
    business_data["address"] = input("Indirizzo: ")
    business_data["phone"] = input("Telefono principale: ")
    business_data["email"] = input("Email: ")
    business_data["website"] = input("Sito web (opzionale): ") or None
    
    # Google Calendar ID
    print("\n📅 CONFIGURAZIONE CALENDARIO:")
    print("Per ottenere l'ID del calendario:")
    print("1. Vai su Google Calendar")
    print("2. Nelle impostazioni del calendario, cerca 'ID calendario'")
    print("3. Copia l'ID (es: abc123@group.calendar.google.com)")
    business_data["google_calendar_id"] = input("ID del Google Calendar: ")
    
    # Configurazione orari prenotazioni
    print("\n🕐 ORARI DI PRENOTAZIONE:")
    start_hour = int(input("Ora inizio (formato 24h, es: 9): "))
    end_hour = int(input("Ora fine (formato 24h, es: 18): "))
    duration = int(input("Durata standard appuntamento (minuti, es: 60): "))
    
    business_data["booking_hours"] = {
        "start": start_hour,
        "end": end_hour,
        "default_duration": duration
    }
    
    # Servizi offerti
    print("\n🔧 SERVIZI OFFERTI:")
    print("Inserisci i servizi uno per uno (premi Invio vuoto per terminare):")
    services = []
    while True:
        service = input(f"Servizio {len(services) + 1}: ").strip()
        if not service:
            break
        services.append(service)
    
    business_data["services"] = services
    
    # Orari di apertura (informativi)
    print("\n🏪 ORARI DI APERTURA (informativi):")
    business_data["opening_hours"] = {
        "lunedi-venerdi": input("Lun-Ven: "),
        "sabato": input("Sabato: "),
        "domenica": input("Domenica: ")
    }
    
    # Descrizione
    print("\n📝 DESCRIZIONE:")
    business_data["description"] = input("Descrizione del business: ")
    
    # Aggiungi timestamp
    business_data.update({
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "booking_enabled": True
    })
    
    # Salva nel database
    try:
        # Controlla se esiste già
        existing = businesses.find_one({"twilio_phone_number": business_data["twilio_phone_number"]})
        if existing:
            print(f"\n⚠️  Business già esistente per {business_data['twilio_phone_number']}")
            update = input("Vuoi aggiornarlo? (s/n): ").lower() == 's'
            if update:
                businesses.update_one(
                    {"twilio_phone_number": business_data["twilio_phone_number"]},
                    {"$set": business_data}
                )
                print("✅ Business aggiornato con successo!")
            else:
                print("❌ Operazione annullata")
        else:
            result = businesses.insert_one(business_data)
            print(f"\n✅ Business creato con successo!")
            print(f"ID: {result.inserted_id}")
        
        # Mostra riepilogo
        print(f"\n📊 RIEPILOGO CONFIGURAZIONE:")
        print(f"Nome: {business_data['business_name']}")
        print(f"Tipo: {business_data['business_type']}")
        print(f"WhatsApp: {business_data['twilio_phone_number']}")
        print(f"Calendar ID: {business_data['google_calendar_id']}")
        print(f"Orari prenotazioni: {start_hour}:00 - {end_hour}:00")
        print(f"Durata standard: {duration} minuti")
        print(f"Servizi: {', '.join(services)}")
        
    except Exception as e:
        print(f"❌ Errore nel salvare: {e}")

def test_calendar_connection():
    """Testa la connessione al calendario"""
    print("\n🔧 TEST CONNESSIONE CALENDARIO")
    print("=" * 30)
    
    calendar_id = input("ID Calendar da testare: ")
    
    try:
        from calendar_service import CalendarService
        
        service_account_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY")
        if not service_account_key:
            print("❌ Variabile GOOGLE_SERVICE_ACCOUNT_KEY non impostata")
            return
        
        calendar_service = CalendarService(calendar_id, service_account_key)
        
        if calendar_service.service:
            # Test: ottieni eventi prossimi
            upcoming = calendar_service.get_upcoming_appointments(days_ahead=7)
            print(f"✅ Connessione riuscita!")
            print(f"📅 Eventi prossimi 7 giorni: {len(upcoming)}")
            
            # Test: slot disponibili per domani
            from datetime import datetime, timedelta
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            slots = calendar_service.get_available_slots(tomorrow)
            print(f"🕐 Slot disponibili domani ({tomorrow}): {len(slots)}")
            
        else:
            print("❌ Impossibile inizializzare il servizio calendar")
            
    except ImportError:
        print("❌ Modulo calendar_service non trovato")
    except Exception as e:
        print(f"❌ Errore nel test: {e}")

def main():
    """Menu principale"""
    while True:
        print("\n" + "="*50)
        print("🔧 SETUP BUSINESS CON PRENOTAZIONI")
        print("="*50)
        print("1. Configura nuovo business")
        print("2. Testa connessione calendario")
        print("3. Lista business esistenti")
        print("0. Esci")
        
        choice = input("\nScegli un'opzione: ").strip()
        
        if choice == "0":
            print("👋 Arrivederci!")
            break
        elif choice == "1":
            setup_booking_business()
        elif choice == "2":
            test_calendar_connection()
        elif choice == "3":
            print("\n📋 BUSINESS ESISTENTI:")
            try:
                for business in businesses.find():
                    booking_status = "🟢 Attivo" if business.get('booking_enabled') else "🔴 Disattivo"
                    print(f"• {business.get('business_name', 'N/A')} - {business.get('twilio_phone_number', 'N/A')} - Prenotazioni: {booking_status}")
            except Exception as e:
                print(f"Errore: {e}")

if __name__ == "__main__":
    main()