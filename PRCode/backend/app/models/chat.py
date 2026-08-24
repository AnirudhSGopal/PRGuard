import uuid
from datetime import datetime
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Session(Base):
    __tablename__ = "sessions"

    id:         Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:    Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    repo_name:  Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Message(Base):
    __tablename__ = "messages"

    id:         Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"))
    role:       Mapped[str] = mapped_column(String)  # 'user' or 'assistant'
    content:    Mapped[str] = mapped_column(Text)
    chunks:     Mapped[str] = mapped_column(Text, nullable=True)  # which code chunks were used
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))