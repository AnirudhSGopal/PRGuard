import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class User(Base):
    __tablename__ = "users"

    id:           Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    github_id:    Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    username:     Mapped[str] = mapped_column(String)
    email:        Mapped[Optional[str]] = mapped_column(String, unique=True, index=True, nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    role:         Mapped[str] = mapped_column(String(20), default="user", index=True)
    auth_provider: Mapped[str] = mapped_column(String(20), default="github", index=True)
    api_key:      Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url:   Mapped[Optional[str]] = mapped_column(String, nullable=True)
    access_token: Mapped[str] = mapped_column(String)
    session_token_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))