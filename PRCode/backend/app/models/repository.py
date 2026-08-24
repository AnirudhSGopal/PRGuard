from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base

class ConnectedRepository(Base):
    __tablename__ = "connected_repositories"

    id:             Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id:        Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    github_repo_id: Mapped[str] = mapped_column(String, index=True)
    repo_name:      Mapped[str] = mapped_column(String)
    connected_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
