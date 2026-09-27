"""PR review job — graph-aware, two-pass.

  graph    diff lines → changed symbols → callers (blast radius) from the indexed graph
  sast     Semgrep on the changed files (bundled + UI-authored rules)
  triage   fast model routes each file: skip | fast | deep (obvious cases decided without a model)
  review   fast/deep model per file, with callers packed into the prompt
  verify   fast model re-checks critical/high LLM findings; unconfirmed ones are dropped
  persist  dedupe SAST vs LLM, stable fingerprints, auto-resolve findings that vanished
  gate     risk score + gate decision → GitHub check run (App) or commit status (PAT)
  post     one batched review: summary, blast-radius table, inline comments

The graph comes from the latest baseline of the default branch — close enough for
callers; a per-PR head-SHA reindex is the upgrade path (ROADMAP A3)."""
from __future__ import annotations

import base64
import json
import re
import tempfile
import uuid
from pathlib import Path

import httpx
from sqlalchemy import text

from crv_adapters.forge.github_app import create_check_run
from crv_core.db import session_factory
from crv_core.settings import get_settings
from crv_worker.analysis import policy
from crv_worker.analysis.llm_review import review, triage_files, verify_findings
from crv_worker.analysis.sast import run_semgrep
from crv_worker.context.blast_radius import blast_radius, symbols_touching
from crv_worker.forge_token import connection_auth

_GH = "https://api.github.com"


async def run(ctx, connection_id: str, pr_number: int, repo_full_name: str) -> dict:
    print(f"[pr_review] Starting PR review for {repo_full_name} PR #{pr_number}")
    settings = get_settings()
    try:
        auth = await connection_auth(connection_id)
    except LookupError as e:
        print(f"[pr_review] Error: {e}")
        return {"status": "failed", "error": str(e)}
    api_base = auth.base_url if auth.base_url and auth.base_url.startswith("http") else _GH
    headers = {"Authorization": f"Bearer {auth.token}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}

    async with session_factory()() as db:
        repo_row = (await db.execute(text("""
            SELECT id::text, config FROM repositories WHERE connection_id = :cid AND full_name = :fn
        """), {"cid": connection_id, "fn": repo_full_name})).mappings().one_or_none()
        if repo_row is None:
            return {"status": "failed", "error": f"repo {repo_full_name} not enabled"}
        repo_id = repo_row["id"]
        repo_cfg = (repo_row["config"] or {}).get("review", {})
        org = (await db.execute(text(
            "SELECT COALESCE(settings->'custom_rules', '[]'::jsonb) AS rules FROM organizations WHERE slug='default'"
        ))).mappings().one()
        custom_rules = list(org["rules"] or [])
    block_severity = repo_cfg.get("block_severity", settings.gate_block_severity)
    min_conf = float(repo_cfg.get("min_confidence", settings.min_confidence))
    guidelines = repo_cfg.get("guidelines") or ""

    # ── fetch PR + files + head contents ────────────────────────────────────
    async with httpx.AsyncClient(timeout=30) as h:
        pr = (await h.get(f"{api_base}/repos/{repo_full_name}/pulls/{pr_number}", headers=headers)).json()
        files = (await h.get(f"{api_base}/repos/{repo_full_name}/pulls/{pr_number}/files?per_page=100", headers=headers)).json()
        if not isinstance(pr, dict) or not isinstance(files, list):
            return {"status": "failed", "error": "unexpected github response"}
        head_sha = pr.get("head", {}).get("sha", "")
        files_to_review = [f for f in files if f.get("status") != "removed" and (f.get("patch") or "")][: settings.max_diff_files]
        contents: dict[str, str] = {}
        for f in files_to_review:
            url = f.get("contents_url")
            if not url:
                continue
            try:
                r = await h.get(url, headers=headers)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("encoding") == "base64" and d.get("content"):
                        contents[f["filename"]] = base64.b64decode(d["content"]).decode("utf-8", errors="replace")
            except Exception as e:  # noqa: BLE001
                print(f"[pr_review] could not fetch {f['filename']}: {e}")
    print(f"[pr_review] PR #{pr_number} @ {head_sha[:10]} · {len(files_to_review)} reviewable files")

    # ── run row ─────────────────────────────────────────────────────────────
    stats: dict = {"phase": "graph", "files_total": len(files), "files_reviewable": len(files_to_review), "phases": {}}
    run_id = str(uuid.uuid4())
    async with session_factory()() as db:
        key = f"pr:{repo_id}:{pr_number}:{head_sha}"
        existing = (await db.execute(text("SELECT id FROM runs WHERE idempotency_key = :key"), {"key": key})).first()
        if existing:
            run_id = str(existing[0])
            await db.execute(text("""UPDATE runs SET status='running', started_at=now(), finished_at=NULL, error=NULL,
                                     stats=CAST(:s AS jsonb) WHERE id=:id"""), {"id": run_id, "s": json.dumps(stats)})
        else:
            await db.execute(text("""
                INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha, pr_number, idempotency_key, started_at, stats)
                VALUES (:id, :rid, 'pr_review', 'webhook', 'running', :sha, :pr, :key, now(), CAST(:s AS jsonb))
            """), {"id": run_id, "rid": repo_id, "sha": head_sha, "pr": pr_number, "key": key, "s": json.dumps(stats)})
        await db.commit()

    async def phase(name: str, **extra) -> None:
        stats["phase"] = name
        stats["phases"][name] = {**stats["phases"].get(name, {}), **extra}
        async with session_factory()() as db:
            await db.execute(text("UPDATE runs SET stats = CAST(:s AS jsonb) WHERE id = :id"),
                             {"id": run_id, "s": json.dumps(stats, default=str)})
            await db.commit()

    # ── graph: changed symbols + blast radius ───────────────────────────────
    changed_by_file: dict[str, list[dict]] = {}
    callers_by_file: dict[str, list[dict]] = {}
    blast_rows: list[dict] = []
    async with session_factory()() as db:
        for f in files_to_review:
            touched = await symbols_touching(db, repo_id, f["filename"], _get_modified_lines(f.get("patch") or ""))
            if touched:
                changed_by_file[f["filename"]] = touched
        all_changed = [s for lst in changed_by_file.values() for s in lst]
        if all_changed:
            blast_rows = await blast_radius(db, repo_id, [s["id"] for s in all_changed], depth=2, cap=40)
            target_file = {s["id"]: p for p, lst in changed_by_file.items() for s in lst}
            for r in blast_rows:
                callers_by_file.setdefault(target_file.get(r["target_id"], ""), []).append(r)
    sig_changes = sum(1 for f in files_to_review if policy.signature_changed(f.get("patch") or ""))
    await phase("sast", changed_symbols=len([s for l in changed_by_file.values() for s in l]),
                blast_radius=len(blast_rows), signature_changes=sig_changes)

    # ── SAST on the head-SHA contents ───────────────────────────────────────
    sast_findings: list[dict] = []
    sast_note = None
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for path, body in contents.items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        sast_findings, sast_note = await run_semgrep(root, list(contents), custom_rules)
    # keep only SAST hits on lines this PR touched (plus anything security-tagged)
    touched_lines = {f["filename"]: _get_modified_lines(f.get("patch") or "") for f in files_to_review}
    sast_findings = [s for s in sast_findings
                     if s.get("category") == "security" or (s.get("start_line") in touched_lines.get(s.get("_file_path"), set()))]
    for s in sast_findings:
        s["_affected"] = [c["symbol_key"] for c in changed_by_file.get(s["_file_path"], [])]
    await phase("triage", sast_findings=len(sast_findings), sast_note=sast_note)

    # ── triage ──────────────────────────────────────────────────────────────
    verdicts: dict[str, str] = {}
    ask: list[dict] = []
    for f in files_to_review:
        path, patch = f["filename"], f.get("patch") or ""
        pre = policy.triage_prefilter(path)
        if pre is None and len(callers_by_file.get(path, [])) >= 5:
            pre = "deep"
        if pre:
            verdicts[path] = pre
            continue
        ask.append({"path": path, "excerpt": "\n".join(patch.splitlines()[:40]),
                    "changed_symbols": [c["name"] for c in changed_by_file.get(path, [])][:10],
                    "callers": len(callers_by_file.get(path, [])),
                    "signature_changed": policy.signature_changed(patch)})
    model_verdicts = await triage_files(ask, run_id) if ask else {}
    for item in ask:
        verdicts[item["path"]] = (model_verdicts or {}).get(item["path"], "deep")
    counts = {k: sum(1 for v in verdicts.values() if v == k) for k in ("skip", "fast", "deep")}
    await phase("review", verdicts=counts, triage_model=model_verdicts is not None)
    print(f"[pr_review] triage → {counts}")

    # ── review ──────────────────────────────────────────────────────────────
    llm_findings: list[dict] = []
    per_file: list[str] = []
    for f in files_to_review:
        path, patch = f["filename"], f.get("patch") or ""
        verdict = verdicts.get(path, "deep")
        if verdict == "skip":
            per_file.append(f"- `{path}` — skipped (triage)")
            continue
        ctx_txt = (f"File: {path}\nPR #{pr_number}: {pr.get('title', '')}\n{pr.get('body', '') or ''}"
                   + (f"\n\nREPOSITORY REVIEW GUIDELINES:\n{guidelines}\n" if guidelines else "")
                   + _callers_context(changed_by_file.get(path, []), callers_by_file.get(path, []), contents))
        result = await review(code=patch, full_file=contents.get(path), language=_lang_from_path(path),
                              context=ctx_txt, run_id=run_id, model_role=verdict)
        if result.error:
            per_file.append(f"- `{path}` — review failed: {result.error}")
            continue
        for fd in result.findings:
            fd["source"] = "llm"
            fd["_file_path"] = path
            fd["_patch"] = patch
            fd["_affected"] = [c["symbol_key"] for c in changed_by_file.get(path, [])]
        llm_findings.extend(result.findings)
        per_file.append(f"- `{path}` — {verdict} review · {len(result.findings)} finding(s)")
    await phase("verify", llm_findings=len(llm_findings))

    # ── verify critical/high ────────────────────────────────────────────────
    to_verify = [(i, fd) for i, fd in enumerate(llm_findings) if fd.get("severity") in ("critical", "high")]
    dropped = 0
    if to_verify:
        confirmed = await verify_findings([
            {"index": i, "title": fd.get("title"), "body": fd.get("body"), "file": fd["_file_path"],
             "lines": [fd.get("start_line"), fd.get("end_line")],
             "code": _excerpt(contents.get(fd["_file_path"]), fd.get("start_line"), fd.get("end_line")) or fd["_patch"][:3000]}
            for i, fd in to_verify], run_id)
        if confirmed is not None:
            rejected = {i for i, _ in to_verify} - confirmed
            dropped = len(rejected)
            llm_findings = [fd for i, fd in enumerate(llm_findings) if i not in rejected]
    for s in sast_findings:
        s["_patch"] = next((f.get("patch") or "" for f in files_to_review if f["filename"] == s["_file_path"]), "")
    findings = policy.dedupe(sast_findings, llm_findings)
    findings = [fd for fd in findings if float(fd.get("confidence", 0.6)) >= min_conf or fd.get("source") == "sast"]
    await phase("persist", verified_dropped=dropped, findings=len(findings))

    # ── persist + auto-resolve ──────────────────────────────────────────────
    fps: list[str] = []
    async with session_factory()() as db:
        await db.execute(text("DELETE FROM findings WHERE run_id = :run"), {"run": run_id})
        for fd in findings:
            fp = policy.fingerprint(fd["_file_path"], fd.get("title", ""), fd.get("category", ""), fd.get("_affected"))
            fps.append(fp)
            await db.execute(text("""
                INSERT INTO findings (id, repo_id, run_id, fingerprint, source, category, severity, confidence,
                                      title, body, file_path, start_line, end_line, suggested_patch, status, affected_symbols)
                VALUES (:id, :rid, :run, :fp, :src, :cat, :sev, :conf, :title, :body, :file, :sl, :el, :patch, 'open', CAST(:aff AS jsonb))
            """), {"id": str(uuid.uuid4()), "rid": repo_id, "run": run_id, "fp": fp, "src": fd.get("source", "llm"),
                    "cat": fd.get("category", "maintainability"), "sev": fd.get("severity", "low"),
                    "conf": float(fd.get("confidence", 0.6)), "title": fd.get("title", "Untitled"), "body": fd.get("body", ""),
                    "file": fd["_file_path"], "sl": fd.get("start_line"), "el": fd.get("end_line"),
                    "patch": fd.get("suggested_patch"), "aff": json.dumps(fd.get("_affected", []))})
        gone = await db.execute(text("""
            UPDATE findings SET status = 'resolved',
                   resolution = CAST(:res AS jsonb)
            WHERE repo_id = :rid AND status = 'open' AND run_id <> :run
              AND run_id IN (SELECT id FROM runs WHERE repo_id = :rid AND pr_number = :pr)
              AND NOT (fingerprint = ANY(CAST(:fps AS text[])))
        """), {"rid": repo_id, "run": run_id, "pr": pr_number, "fps": fps,
               "res": json.dumps({"method": "auto_resolved", "reason": f"not present at {head_sha[:10]}"})})
        await db.commit()

    # ── risk + gate ─────────────────────────────────────────────────────────
    score = policy.risk_score(findings, len(blast_rows), sig_changes)
    band = policy.risk_band(score)
    decision, blocking, reason = policy.gate(findings, block_severity)
    async with session_factory()() as db:
        await db.execute(text("""
            INSERT INTO gate_decisions (id, repo_id, run_id, pr_number, commit_sha, decision, blocking_count, reason, posted_at)
            VALUES (:id, :rid, :run, :pr, :sha, :dec, :n, :reason, now())
        """), {"id": str(uuid.uuid4()), "rid": repo_id, "run": run_id, "pr": pr_number, "sha": head_sha,
                "dec": decision, "n": blocking, "reason": reason})
        await db.commit()
    await phase("post", risk_score=score, risk_band=band, gate=decision, blocking=blocking, auto_resolved=gone.rowcount)

    # ── post ────────────────────────────────────────────────────────────────
    body = _summary(pr_number, files_to_review, findings, blast_rows, changed_by_file, per_file, score, band,
                    decision, reason, counts, sast_note, dropped)
    comments = _inline_comments(findings)
    details_url = f"{settings.web_url.rstrip('/')}/prs"
    async with httpx.AsyncClient(timeout=20) as h:
        posted = False
        if comments:
            r = await h.post(f"{api_base}/repos/{repo_full_name}/pulls/{pr_number}/reviews", headers=headers,
                             json={"body": body, "event": "COMMENT", "comments": comments})
            posted = r.status_code in (200, 201)
            if not posted:
                print(f"[pr_review] batched review failed {r.status_code}: {r.text[:200]}")
        if not posted:
            await h.post(f"{api_base}/repos/{repo_full_name}/issues/{pr_number}/comments", headers=headers, json={"body": body})
        # merge gate: check run when installed as an App, commit status for PATs
        conclusion = "failure" if decision == "block" else "success"
        title = f"PRVet: {decision.upper()} · risk {score}/100 ({band}) · {len(findings)} finding(s)"
        if auth.is_app:
            await create_check_run(auth.token, repo_full_name, head_sha, name="PRVet review", conclusion=conclusion,
                                   title=title, summary=body, details_url=details_url, api_base=api_base,
                                   annotations=[{"path": fd["_file_path"], "start_line": int(fd["start_line"]), "end_line": int(fd.get("end_line") or fd["start_line"]),
                                                 "annotation_level": "failure" if fd.get("severity") in ("critical", "high") else "warning",
                                                 "title": fd.get("title", "")[:255], "message": (fd.get("body") or "")[:60000]}
                                                for fd in findings if fd.get("start_line")])
        else:
            await h.post(f"{api_base}/repos/{repo_full_name}/statuses/{head_sha}", headers=headers,
                         json={"state": conclusion, "context": "prvet/review", "description": title[:140], "target_url": details_url})

    stats.update({"phase": "done", "files_reviewed": len([v for v in verdicts.values() if v != "skip"]),
                  "findings": len(findings), "risk_score": score, "risk_band": band, "gate": decision,
                  "changed_symbols": sum(len(v) for v in changed_by_file.values()), "blast_radius": len(blast_rows),
                  "blast": [{"caller": r["symbol_key"], "path": r["path"], "line": r["start_line"], "target": r["target_key"], "depth": r["depth"]} for r in blast_rows]})
    async with session_factory()() as db:
        await db.execute(text("UPDATE runs SET status='succeeded', finished_at=now(), stats=CAST(:s AS jsonb) WHERE id=:id"),
                         {"id": run_id, "s": json.dumps(stats, default=str)})
        await db.commit()
    print(f"[pr_review] done · gate={decision} risk={score} findings={len(findings)}")
    return {"status": "succeeded", "run_id": run_id, "findings": len(findings), "gate": decision, "risk_score": score}


# ── helpers ─────────────────────────────────────────────────────────────────

def _summary(pr_number, files, findings, blast_rows, changed_by_file, per_file, score, band, decision, reason,
             counts, sast_note, dropped) -> str:
    sev: dict[str, int] = {}
    for f in findings:
        sev[f.get("severity", "info")] = sev.get(f.get("severity", "info"), 0) + 1
    icon = {"pass": "✅", "block": "🛑"}[decision]
    lines = [f"## PRVet review — {icon} {decision.upper()}",
             "",
             f"**Risk:** {score}/100 ({band}) · **Findings:** {len(findings)} · **Files:** {len(files)} "
             f"(deep {counts.get('deep', 0)} · fast {counts.get('fast', 0)} · skipped {counts.get('skip', 0)})",
             f"_{reason}_", ""]
    if sev:
        lines += ["| Severity | Count |", "|---|---|"] + [f"| {s} | {sev[s]} |" for s in ("critical", "high", "medium", "low", "info") if sev.get(s)] + [""]
    if findings:
        lines.append("### Findings\n")
        for i, f in enumerate(findings, 1):
            src = "semgrep" if f.get("source") == "sast" else "review"
            lines.append(f"**{i}. [{f.get('severity', 'low').upper()}] {f.get('title', 'Untitled')}** · `{f['_file_path']}:{f.get('start_line') or '–'}` · {f.get('category')} · {src}\n")
            lines.append(f"{f.get('body', '')}\n")
            if f.get("suggested_patch"):
                lines.append(f"```diff\n{f['suggested_patch']}\n```\n")
    if blast_rows:
        lines += ["### Blast radius", "", "| Changed symbol | Affected caller | Location | Depth |", "|---|---|---|---|"]
        lines += [f"| `{r['target_name']}` | `{r['name']}` | `{r['path']}:{r['start_line']}` | {r['depth']} |" for r in blast_rows[:25]]
        if len(blast_rows) > 25:
            lines.append(f"\n_…and {len(blast_rows) - 25} more callers._")
        lines.append("")
    elif changed_by_file:
        lines.append("_No indexed callers reference the changed symbols._\n")
    else:
        lines.append("_No indexed symbols matched the diff — run a baseline on this repo to enable blast-radius review._\n")
    lines += ["<details><summary>Per-file</summary>", "", *per_file, "", "</details>", ""]
    foot = []
    if sast_note:
        foot.append(sast_note)
    if dropped:
        foot.append(f"{dropped} high-severity candidate(s) rejected by verification pass")
    if foot:
        lines.append("_" + " · ".join(foot) + "_")
    return "\n".join(lines)


def _inline_comments(findings: list[dict]) -> list[dict]:
    out = []
    for f in findings:
        line = f.get("start_line") or f.get("end_line")
        try:
            line = int(line) if line else None
        except (TypeError, ValueError):
            line = None
        if not line or line not in _get_modified_lines(f.get("_patch") or ""):
            continue
        body = (f"### **[{f.get('severity', 'low').upper()}] {f.get('title', 'Untitled')}**\n"
                f"**Category:** `{f.get('category', 'maintainability')}` · **Confidence:** `{float(f.get('confidence', 0.6)):.2f}`"
                f"{' · **Source:** semgrep' if f.get('source') == 'sast' else ''}\n\n{f.get('body', '')}")
        if f.get("suggested_patch"):
            body += f"\n\n**Suggested fix:**\n```diff\n{f['suggested_patch']}\n```"
        out.append({"path": f["_file_path"], "line": line, "body": body})
    return out[: get_settings().max_comments_per_pr]


def _callers_context(changed: list[dict], callers: list[dict], contents: dict[str, str]) -> str:
    if not changed:
        return ""
    lines = ["", "CHANGED SYMBOLS (from the indexed graph):"]
    for c in changed:
        lines.append(f"- {c['kind']} `{c['symbol_key']}` L{c['start_line']}-{c['end_line']}" + (f" — {c['signature']}" if c.get("signature") else ""))
    if callers:
        lines += ["", "BLAST RADIUS — code elsewhere that depends on the changed symbols. Check whether the change "
                      "breaks any of these callers (signature, return shape, exceptions, nullability):"]
        budget = 12_000
        for r in callers:
            head = f"- `{r['symbol_key']}` ({r['path']}:{r['start_line']}) → uses `{r['target_name']}` (depth {r['depth']})"
            snippet = _excerpt(contents.get(r["path"]), r["start_line"], r["end_line"])
            block = head + (f"\n```\n{snippet}\n```" if snippet else "")
            if budget - len(block) < 0:
                lines.append(head)
                continue
            budget -= len(block)
            lines.append(block)
    return "\n".join(lines) + "\n"


def _excerpt(body: str | None, start, end, max_lines: int = 60) -> str | None:
    if not body or not start:
        return None
    ls = body.splitlines()
    s = max(1, int(start))
    e = min(int(end or s), s + max_lines - 1, len(ls))
    return "\n".join(ls[s - 1:e]) or None


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _get_modified_lines(patch: str) -> set[int]:
    modified: set[int] = set()
    cur = 0
    for line in (patch or "").splitlines():
        m = _HUNK.match(line)
        if m:
            cur = int(m.group(1))
            continue
        if line.startswith("+"):
            modified.add(cur)
            cur += 1
        elif line.startswith("-"):
            continue
        else:
            cur += 1
    return modified


def _lang_from_path(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {"py": "python", "ts": "typescript", "tsx": "typescript", "js": "javascript", "jsx": "javascript",
            "go": "go", "java": "java", "rs": "rust", "rb": "ruby", "cs": "csharp", "php": "php", "kt": "kotlin",
            "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp", "sql": "sql", "yaml": "yaml", "yml": "yaml"}.get(ext, ext or "text")
