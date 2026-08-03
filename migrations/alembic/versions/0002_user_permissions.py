"""Add password_hash column and user repository permissions table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-02T22:00:00Z
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Alter users table to add password_hash column
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
    
    # 2. Create user_repository_permissions table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_repository_permissions (
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, repository_id)
        )
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_repository_permissions")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash")
