"""Admin utility endpoints — LLM connectivity test, recent runs, audit log."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text

from crv_adapters.llm import LlmError, client_from_org
from crv_core.db import session_factory
from crv_api.routers.auth import get_admin_user

router = APIRouter(dependencies=[Depends(get_admin_user)])


class LlmTestOut(BaseModel):
    ok: bool
    model: str
    latency_ms: int | None
    error: str | None


@router.post("/admin/llm/test", response_model=LlmTestOut)
async def llm_test() -> LlmTestOut:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    providers = list(row["ps"] or [])
    try:
        client = client_from_org(providers, timeout_s=15)
        resp = await client.chat(
            "fast",  # resolves via role_map
            [{"role": "user", "content": "Reply with the single word: pong."}],
            temperature=0.0,
        )
        return LlmTestOut(ok=True, model=resp.model, latency_ms=resp.latency_ms, error=None)
    except LlmError as e:
        return LlmTestOut(ok=False, model="?", latency_ms=None, error=str(e))


@router.get("/runs")
async def recent_runs(limit: int = 25) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT r.id::text, r.repo_id::text, repo.full_name AS repo,
                   r.run_type, r.status, r.commit_sha, r.duration_ms, r.stats,
                   r.created_at, r.finished_at
            FROM runs r JOIN repositories repo ON repo.id = r.repo_id
            ORDER BY r.created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/audit")
async def recent_audit(limit: int = 100) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id, actor_type, actor_id, action, resource_type, resource_id,
                   metadata, ip_address, created_at
            FROM audit_log ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


class GenerateRuleIn(BaseModel):
    description: str
    language: str


@router.post("/admin/rules/generate")
async def generate_rule(body: GenerateRuleIn) -> dict:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    providers = list(row["ps"] or [])
    
    prompt = (
        "You are an expert static analysis rules engineer. The user wants to write a custom lint/security rule.\n"
        f"Language context: {body.language}\n"
        f"Description / intent: {body.description}\n\n"
        "Generate a custom rule matching this requirement. Output JSON ONLY containing these fields:\n"
        "- id: a unique identifier in kebab-case, string (matches ^[a-z][a-z0-9_-]+$)\n"
        "- message: the diagnostic/warning message to show developers, string\n"
        "- severity: one of 'critical', 'high', 'medium', 'low', 'info'\n"
        "- category: one of 'security', 'bug', 'performance', 'maintainability', 'style', 'dependency', 'test'\n"
        "- pattern: the search pattern (can be semgrep-style print($X) or tree-sitter query pattern or regex), string\n"
        "- pattern_not: optional exclusion pattern, string or null\n"
        "- fix: optional auto-fix replacement string or null\n\n"
        "Reply with pure JSON. Do not include markdown code block syntax."
    )
    
    try:
        client = client_from_org(providers, timeout_s=30)
        resp = await client.chat(
            "deep",
            [{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        text_content = resp.text
        import re
        m = re.search(r"\{.*\}", text_content, re.DOTALL)
        if m:
            clean_json = m.group(0)
        else:
            clean_json = text_content
            
        import json
        rule_data = json.loads(clean_json)
        return rule_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM rule generation failed: {e}")


class ParseAstIn(BaseModel):
    code: str
    language: str


@router.post("/admin/ast/parse")
async def parse_ast(body: ParseAstIn) -> dict:
    lang = body.language.lower()
    if lang == "python":
        import ast
        try:
            tree = ast.parse(body.code)
            
            def _ast_to_tree(node, name=""):
                if isinstance(node, list):
                    children = []
                    for i, x in enumerate(node):
                        children.append(_ast_to_tree(x, f"[{i}]"))
                    return {
                        "type": "list",
                        "text": name,
                        "children": children
                    }
                if not hasattr(node, "_fields"):
                    return {
                        "type": "literal",
                        "text": f"{name}: {node}" if name else str(node)
                    }
                
                children = []
                for field in node._fields:
                    val = getattr(node, field)
                    if val is not None:
                        children.append(_ast_to_tree(val, field))
                
                return {
                    "type": node.__class__.__name__,
                    "line": getattr(node, "lineno", None),
                    "text": name or None,
                    "children": children
                }
                
            return {"status": "success", "ast": _ast_to_tree(tree)}
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    elif lang in ("javascript", "typescript", "tsx"):
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_javascript as tsjs
            import tree_sitter_typescript as tsts
            
            if lang == "javascript":
                parser = Parser(Language(tsjs.language()))
            elif lang == "typescript":
                parser = Parser(Language(tsts.language_typescript()))
            else:
                parser = Parser(Language(tsts.language_tsx()))
                
            tree = parser.parse(body.code.encode("utf-8"))
            
            def _ts_to_dict(node):
                text_val = ""
                if not node.children or node.type in ("identifier", "property_identifier", "number", "string", "comment"):
                    try:
                        text_val = node.text.decode("utf-8")
                    except Exception:
                        pass
                
                return {
                    "type": node.type,
                    "line": node.start_point[0] + 1,
                    "col": node.start_point[1],
                    "text": text_val or None,
                    "children": [_ts_to_dict(c) for c in node.children]
                }
                
            return {"status": "success", "ast": _ts_to_dict(tree.root_node)}
        except Exception as e:
            return {"status": "error", "error": str(e)}
            
    else:
        return {"status": "error", "error": f"AST parsing not supported for language: {lang}"}


class UserCreateIn(BaseModel):
    email: str
    display_name: str | None = None
    role: str = "member"
    is_active: bool = True
    password: str
    permitted_repos: list[str] = []

class UserUpdateIn(BaseModel):
    display_name: str | None = None
    role: str = "member"
    is_active: bool = True
    password: str | None = None
    permitted_repos: list[str] = []

class UserOut(BaseModel):
    id: str
    email: str
    display_name: str | None
    role: str
    is_active: bool
    permitted_repos: list[str]

@router.get("/admin/users", response_model=list[UserOut])
async def list_users() -> list[UserOut]:
    async with session_factory()() as db:
        users = (await db.execute(text("""
            SELECT id::text, email, display_name, role, is_active
            FROM users ORDER BY created_at DESC
        """))).mappings().all()
        
        out = []
        for u in users:
            repo_ids = (await db.execute(text("""
                SELECT repository_id::text FROM user_repository_permissions
                WHERE user_id = :uid
            """), {"uid": u["id"]})).scalars().all()
            
            out.append(UserOut(
                id=u["id"],
                email=u["email"],
                display_name=u["display_name"],
                role=u["role"],
                is_active=u["is_active"],
                permitted_repos=list(repo_ids)
            ))
        return out

@router.post("/admin/users", response_model=UserOut, status_code=201)
async def create_user(body: UserCreateIn) -> UserOut:
    import hashlib
    import uuid

    def _hash_pw(password: str) -> str:
        salt = bytes.fromhex("1234567890abcdef1234567890abcdef")
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return f"pbkdf2_sha256$100000${salt.hex()}${pw_hash.hex()}"

    async with session_factory()() as db:
        existing = (await db.execute(text("""
            SELECT id FROM users WHERE LOWER(email) = LOWER(:e)
        """), {"e": body.email})).scalar_one_or_none()
        if existing:
            raise HTTPException(400, "User with this email already exists")

        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug = 'default'"))).scalar_one_or_none()
        if not org_id:
            raise HTTPException(500, "Default organization not found")

        uid = str(uuid.uuid4())
        await db.execute(
            text("""
                INSERT INTO users (id, org_id, email, display_name, role, is_active, password_hash)
                VALUES (:id, :org, :email, :name, :role, :active, :pw)
            """),
            {
                "id": uid,
                "org": str(org_id),
                "email": body.email,
                "name": body.display_name,
                "role": body.role,
                "active": body.is_active,
                "pw": _hash_pw(body.password)
            }
        )

        for rid in body.permitted_repos:
            await db.execute(text("""
                INSERT INTO user_repository_permissions (user_id, repository_id)
                VALUES (:uid, :rid)
                ON CONFLICT DO NOTHING
            """), {"uid": uid, "rid": rid})

        await db.commit()

        return UserOut(
            id=uid,
            email=body.email,
            display_name=body.display_name,
            role=body.role,
            is_active=body.is_active,
            permitted_repos=body.permitted_repos
        )

@router.put("/admin/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UserUpdateIn) -> UserOut:
    import hashlib
    def _hash_pw(password: str) -> str:
        salt = bytes.fromhex("1234567890abcdef1234567890abcdef")
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
        return f"pbkdf2_sha256$100000${salt.hex()}${pw_hash.hex()}"

    async with session_factory()() as db:
        user = (await db.execute(text("""
            SELECT id::text, email FROM users WHERE id = :id
        """), {"id": user_id})).mappings().one_or_none()
        
        if not user:
            raise HTTPException(404, "User not found")

        if body.password:
            await db.execute(
                text("""
                    UPDATE users
                    SET display_name = :name, role = :role, is_active = :active, password_hash = :pw
                    WHERE id = :id
                """),
                {
                    "id": user_id,
                    "name": body.display_name,
                    "role": body.role,
                    "active": body.is_active,
                    "pw": _hash_pw(body.password)
                }
            )
        else:
            await db.execute(
                text("""
                    UPDATE users
                    SET display_name = :name, role = :role, is_active = :active
                    WHERE id = :id
                """),
                {
                    "id": user_id,
                    "name": body.display_name,
                    "role": body.role,
                    "active": body.is_active
                }
            )

        await db.execute(text("""
            DELETE FROM user_repository_permissions WHERE user_id = :uid
        """), {"uid": user_id})

        for rid in body.permitted_repos:
            await db.execute(text("""
                INSERT INTO user_repository_permissions (user_id, repository_id)
                VALUES (:uid, :rid)
                ON CONFLICT DO NOTHING
            """), {"uid": user_id, "rid": rid})

        await db.commit()

        return UserOut(
            id=user_id,
            email=user["email"],
            display_name=body.display_name,
            role=body.role,
            is_active=body.is_active,
            permitted_repos=body.permitted_repos
        )

@router.delete("/admin/users/{user_id}", status_code=204)
async def delete_user(user_id: str) -> None:
    async with session_factory()() as db:
        user_exists = (await db.execute(text("SELECT 1 FROM users WHERE id = :id"), {"id": user_id})).scalar_one_or_none()
        if not user_exists:
            raise HTTPException(404, "User not found")
            
        await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await db.commit()


