import sqlite3
from typing import Dict, Any, List, Optional

class SQLiteCollection:
    def __init__(self, conn: sqlite3.Connection, table: str):
        self.conn = conn
        self.table = table

    def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not query:
            return None
        where_clause = " AND ".join([f"{k}=?" for k in query.keys()])
        cur = self.conn.execute(f"SELECT * FROM {self.table} WHERE {where_clause} LIMIT 1", tuple(query.values()))
        row = cur.fetchone()
        return self._row_to_dict(cur, row) if row else None

    def find(self, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not query:
            cur = self.conn.execute(f"SELECT * FROM {self.table}")
        else:
            where_clause = " AND ".join([f"{k}=?" for k in query.keys()])
            cur = self.conn.execute(f"SELECT * FROM {self.table} WHERE {where_clause}", tuple(query.values()))
        rows = cur.fetchall()
        return [self._row_to_dict(cur, r) for r in rows]

    def insert_one(self, data: Dict[str, Any]):
        keys = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        cur = self.conn.execute(f"INSERT INTO {self.table} ({keys}) VALUES ({placeholders})", tuple(data.values()))
        self.conn.commit()
        return {"inserted_id": cur.lastrowid}

    def update_one(self, query: Dict[str, Any], update: Dict[str, Any], upsert: bool=False):
        # supporta formato tipo {"$set": {...}} o direttamente {...}
        if "$set" in update: updates = update["$set"]
        else: updates = update
        set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
        where_clause = " AND ".join([f"{k}=?" for k in query.keys()])
        params = tuple(updates.values()) + tuple(query.values())
        self.conn.execute(f"UPDATE {self.table} SET {set_clause} WHERE {where_clause}", params)
        self.conn.commit()

    def delete_one(self, query: Dict[str, Any]):
        where_clause = " AND ".join([f"{k}=?" for k in query.keys()])
        self.conn.execute(f"DELETE FROM {self.table} WHERE {where_clause}", tuple(query.values()))
        self.conn.commit()

    def count_documents(self, query: Dict[str, Any] = None) -> int:
        if not query:
            cur = self.conn.execute(f"SELECT COUNT(*) FROM {self.table}")
        else:
            where_clause = " AND ".join([f"{k}=?" for k in query.keys()])
            cur = self.conn.execute(f"SELECT COUNT(*) FROM {self.table} WHERE {where_clause}", tuple(query.values()))
        return cur.fetchone()[0]

    def _row_to_dict(self, cur, row):
        return dict(zip([d[0] for d in cur.description], row))


class SQLiteClient:
    def __init__(self, db_path: str = "remindly.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

        self.businesses = SQLiteCollection(self.conn, "businesses")
        self.conversations = SQLiteCollection(self.conn, "conversations")
        self.customers = SQLiteCollection(self.conn, "customers")
        self.bookings = SQLiteCollection(self.conn, "bookings")
        self.pending_bookings = SQLiteCollection(self.conn, "pending_bookings")

    def get_database(self):
        return self

    def close(self):
        self.conn.close()

    def _init_tables(self):
        c = self.conn.cursor()

        c.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT,
            business_type TEXT,
            twilio_phone_number TEXT UNIQUE,
            address TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            google_calendar_id TEXT,
            booking_hours TEXT,
            services TEXT,
            opening_hours TEXT,
            description TEXT,
            booking_enabled INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            business_id INTEGER,
            messages TEXT,          -- JSON string (lista di {role,content,timestamp})
            last_interaction TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(user_id, business_id)
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            business_id INTEGER,
            name TEXT,
            email TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(user_id, business_id)
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            business_id INTEGER,
            booking_data TEXT,      -- JSON {date,time,duration,service_type,customer_name,customer_phone,notes}
            status TEXT,
            calendar_event_id TEXT,
            created_at TEXT,
            confirmed_at TEXT,
            cancelled_at TEXT
        )""")

        c.execute("""
        CREATE TABLE IF NOT EXISTS pending_bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            business_id INTEGER,
            booking_data TEXT,
            status TEXT,
            created_at TEXT,
            expires_at TEXT
        )""")

        self.conn.commit()
