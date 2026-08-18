import uuid
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from backend.db import get_system_db
from backend.auth import hash_password, verify_password, issue_token
from backend.rate_limiter import check_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/register")
def register(req: RegisterRequest):
    if req.role not in ['initiator', 'insurer']:
        raise HTTPException(status_code=400, detail="Invalid role. Must be initiator or insurer.")
    
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE email = %s", (req.email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Email already registered")
            
            user_id = str(uuid.uuid4())
            pwd_hash = hash_password(req.password)
            cur.execute(
                "INSERT INTO users (user_id, email, password_hash, role, full_name) VALUES (%s, %s, %s, %s, %s)",
                (user_id, req.email, pwd_hash, req.role, req.full_name)
            )
        conn.commit()
        return {"message": "User registered successfully", "user_id": user_id}
    finally:
        conn.close()

@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    conn = get_system_db()
    try:
        with conn.cursor() as cur:
            # Rate limit check
            client_ip = request.client.host if request.client else "unknown"
            if not check_rate_limit(cur, client_ip, "/auth/login"):
                raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait.")
            
            cur.execute("SELECT user_id, password_hash, role, full_name FROM users WHERE email = %s", (req.email,))
            user = cur.fetchone()
            if not user or not verify_password(req.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            token = issue_token(user["user_id"], user["role"])
            # Set httpOnly cookie
            response.set_cookie(
                key="token",
                value=token,
                httponly=True,
                samesite="lax",
                secure=False,  # set True in prod HTTPS
                max_age=28800
            )
            return {
                "token": token, 
                "role": user["role"], 
                "user_id": user["user_id"],
                "full_name": user["full_name"] or ("Dr. Sarah Chen" if user["role"] == "initiator" else "Insurer Reviewer")
            }
    finally:
        conn.close()

@router.get("/me")
def get_me(request: Request):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    import jwt
    from backend.auth import SECRET_KEY
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        conn = get_system_db()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, email, role, full_name FROM users WHERE user_id = %s", (payload["user_id"],))
            user = cur.fetchone()
            if user:
                return user
        conn.close()
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="token")
    return {"message": "Logged out successfully"}
