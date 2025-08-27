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
        if hasattr(self, 'client') and self.client:
            return

        uri = db_uri or os.getenv("MONGO_URI")
        if not uri:
            raise Exception("ERRORE CRITICO: La variabile d'ambiente MONGO_URI non è stata impostata.")

        try:
            server_api = ServerApi('1')
            self.client = MongoClient(uri, server_api=server_api)
            self.client.admin.command('ping')
            print("--- CONNESSIONE A MONGODB STABILITA CON SUCCESSO! ---")
            
            db = self.client.remindly
            self.businesses = db.businesses
            self.conversations = db.conversations
            self.customers = db.customers
            self.bookings = db.bookings
            self.pending_bookings = db.pending_bookings

        except Exception as e:
            print(f"--- ERRORE FATALE DI CONNESSIONE A MONGODB ---")
            raise Exception(f"Impossibile connettersi a MongoDB: {e}")

# Nome corretto e coerente
db_connection = MongoClientWrapper()