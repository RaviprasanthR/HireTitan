"""ORM model for ``app.settings`` (data-model.md): a single row."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column

from hiretitan.platform.db import Base


class SettingsRow(Base):
    __tablename__ = "settings"
    __table_args__ = (
        CheckConstraint("id", name="singleton"),
        CheckConstraint("budget_cap_usd >= 0", name="budget_cap_non_negative"),
    )

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default=text("true"))
    budget_cap_usd: Mapped[Decimal] = mapped_column(Numeric(8, 2), server_default=text("25.00"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
