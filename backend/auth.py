import os
import datetime
import jwt
import bcrypt
from fastapi import Depends, HTTPException, Header, Request
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-prior-auth-system-2026-secure-jwt")

def issue_token(user_id: str, role: str) -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def require_role(required_role: str):
    def dependency(request: Request, authorization: str = Header(None)):
        token = None
        if authorization:
            token = authorization.replace("Bearer ", "").strip()
        elif "token" in request.cookies:
            token = request.cookies.get("token")
            
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token missing")
            
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
            
        if payload.get("role") != required_role:
            raise HTTPException(status_code=403, detail="Forbidden for this role")
            
        return payload
    return dependency

def get_current_user(request: Request, authorization: str = Header(None)):
    token = None
    if authorization:
        token = authorization.replace("Bearer ", "").strip()
    elif "token" in request.cookies:
        token = request.cookies.get("token")
        
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token missing")
        
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
