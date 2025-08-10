import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi

class MongoCollection:
    def __init__(self, collection):
        self.collection = collection

    def find_one(self, query):
        return self.collection.find_one(query)

    def find(self, query={}):
        return list(self.collection.find(query))

    def insert_one(self, data):
        result = self.collection.insert_one(data)
        return {"inserted_id": result.inserted_id}

    def update_one(self, query, update, upsert=False):
        # Supporta il formato {"$set": ...}
        self.collection.update_one(query, update, upsert=upsert)

    def delete_one(self, query):
        self.collection.delete_one(query)

    def count_documents(self, query={}):
        return self.collection.count_documents(query)


class MongoClientWrapper:
    def __init__(self, db_uri: str, db_name: str = "remindly"):
        try:
            # Imposta la versione stabile dell'API
            server_api = ServerApi('1')
            self.client = MongoClient(db_uri, server_api=server_api)
            self.db = self.client[db_name]

            # Testa la connessione
            self.client.admin.command('ping')
            print("Connessione a MongoDB stabilita con successo!")

            # Inizializza le collections
            self.businesses = MongoCollection(self.db.businesses)
            self.conversations = MongoCollection(self.db.conversations)
            self.customers = MongoCollection(self.db.customers)
            self.bookings = MongoCollection(self.db.bookings)
            self.pending_bookings = MongoCollection(self.db.pending_bookings)

        except Exception as e:
            print(f"ERRORE: Impossibile connettersi a MongoDB: {e}")
            self.client = None

    def get_database(self):
        return self

    def close(self):
        if self.client:
            self.client.close()

# Esponi una singola istanza del client
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise Exception("ERRORE: La variabile d'ambiente MONGO_URI non è stata impostata.")

# Rinominiamo la classe per coerenza
SQLiteClient = MongoClientWrapper(MONGO_URI)