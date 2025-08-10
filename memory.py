import re
import json
from datetime import datetime
from typing import Dict, List
from openai import OpenAI

NAME_PATTERNS = [
    r'\bmi chiamo\s+([A-Za-zÀ-ÿ\-\' ]+)',
    r'\bsono\s+([A-Za-zÀ-ÿ\-\' ]+)',
    r'\bil mio nome è\s+([A-Za-zÀ-ÿ\-\' ]+)'
]
EMAIL_PATTERN = r'[\w\.-]+@[\w\.-]+\.\w+'

class MemoryService:
    """
    - Estrae dati cliente (nome, email) e li salva in `customers`
    - Genera riassunti periodici delle conversazioni (long-term memory)
    - Costruisce un contesto distillato (riassunti + profilo) da passare al modello
    """
    def __init__(self, db, openai_api_key: str):
        self.db = db
        self.client = OpenAI(api_key=openai_api_key)

    def upsert_customer_profile(self, user_id: str, business_id: int, history: List[Dict], current_text: str):
        """Estrae e salva informazioni del cliente"""
        name = None
        for pat in NAME_PATTERNS:
            m = re.search(pat, current_text, flags=re.IGNORECASE)
            if m:
                name = m.group(1).strip().title()
                break
        
        email = None
        e = re.search(EMAIL_PATTERN, current_text)
        if e:
            email = e.group(0)

        if name or email:
            # Cerca cliente esistente
            existing = self.db.customers.find_one({
                "user_id": user_id,
                "business_id": business_id
            })
            
            updates = {
                "user_id": user_id,
                "business_id": business_id,
                "updated_at": datetime.now().isoformat()
            }
            
            if name:
                updates["name"] = name
            if email:
                updates["email"] = email
                
            if not existing:
                updates["created_at"] = datetime.now().isoformat()
                self.db.customers.insert_one(updates)
            else:
                self.db.customers.update_one(
                    {"user_id": user_id, "business_id": business_id},
                    updates
                )

    def summarize_if_needed(self, user_id: str, business_id: int, threshold: int = 20):
        """Genera riassunto se la conversazione supera la soglia"""
        conv = self.db.conversations.find_one({
            "user_id": user_id, 
            "business_id": business_id
        })
        
        if not conv:
            return
            
        msgs = json.loads(conv.get("messages", "[]"))
        
        if len(msgs) < threshold:
            return
            
        # Prendi gli ultimi N messaggi per il riassunto
        slice_msgs = msgs[-threshold:]
        
        prompt = [
            {
                "role": "system", 
                "content": "Riassumi i punti chiave, richieste, preferenze e dati utili (nome, email, servizi richiesti). Stile telegrafico, puntato."
            },
            {
                "role": "user", 
                "content": "\n\n".join([f"{m['role'].upper()}: {m['content']}" for m in slice_msgs])
            }
        ]
        
        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=prompt,
                temperature=0.2,
                max_tokens=250
            )
            summary = resp.choices[0].message.content.strip()
            
            # Recupera i riassunti esistenti (se presenti)
            summaries = json.loads(conv.get("summaries", "[]")) if conv.get("summaries") else []
            
            # Aggiungi nuovo riassunto
            summaries.append({
                "content": summary,
                "ts": datetime.now().isoformat()
            })
            
            # Aggiorna conversazione con i riassunti
            self.db.conversations.update_one(
                {"user_id": user_id, "business_id": business_id},
                {
                    "summaries": json.dumps(summaries),
                    "last_summary_at": datetime.now().isoformat()
                }
            )
            
            print(f"✅ Riassunto generato per {user_id}")
            
        except Exception as e:
            print(f"Errore riassunto: {e}")

    def build_context(self, user_id: str, business_id: int, history: List[Dict], max_summaries: int = 3) -> str:
        """Costruisce il contesto da passare all'AI"""
        parts = []
        
        # Recupera conversazione
        conv = self.db.conversations.find_one({
            "user_id": user_id, 
            "business_id": business_id
        })
        
        if conv:
            # Aggiungi riassunti se presenti
            summaries = json.loads(conv.get("summaries", "[]")) if conv.get("summaries") else []
            if summaries:
                recent_summaries = summaries[-max_summaries:]
                parts.append("RIASSUNTI RECENTI:\n" + "\n---\n".join(s["content"] for s in recent_summaries))
        
        # Aggiungi profilo cliente
        cust = self.db.customers.find_one({
            "user_id": user_id, 
            "business_id": business_id
        })
        
        if cust:
            profile_parts = []
            if cust.get('name'):
                profile_parts.append(f"Nome: {cust['name']}")
            if cust.get('email'):
                profile_parts.append(f"Email: {cust['email']}")
            if profile_parts:
                parts.append(f"PROFILO CLIENTE: {', '.join(profile_parts)}")
        
        # Aggiungi storia recente
        if history:
            recent_history = history[-6:]  # Ultimi 6 messaggi
            history_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent_history])
            parts.append(f"STORIA RECENTE:\n{history_text}")
        
        return "\n\n".join(parts) if parts else ""