"""One way to put a stored resume file into a test database (feature 002f)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def add_resume_file(
    session: AsyncSession,
    name: str = "Backend_2025.pdf",
    status: str = "parsed",
    created_at: str | None = None,
) -> UUID:
    """Insert a ``resume_files`` row and return its id. Only the row is made, because that is all
    the job-search code reads; ``created_at`` (an ISO string) defaults to now."""
    columns = "id, kind, original_name, size_bytes, sha256, parse_status"
    values = "gen_random_uuid(), 'upload_pdf', :name, 1000, :sha, :status"
    params: dict[str, Any] = {"name": name, "sha": "a" * 64, "status": status}
    if created_at is not None:
        columns += ", created_at"
        values += ", CAST(:created_at AS timestamptz)"
        params["created_at"] = created_at
    row = await session.execute(
        text(f"INSERT INTO app.resume_files ({columns}) VALUES ({values}) RETURNING id"), params
    )
    return row.scalar_one()
