"""
Authentication and user models.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal


class UserBase(BaseModel):
    """Base user model."""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Model for user registration."""
    password: str = Field(..., min_length=6)


class UserInDB(UserBase):
    """User model as stored in database."""
    id: int
    is_active: bool = True
    hashed_password: str


class User(UserBase):
    """User model returned to clients (without password)."""
    id: int
    is_active: bool = True
    role: Literal["admin", "operator", "viewer"] = "viewer"
    permissions: list[str] = Field(default_factory=list)
    use_custom_permissions: bool = False
    custom_permissions: list[str] = Field(default_factory=list)
    auth_source: Literal["local", "ldap"] = "local"
    telegram_id: Optional[int] = None
    assigned_database: Optional[str] = None
    mailbox_email: Optional[EmailStr] = None
    mailbox_login: Optional[str] = None
    mail_signature_html: Optional[str] = None
    mail_is_configured: bool = False


class LoginRequest(BaseModel):
    """Login request model."""
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Login response with token and user info."""
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: User
    session_id: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    old_password: str
    new_password: str = Field(..., min_length=6)


class UserCreateRequest(BaseModel):
    """Admin request model to create user."""
    username: str = Field(..., min_length=3, max_length=50)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Literal["admin", "operator", "viewer"] = "viewer"
    auth_source: Literal["local", "ldap"] = "local"
    telegram_id: Optional[int] = None
    assigned_database: Optional[str] = None
    is_active: bool = True
    use_custom_permissions: bool = False
    custom_permissions: list[str] = Field(default_factory=list)
    mailbox_email: Optional[EmailStr] = None
    mailbox_login: Optional[str] = None
    mailbox_password: Optional[str] = Field(default=None, min_length=1, max_length=256)
    mail_signature_html: Optional[str] = None

    @field_validator(
        "mailbox_email",
        "email",
        "full_name",
        "assigned_database",
        "password",
        "mailbox_login",
        "mailbox_password",
        "mail_signature_html",
        mode="before",
    )
    @classmethod
    def _blank_str_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("telegram_id", mode="before")
    @classmethod
    def _blank_telegram_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class UserUpdateRequest(BaseModel):
    """Admin request model to update user."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[Literal["admin", "operator", "viewer"]] = None
    auth_source: Optional[Literal["local", "ldap"]] = None
    telegram_id: Optional[int] = None
    assigned_database: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    use_custom_permissions: Optional[bool] = None
    custom_permissions: Optional[list[str]] = None
    mailbox_email: Optional[EmailStr] = None
    mailbox_login: Optional[str] = None
    mailbox_password: Optional[str] = Field(default=None, min_length=1, max_length=256)
    mail_signature_html: Optional[str] = None

    @field_validator(
        "mailbox_email",
        "email",
        "full_name",
        "assigned_database",
        "mailbox_login",
        "mailbox_password",
        "mail_signature_html",
        mode="before",
    )
    @classmethod
    def _blank_str_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("telegram_id", mode="before")
    @classmethod
    def _blank_telegram_to_none(cls, value):
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


class SessionInfo(BaseModel):
    """Active session information."""
    session_id: str
    user_id: int
    username: str
    role: str = "viewer"
    ip_address: str = ""
    user_agent: str = ""
    created_at: str
    last_seen_at: str
    expires_at: str
    is_active: bool = True
