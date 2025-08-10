import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

class MongoClientWrapper:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MongoClientWrapper, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_uri: str = None):
        # Evita di reinizializzare se già connesso
        if hasattr(self, 'client') and self.client:
            return

        uri = db_uri or os.getenv("MONGO_URI")
        if not uri:
            raise Exception("ERRORE CRITICO: La variabile d'ambiente MONGO_URI non è impostata.")

        try:
            server_api = ServerApi('1')
            self.client = MongoClient(uri, server_api=server_api)
            # Testa la connessione
            self.client.admin.command('ping')
            print("Connessione a MongoDB stabilita con successo!")
            
            # --- MODIFICA CHIAVE: ESPONI DIRETTAMENTE LE COLLEZIONI ---
            db = self.client.remindly # Usa direttamente il nome del database
            self.businesses = db.businesses
            self.conversations = db.conversations
            self.customers = db.customers
            self.bookings = db.bookings
            self.pending_bookings = db.pending_bookings

        except Exception as e:
            print(f"ERRORE: Impossibile connettersi a MongoDB: {e}")
            self.client = None
            # Assicura che gli attributi esistano anche in caso di errore per evitare AttributeError
            self.businesses = None
            self.conversations = None
            self.customers = None
            self.bookings = None
            self.pending_bookings = None

# Rinominiamo la classe per coerenza con il resto del codice
SQLiteClient = MongoClientWrapper()