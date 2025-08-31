# manage_business.py - Aggiornato per sistema dinamico

import os
import json
from datetime import datetime, timedelta
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
    
    def setup_dynamic_calendar_events(self, business_id):
        """
        Crea eventi di sistema nel calendario per gestire orari dinamici
        Esempi di eventi che puoi creare manualmente in Google Calendar:
        
        1. CHIUSURA GIORNALIERA:
           - Titolo: "CHIUSO - Domenica"
           - Data: Ogni domenica
           - Orario: Tutto il giorno
           
        2. ORARI SPECIALI:
           - Titolo: "ORARI: 10:00-20:00 - Sabato"
           - Data: Sabati specifici
           - Orario: 10:00-20:00
           
        3. FERIE:
           - Titolo: "CHIUSO - Ferie Agosto"
           - Data: Dal 15 al 25 agosto
           - Orario: Tutto il giorno
           
        4. ORARI RIDOTTI:
           - Titolo: "ORARI: 14:00-18:00 - Festivo"
           - Data: Giorni festivi
           - Orario: 14:00-18:00
        """
        print(f"""
📅 CONFIGURAZIONE CALENDARIO DINAMICO per Business ID: {business_id}

Per configurare orari dinamici, crea questi eventi nel tuo Google Calendar:

🚫 CHIUSURE:
   Titolo evento: "CHIUSO - [motivo]"
   Esempi: "CHIUSO - Domenica", "CHIUSO - Ferie", "CHIUSO - Malattia"
   
⏰ ORARI SPECIALI:
   Titolo evento: "ORARI: HH:MM-HH:MM - [motivo]"
   Esempi: "ORARI: 10:00-20:00 - Sabato", "ORARI: 14:00-18:00 - Festivo"

📝 REGOLE:
   - Eventi "CHIUSO" = business completamente chiuso
   - Eventi "ORARI" = sovrascrivono orari default per quella data
   - Il sistema rileva automaticamente questi eventi e adatta la disponibilità
   - Senza eventi speciali, usa gli orari dal database ({business_id})

✅ Il sistema è già configurato e funzionante!
        """)
    
    def get_business(self, twilio_number):
        try:
            business = self.businesses.find_one({"twilio_phone_number": twilio_number})
            if business:
                services_str = business.get("services")
                if services_str and isinstance(services_str, str):
                    try: 
                        business["services"] = json.loads(services_str)
                    except json.JSONDecodeError: 
                        pass
                return business
            return None
        except Exception as e:
            print(f"❌ Errore nel recuperare business: {e}")
            return None

    def test_calendar_integration(self, twilio_number):
        """Test dell'integrazione dinamica del calendario"""
        business = self.get_business(twilio_number)
        if not business:
            print("❌ Business non trovato")
            return False
            
        business_id = business['_id']
        calendar_id = business.get('google_calendar_id')
        
        if not calendar_id:
            print("❌ Google Calendar ID non configurato")
            return False
            
        print(f"🔍 Testing calendario per: {business.get('business_name')}")
        print(f"📅 Calendar ID: {calendar_id[:20]}...")
        
        # Test prossimi 3 giorni
        today = datetime.now()
        for i in range(3):
            test_date = (today + timedelta(days=i)).strftime('%Y-%m-%d')
            day_name = (today + timedelta(days=i)).strftime('%A')
            
            print(f"\n📅 {day_name} ({test_date}):")
            
            try:
                from calendar_service import CalendarService
                calendar_service = CalendarService(
                    calendar_id=calendar_id,
                    service_account_key=os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
                )
                
                # Test controllo orari
                is_open, start_time, end_time = calendar_service.check_business_hours_override(test_date)
                
                if is_open is False:
                    print("   🚫 Business CHIUSO (evento nel calendario)")
                elif start_time and end_time:
                    print(f"   ⏰ Orari SPECIALI: {start_time} - {end_time}")
                else:
                    default_hours = business.get("booking_hours", "9-18")
                    print(f"   📝 Orari DEFAULT: {default_hours}")
                
                # Test slot disponibili
                slots = calendar_service.get_available_slots(
                    date=test_date,
                    duration_minutes=60,
                    start_hour=9,
                    end_hour=18
                )
                
                print(f"   ✅ Slot disponibili: {len(slots)}")
                if slots:
                    first_few = [s['start'] for s in slots[:3]]
                    print(f"   🕐 Primi slot: {', '.join(first_few)}")
                    
            except Exception as e:
                print(f"   ❌ Errore test: {e}")
        
        return True

def main():
    manager = BusinessManager()
    
    while True:
        print("\n" + "="*60)
        print("🏢 GESTORE BUSINESS - SISTEMA DINAMICO CALENDARIO")
        print("="*60)
        print("1. Aggiungi nuovo business")
        print("2. Visualizza business")
        print("3. Setup calendario dinamico")
        print("4. Test integrazione calendario")
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
            
            print("\n🕒 ORARI BASE (usati quando non ci sono eventi speciali nel calendario)")
            print("Il sistema dinamico può sovrascrivere questi orari con eventi nel calendario")
            start_h = input("Ora di inizio base (es: 9): ")
            end_h = input("Ora di fine base (es: 18): ")
            business_data["booking_hours"] = f"{start_h}-{end_h}"
            
            print("\n✂️ SERVIZI OFFERTI")
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
            
            business_id = manager.add_business(business_data)
            if business_id:
                print(f"\n✅ Business creato! ID: {business_id}")
                setup_calendar = input("\nVuoi vedere le istruzioni per il calendario dinamico? (s/n): ")
                if setup_calendar.lower() == 's':
                    manager.setup_dynamic_calendar_events(business_id)
            
        elif choice == "2":
            twilio_number = input("Numero Twilio del business da visualizzare: ")
            business = manager.get_business(twilio_number)
            if business:
                print(json.dumps(business, indent=2, ensure_ascii=False, default=str))
            else:
                print("Business non trovato.")
                
        elif choice == "3":
            twilio_number = input("Numero Twilio del business: ")
            business = manager.get_business(twilio_number)
            if business:
                manager.setup_dynamic_calendar_events(business['_id'])
            else:
                print("❌ Business non trovato")
                
        elif choice == "4":
            twilio_number = input("Numero Twilio del business da testare: ")
            manager.test_calendar_integration(twilio_number)

if __name__ == "__main__":
    main()

# ESEMPI DI USO DEL SISTEMA DINAMICO:

"""
📅 COME FUNZIONA IL SISTEMA DINAMICO:

1. ORARI BASE (nel database):
   booking_hours: "9-18" 
   ↓
   Usati quando NON ci sono eventi speciali nel calendario

2. EVENTI SPECIALI (in Google Calendar):
   
   CHIUSURA DOMENICA:
   • Titolo: "CHIUSO - Domenica"
   • Ricorrenza: Ogni domenica
   • Tipo: Tutto il giorno
   ↓ 
   Sistema: Nessun slot disponibile la domenica
   
   ORARI SABATO LUNGO:
   • Titolo: "ORARI: 10:00-20:00 - Sabato"
   • Data: Sabati specifici  
   • Orario: 10:00-20:00
   ↓
   Sistema: Slot dalle 10 alle 20 invece che 9-18
   
   FERIE AGOSTO:
   • Titolo: "CHIUSO - Ferie Agosto"
   • Date: 15-25 Agosto 2024
   • Tipo: Tutto il giorno
   ↓
   Sistema: Nessun slot disponibile in quel periodo
   
   ORARI RIDOTTI FESTIVI:
   • Titolo: "ORARI: 14:00-17:00 - Epifania"
   • Data: 6 Gennaio 2024
   • Orario: 14:00-17:00
   ↓
   Sistema: Solo slot pomeridiani

3. RISULTATO:
   Il bot controlla SEMPRE Google Calendar prima di proporre orari,
   rispettando automaticamente chiusure e orari speciali.
"""