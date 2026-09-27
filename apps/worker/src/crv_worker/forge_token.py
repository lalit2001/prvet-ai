"""One place to turn a forge connection into a bearer token.

PAT connections keep `capabilities.dev_token`. GitHub App installations are
also forge_connections rows (capabilities.installation_id + app_uuid) whose
token is minted from the app's private key on demand."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from crv_adapters.forge.github_app import installation_token
from crv_core.db import session_factory


@dataclass
class ConnAuth:
    connection_id: str
    forge_type: str
    base_url: str
    token: str
    capabilities: dict
    is_app: bool
    webhook_secret: str | None


async def connection_auth(connection_id: str) -> ConnAuth:
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT forge_type, base_url, capabilities FROM forge_connections WHERE id = :id
        """), {"id": connection_id})).mappings().one_or_none()
        if row is None:
            raise LookupError(f"connection {connection_id} not found")
        caps = row["capabilities"] or {}
        if caps.get("installation_id") and caps.get("app_uuid"):
            app = (await db.execute(text("""
                SELECT app_id, credentials FROM forge_apps WHERE id = :id
            """), {"id": caps["app_uuid"]})).mappings().one_or_none()
            if app is None:
                raise LookupError("GitHub App for this installation was deleted")
            creds = app["credentials"] or {}
            token = await installation_token(str(app["app_id"]), creds["pem"], str(caps["installation_id"]),
                                             api_base=row["base_url"] or "https://api.github.com")
            return ConnAuth(connection_id, row["forge_type"], row["base_url"], token, caps, True, creds.get("webhook_secret"))
    token = caps.get("dev_token")
    if not token:
        raise LookupError("connection has no stored token")
    return ConnAuth(connection_id, row["forge_type"], row["base_url"], token, caps, False, caps.get("dev_webhook_secret"))
