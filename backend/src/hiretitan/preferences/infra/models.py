"""ORM model for ``app.preferences`` (data-model.md): a single row."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import Base


class PreferencesRow(Base):
    __tablename__ = "preferences"
    __table_args__ = (CheckConstraint("singleton", name="singleton"),)

    singleton: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default=text("true"))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
