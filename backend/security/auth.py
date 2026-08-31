import os
import jwt
import hashlib
import binascii
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from fastapi import HTTPException, Header, Depends
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import User

JWT_SECRET_KEY = os.environ.get("JWT_SECRET", "saathicare_production_secret_key_2026_scst")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

def utcnow():
    return datetime.now(timezone.utc)

# ─────────────────────────────────────────────
# 1. PASSWORD HASHING (PBKDF2 SHA-256)
# ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random 16-byte salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 64000)
    return binascii.hexlify(salt).decode('ascii') + "$" + binascii.hexlify(key).decode('ascii')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against PBKDF2 hashed password string."""
    try:
        salt_str, key_str = hashed_password.split("$")
        salt = binascii.unhexlify(salt_str)
        expected_key = binascii.unhexlify(key_str)
        key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 64000)
        return hmac_compare(key, expected_key)
    except Exception:
        return False

def hmac_compare(a: bytes, b: bytes) -> bool:
    """Constant time byte string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0

# ─────────────────────────────────────────────
# 2. JWT TOKEN ISSUANCE & VERIFICATION
# ─────────────────────────────────────────────

def create_access_token(
    user_id: str,
    role: str,
    jurisdiction: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate signed JWT access token with user_id, role, jurisdiction claims."""
    expire = utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    payload = {
        "sub": str(user_id),
        "role": role.lower().replace(" ", "_"),
        "jurisdiction": jurisdiction,
        "iat": utcnow(),
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and verify JWT signature and expiry. Returns claims payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token signature")

# ─────────────────────────────────────────────
# 3. DEMO USER SEEDING
# ─────────────────────────────────────────────

DEMO_USERS = [
    {
        "username": "district_officer",
        "password": "District@123",
        "role": "district_officer",
        "jurisdiction": "Hathras",
        "full_name": "District Officer Hathras",
        "email": "district.officer@hathras.gov.in"
    },
    {
        "username": "state_officer",
        "password": "State@123",
        "role": "state_officer",
        "jurisdiction": "Uttar Pradesh",
        "full_name": "State SC/ST Commission Officer",
        "email": "state.officer@up.gov.in"
    },
    {
        "username": "counselor_ananya",
        "password": "Demo@123",
        "role": "counsellor",
        "jurisdiction": "Hathras",
        "full_name": "Dr. Ananya Rao",
        "email": "counselor@saathicare.demo"
    },
    {
        "username": "national_admin",
        "password": "Admin@123",
        "role": "national_admin",
        "jurisdiction": "National",
        "full_name": "National Oversight Admin",
        "email": "admin@saathicare.gov.in"
    }
]

def seed_demo_users(db: Optional[Session] = None):
    """Seed standard demo users if not present."""
    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True
    try:
        from sqlalchemy import or_
        for u in DEMO_USERS:
            existing = db.query(User).filter(
                or_(User.username == u["username"], User.email == u["email"])
            ).first()
            if existing:
                existing.username = u["username"]
                existing.role = u["role"]
                existing.jurisdiction = u["jurisdiction"]
                existing.full_name = u["full_name"]
                if not existing.hashed_password:
                    existing.hashed_password = hash_password(u["password"])
            else:
                user = User(
                    username=u["username"],
                    hashed_password=hash_password(u["password"]),
                    role=u["role"],
                    jurisdiction=u["jurisdiction"],
                    full_name=u["full_name"],
                    email=u["email"]
                )
                db.add(user)
        db.commit()
    finally:
        if close_session:
            db.close()

from typing import Dict, Any, Optional, Annotated

def get_current_user_claims(authorization: Optional[str] = Header(None, alias="Authorization")) -> Dict[str, Any]:
    """Dependency extracting and verifying signed JWT token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]
    return decode_access_token(token)
