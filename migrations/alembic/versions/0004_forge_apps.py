"""GitHub App registrations. Installations are forge_connections rows
(capabilities.installation_id / app_uuid) so the review pipeline is unchanged.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27T12:00:00Z
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS forge_apps (
            id           UUID PRIMARY KEY,
            org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            forge_type   TEXT NOT NULL DEFAULT 'github',
            base_url     TEXT NOT NULL DEFAULT 'https://api.github.com',
            app_id       TEXT,
            slug         TEXT,
            name         TEXT,
            html_url     TEXT,
            client_id    TEXT,
            credentials  JSONB NOT NULL DEFAULT '{}',   -- pem, webhook_secret, client_secret (ponytail: move to SecretsAdapter refs)
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS forge_connections_installation_idx
            ON forge_connections ((capabilities->>'installation_id'));
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS forge_connections_installation_idx; DROP TABLE IF EXISTS forge_apps;")
