from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy import text

import os
import jwt
from crv_core.db import session_factory

router = APIRouter()

JWT_SECRET = os.environ.get("JWT_SECRET", "crv-jwt-secret-keep-it-safe-for-dev")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()

class LoginIn(BaseModel):
    email: str
    password: str

class LoginOut(BaseModel):
    token: str
    role: str
    email: str
    display_name: str | None = None

def _verify_pw(password: str, hashed: str) -> bool:
    if not hashed or not hashed.startswith("pbkdf2_sha256$"):
        return False
    try:
        parts = hashed.split("$")
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        original_hash = bytes.fromhex(parts[3])
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
        return pw_hash == original_hash
    except Exception:
        return False

def _create_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=1)
    to_encode.update({"exp": int(expire.timestamp())})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

@router.post("/auth/login", response_model=LoginOut)
async def login(body: LoginIn) -> LoginOut:
    async with session_factory()() as db:
        user = (await db.execute(text("""
            SELECT id::text, email, role, display_name, password_hash
            FROM users WHERE LOWER(email) = LOWER(:e) AND is_active = true
        """), {"e": body.email})).mappings().one_or_none()
        
    if not user or not user["password_hash"]:
        raise HTTPException(401, "Invalid email or password")
        
    if not _verify_pw(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
        
    token = _create_token({
        "user_id": user["id"],
        "email": user["email"],
        "role": user["role"]
    })
    
    return LoginOut(
        token=token,
        role=user["role"],
        email=user["email"],
        display_name=user["display_name"]
    )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(401, "Invalid authentication token")
            
        async with session_factory()() as db:
            user = (await db.execute(text("""
                SELECT id::text, email, role, display_name
                FROM users WHERE id = :id AND is_active = true
            """), {"id": user_id})).mappings().one_or_none()
            
        if not user:
            raise HTTPException(401, "User not found or inactive")
            
        return dict(user)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")

async def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Access denied. Administrator privileges required.")
    return user

@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    return user

async def verify_repo_access(repo_id: str, user: dict, db) -> None:
    if user["role"] == "admin":
        return
    row = (await db.execute(text("""
        SELECT 1 FROM user_repository_permissions
        WHERE user_id = :uid AND repository_id = :rid
    """), {"uid": user["id"], "rid": repo_id})).scalar_one_or_none()
    if not row:
        raise HTTPException(403, "Access denied. You do not have permissions for this repository.")
