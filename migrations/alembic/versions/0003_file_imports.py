"""File-level import edges + per-file reference resolution counters.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27T00:00:00Z
"""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_imports (
            id            UUID PRIMARY KEY,
            repo_id       UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            from_file_id  UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            to_file_id    UUID NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            line          INTEGER NOT NULL,
            specifier     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS file_imports_from_idx ON file_imports (repo_id, from_file_id);
        CREATE INDEX IF NOT EXISTS file_imports_to_idx ON file_imports (to_file_id);
        ALTER TABLE files ADD COLUMN IF NOT EXISTS resolved_refs INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE files ADD COLUMN IF NOT EXISTS unresolved_refs INTEGER NOT NULL DEFAULT 0;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS file_imports;
        ALTER TABLE files DROP COLUMN IF EXISTS resolved_refs;
        ALTER TABLE files DROP COLUMN IF EXISTS unresolved_refs;
    """)
