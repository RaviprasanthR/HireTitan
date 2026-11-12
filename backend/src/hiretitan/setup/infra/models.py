"""ORM model for ``app.settings`` (data-model.md): a single row."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import Base


class SettingsRow(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id", name="singleton"),
        CheckConstraint("char_length(display_name) BETWEEN 1 AND 120", name="display_name_length"),
    )

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default=text("true"))
    display_name: Mapped[str | None] = mapped_column(Text)
    setup_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
