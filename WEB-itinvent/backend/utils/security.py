"""Security utilities for JWT token management."""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from pydantic import BaseModel

from backend.config import config


class Token(BaseModel):
    """JWT token response model."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from JWT token."""
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None
    session_id: Optional[str] = None
    telegram_id: Optional[int] = None


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in token (e.g., {"sub": username})
        expires_delta: Optional expiration time override

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.jwt.access_token_expire_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.jwt.secret_key, algorithm=config.jwt.algorithm)

    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and verify a JWT access token.

    Args:
        token: JWT token string

    Returns:
        TokenData if valid, None otherwise
    """
    if not token:
        return None

    secret_keys = [config.jwt.secret_key] + list(config.jwt.previous_secret_keys or [])
    for key in secret_keys:
        if not key:
            continue
        try:
            payload = jwt.decode(token, key, algorithms=[config.jwt.algorithm])
            username: str = payload.get("sub")
            user_id: int = payload.get("user_id")
            role: Optional[str] = payload.get("role")
            session_id: Optional[str] = payload.get("session_id")
            telegram_id: Optional[int] = payload.get("telegram_id")

            if username is None:
                return None

            return TokenData(
                username=username,
                user_id=user_id,
                role=role,
                session_id=session_id,
                telegram_id=telegram_id,
            )
        except JWTError:
            continue
    return None
