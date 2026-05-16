import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id:         Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String)   # pull_request, push etc
    repo_name:  Mapped[str] = mapped_column(String)
    payload:    Mapped[str] = mapped_column(Text)      # raw JSON
    status:     Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))