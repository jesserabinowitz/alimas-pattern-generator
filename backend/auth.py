import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY  = os.getenv("JWT_SECRET", "dev-secret-change-me")
ALGORITHM   = "HS256"
EXPIRE_DAYS = 30

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, ALGORITHM)


def _decode_token(token: str) -> int:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return int(payload["sub"])


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int | None:
    """Returns user_id or None — never raises, callers decide if auth is required."""
    if not token:
        return None
    try:
        return _decode_token(token)
    except JWTError:
        return None


def require_user(user_id: int | None = Depends(get_current_user_id)) -> int:
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id
