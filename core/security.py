from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from core.database import get_db, User
import os

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"])
security = HTTPBearer(auto_error=False)

def create_access_token(data: dict):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str, db: Session):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        phone: str = payload.get("sub")
        if phone is None:
            return None
        user = db.query(User).filter(User.phone_number == phone).first()
        return user
    except JWTError:
        return None

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    
    user = verify_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token invalide")
    
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Compte non vérifié")
    
    return user

def get_current_admin(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    return user
