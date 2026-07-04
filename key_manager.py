import time
import datetime
from sqlalchemy.orm import Session
from core.database import ApiKey

class KeyManager:
    def __init__(self, db: Session):
        self.db = db

    def get_available_key(self, max_rpm=5):
        keys = self.db.query(ApiKey).all()
        if not keys:
            raise Exception("Aucune clé API configurée")
        
        current_time = datetime.datetime.utcnow()
        
        for key in keys:
            if key.minute_start is None or (current_time - key.minute_start).total_seconds() > 60:
                key.request_count_minute = 0
                key.minute_start = current_time
            
            if key.request_count_minute < max_rpm:
                key.request_count_minute += 1
                key.last_used = current_time
                self.db.commit()
                return key.key_value
        
        raise Exception("Toutes les clés API ont atteint leur limite. Attendez une minute.")
