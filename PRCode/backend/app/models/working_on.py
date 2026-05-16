from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class WorkingOnIssue(Base):
    __tablename__ = "working_on_issues"

    id:             Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id:        Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    repo_name:      Mapped[str] = mapped_column(String, index=True)
    issue_number:   Mapped[int] = mapped_column(Integer, index=True)
    active:         Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
