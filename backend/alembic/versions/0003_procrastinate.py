"""Procrastinate job queue schema (platform/runtime).

Procrastinate keeps its own tables, functions and types in ``public``; this migration
applies its shipped schema so a database upgrade is the only setup step.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Removes everything Procrastinate created, whatever its version added.
_REMOVE_PROCRASTINATE = r"""
DO $$
DECLARE obj record;
BEGIN
    FOR obj IN SELECT tablename FROM pg_tables
               WHERE schemaname = 'public' AND tablename LIKE 'procrastinate\_%'
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', obj.tablename);
    END LOOP;
    FOR obj IN SELECT p.oid::regprocedure AS sig FROM pg_proc p
               JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'public' AND p.proname LIKE 'procrastinate\_%'
    LOOP
        EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', obj.sig);
    END LOOP;
    FOR obj IN SELECT t.typname FROM pg_type t
               JOIN pg_namespace n ON n.oid = t.typnamespace
               WHERE n.nspname = 'public' AND t.typname LIKE 'procrastinate\_%'
                 AND t.typtype IN ('c', 'e')
    LOOP
        EXECUTE format('DROP TYPE IF EXISTS public.%I CASCADE', obj.typname);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(SchemaManager.get_schema())


def downgrade() -> None:
    op.execute(_REMOVE_PROCRASTINATE)
