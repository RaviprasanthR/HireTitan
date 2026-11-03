"""Alembic environment: runs migrations online with a sync psycopg connection.

The URL is taken from the ``sqlalchemy.url`` option when a caller (the test
harness) sets it, else from ``DATABASE_URL`` or the ``POSTGRES_*`` settings.
Alembic's version table lives in schema ``app``, so the schema is created
before migrations run.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool, text

from hiretitan.platform.config.settings import Settings
from hiretitan.platform.db import APP_SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().database_url


def _include_name(name: str | None, type_: str, parent_names: object) -> bool:
    # Only our schema: LangGraph (lg) and Procrastinate manage their own tables.
    if type_ == "schema":
        return name == APP_SCHEMA
    return True


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {APP_SCHEMA}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=APP_SCHEMA,
            include_schemas=True,
            include_name=_include_name,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported")
run_migrations_online()
