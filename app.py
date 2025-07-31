import os
import json
from flask import Flask, request
from openai import OpenAI
from twilio.twiml.messaging_response import MessagingResponse
from pymongo import MongoClient

# --- CONFIGURAZIONE E CONNESSIONE AL DATABASE ---

app = Flask(__name__)

# Carica le chiavi API e la stringa di connessione al DB dalle variabili d'ambiente di Railway
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI") # Es: mongodb+srv://user:pass@host...

if not OPENAI_API_KEY or not MONGO_URI:
    raise Exception("ERRORE: Assicurati di aver impostato le variabili OPENAI_API_KEY e MONGO_URI su Railway.")

# Inizializza i client
openai_client = OpenAI(api_key=OPENAI_API_KEY)
mongo_client = MongoClient(MONGO_URI)
db = mongo_client.get_database() # Si connette al database di default
businesses_collection = db.businesses

print("Connessione a MongoDB stabilita.")

# --- WEBHOOK PER WHATSAPP (TWILIO) ---

@app.route("/whatsapp-webhook", methods=["POST"])
def whatsapp_reply():
    """
    Webhook multi-tenant che identifica il business dal numero di telefono
    e risponde usando il profilo corretto recuperato dal database.
    """
    twiml_response = MessagingResponse()

    # 1. Estrai il messaggio dell'utente E il numero di telefono del destinatario (il tuo numero Twilio)
    incoming_msg = request.values.get("Body", "").strip()
    recipient_number = request.values.get("To", "").strip() # Es: 'whatsapp:+14155238886'

    if not incoming_msg or not recipient_number:
        return str(twiml_response) # Ignora richieste non valide

    # 2. Cerca il profilo del business nel database usando il numero Twilio
    try:
        business_profile = businesses_collection.find_one({"twilio_phone_number": recipient_number})
    except Exception as e:
        print(f"ERRORE DB: Impossibile interrogare il database: {e}")
        twiml_response.message("Si è verificato un errore interno. Riprova più tardi.")
        return str(twiml_response)

    if not business_profile:
        print(f"ATTENZIONE: Nessun business trovato per il numero Twilio {recipient_number}")
        twiml_response.message("Questo numero WhatsApp non è attualmente configurato per un servizio di assistenza.")
        return str(twiml_response)

    # 3. Costruisci il prompt di sistema con i dati trovati
    # Escludiamo campi interni di MongoDB come _id dal prompt
    business_profile.pop("_id", None)
    business_info_str = json.dumps(business_profile, indent=2, ensure_ascii=False)

    SYSTEM_PROMPT = f"""
    Sei un assistente virtuale professionale, calmo e umano per un'attività commerciale.
    Basa le tue risposte ESCLUSIVAMENTE sulle informazioni fornite qui sotto.
    Se un utente chiede qualcosa che non è presente nelle informazioni, rispondi gentilmente: "Mi dispiace, non dispongo di questa informazione. Per dettagli specifici la invito a contattare direttamente la struttura."
    Non usare mai emoji. Non inventare mai informazioni. Rispondi sempre in italiano.

    --- INFORMAZIONI SUL BUSINESS ---
    {business_info_str}
    --- FINE INFORMAZIONI SUL BUSINESS ---
    """

    # 4. Chiama OpenAI e invia la risposta
    try:
        completion = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": incoming_msg}
            ],
            temperature=0.2, # Molto bassa per risposte fattuali
            max_tokens=250
        )
        ai_response = completion.choices[0].message.content
        twiml_response.message(ai_response)

    except Exception as e:
        print(f"ERRORE API OpenAI: {e}")
        twiml_response.message("Mi scuso, si è verificato un problema tecnico. La preghiamo di riprovare più tardi.")

    return str(twiml_response)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)