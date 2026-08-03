"""One-time startup wiring. Idempotent — runs on every API boot."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from crv_core.db import session_factory


def run_db_migrations() -> None:
    """Run Alembic database migrations up to head dynamically at startup."""
    import os
    from pathlib import Path
    from alembic.config import Config
    from alembic import command
    
    try:
        cur = Path(__file__).resolve().parent
        ini_path = None
        for _ in range(6):
            candidate = cur / "alembic.ini"
            if candidate.is_file():
                ini_path = str(candidate)
                break
            candidate_mig = cur / "migrations" / "alembic.ini"
            if candidate_mig.is_file():
                ini_path = str(candidate_mig)
                break
            cur = cur.parent
            
        if not ini_path:
            print("[startup] warning: alembic.ini not found, skipping migration check.")
            return
            
        cfg = Config(ini_path)
        
        # Override script_location to be an absolute path relative to ini location
        migrations_dir = Path(ini_path).parent / "alembic"
        if not migrations_dir.is_dir():
            migrations_dir = Path(ini_path).parent / "migrations" / "alembic"
            
        cfg.set_main_option("script_location", str(migrations_dir))
        
        from crv_core.settings import get_settings
        settings = get_settings()
        db_url = settings.database_url.replace("+asyncpg", "")
        cfg.set_main_option("sqlalchemy.url", db_url)
        
        print("[startup] running database migrations via Alembic...")
        command.upgrade(cfg, "head")
        print("[startup] migrations completed successfully.")
    except Exception as e:
        print(f"[startup] warning: migration auto-run failed: {e}")


async def ensure_default_org() -> str:
    """Ensure a single 'default' org exists so the UI has something to hang off."""
    async with session_factory()() as db:
        existing = (await db.execute(
            text("SELECT id FROM organizations WHERE slug = 'default'")
        )).scalar_one_or_none()
        
        if existing:
            oid = str(existing)
        else:
            oid = str(uuid.uuid4())
            await db.execute(
                text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Default', 'default')"),
                {"id": oid},
            )
            await db.commit()

        import hashlib
        import os
        
        admin_pw = os.environ.get("SEED_ADMIN_PASSWORD", "admin123")
        user_pw = os.environ.get("SEED_USER_PASSWORD", "user123")
        
        def _hash_pw(password: str) -> str:
            salt = bytes.fromhex("1234567890abcdef1234567890abcdef")
            pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
            return f"pbkdf2_sha256$100000${salt.hex()}${pw_hash.hex()}"

        admin_existing = (await db.execute(
            text("SELECT id FROM users WHERE email = 'admin@prvet.review'")
        )).scalar_one_or_none()
        
        if not admin_existing:
            await db.execute(
                text("""
                    INSERT INTO users (id, org_id, email, display_name, role, password_hash)
                    VALUES (:id, :org, 'admin@prvet.review', 'System Admin', 'admin', :pw)
                """),
                {"id": str(uuid.uuid4()), "org": oid, "pw": _hash_pw(admin_pw)}
            )
            
        user_existing = (await db.execute(
            text("SELECT id FROM users WHERE email = 'user@prvet.review'")
        )).scalar_one_or_none()
        
        if not user_existing:
            await db.execute(
                text("""
                    INSERT INTO users (id, org_id, email, display_name, role, password_hash)
                    VALUES (:id, :org, 'user@prvet.review', 'Standard User', 'member', :pw)
                """),
                {"id": str(uuid.uuid4()), "org": oid, "pw": _hash_pw(user_pw)}
            )
            
        await db.commit()
        return oid


async def clean_stale_runs() -> int:
    """Mark any 'running' rows as failed — the process holding them is gone.

    Runs in-process asyncio tasks (baseline, ad-hoc review) get killed when
    uvicorn --reload restarts, when we crash, or when the pod is rescheduled.
    Their DB rows would otherwise sit at 'running' forever, blocking retries
    and lying to the UI. Wipe on boot."""
    err = json.dumps({"reason": "server_restarted",
                       "hint": "Task was interrupted (uvicorn reload, crash, or pod restart). Click Re-run."})
    async with session_factory()() as db:
        r = await db.execute(text("""
            UPDATE runs
               SET status = 'failed',
                   finished_at = COALESCE(finished_at, now()),
                   error = CAST(:e AS jsonb)
             WHERE status IN ('running', 'queued')
        """), {"e": err})
        await db.commit()
        return r.rowcount or 0
