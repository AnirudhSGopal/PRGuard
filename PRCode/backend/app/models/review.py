import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class Review(Base):
    __tablename__ = "reviews"

    id:           Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:      Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    repo_name:    Mapped[str] = mapped_column(String)
    issue_number: Mapped[int] = mapped_column()
    issue_title:  Mapped[str] = mapped_column(String)
    answer:       Mapped[str] = mapped_column(Text)
    fix:          Mapped[str] = mapped_column(Text, nullable=True)
    chunks_used:  Mapped[str] = mapped_column(Text, nullable=True)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))