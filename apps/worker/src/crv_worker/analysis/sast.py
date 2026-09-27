"""Semgrep pre-filter. Deterministic findings before the LLM sees anything.

Semgrep is optional (`uv sync --extra sast` / worker image installs it). When
the binary is missing we return no findings plus a note — never fail the run."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import yaml

RULES_DIR = Path(__file__).resolve().parents[5] / "packages" / "rules" / "semgrep"

_SEV = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
_LANG = {"python": "python", "typescript": "typescript", "javascript": "javascript", "tsx": "typescript", "js": "javascript", "ts": "typescript"}


def available() -> bool:
    return shutil.which("semgrep") is not None


async def run_semgrep(root: Path, rel_paths: list[str], custom_rules: list[dict] | None = None,
                      timeout_s: int = 180) -> tuple[list[dict], str | None]:
    """→ (findings, note). Findings use the PRD §13.2 shape with source='sast'."""
    exe = shutil.which("semgrep")
    if exe is None:
        return [], "semgrep not installed — SAST pre-filter skipped"
    paths = [p for p in rel_paths if (root / p).is_file()]
    if not paths:
        return [], None

    findings: list[dict] = []
    notes: list[str] = []
    configs: list[Path] = [RULES_DIR] if RULES_DIR.is_dir() else []
    custom_yaml = _custom_rules_yaml(custom_rules or [])
    with tempfile.TemporaryDirectory() as td:
        if custom_yaml:
            cp = Path(td) / "custom.yml"
            cp.write_text(custom_yaml)
            configs.append(cp)
        # each config runs separately so a broken custom rule can't sink the bundled pack
        for cfg in configs:
            out, err = await _run(exe, root, cfg, paths, timeout_s)
            if err:
                notes.append(f"{cfg.name}: {err}")
                continue
            findings.extend(_parse(out))
    return findings, ("; ".join(notes) or None)


async def _run(exe: str, root: Path, cfg: Path, paths: list[str], timeout_s: int) -> tuple[dict, str | None]:
    cmd = [exe, "--json", "--quiet", "--metrics=off", "--disable-version-check",
           "--timeout", "30", "--config", str(cfg), *paths]
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(root), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        return {}, "timed out"
    except OSError as e:
        return {}, str(e)
    try:
        data = json.loads(stdout or b"{}")
    except json.JSONDecodeError:
        return {}, (stderr.decode(errors="replace")[:300] or "invalid json output")
    errors = [e.get("message", "") for e in data.get("errors", []) if e.get("level") == "error"]
    if errors and not data.get("results"):
        return {}, errors[0][:300]
    return data, None


def _parse(data: dict) -> list[dict]:
    out = []
    for r in data.get("results", []):
        extra = r.get("extra", {})
        meta = extra.get("metadata", {}) or {}
        rule = r.get("check_id", "semgrep")
        for prefix in ("custom.", "prvet."):  # semgrep prefixes ids with the config file path
            if prefix in rule:
                rule = prefix + rule.split(prefix, 1)[1]
                break
        out.append({
            "source": "sast",
            "rule_id": rule,
            "category": meta.get("category", "bug") if meta.get("category") in ("security", "bug", "performance", "maintainability", "style") else "security" if "security" in str(meta).lower() else "bug",
            "severity": _SEV.get(extra.get("severity", "WARNING"), "medium"),
            "confidence": 0.9,
            "start_line": r.get("start", {}).get("line"),
            "end_line": r.get("end", {}).get("line"),
            "title": extra.get("message", rule).split("\n")[0][:140],
            "body": f"Semgrep rule `{rule}`" + (f" ({meta['cwe']})" if meta.get("cwe") else "") + f"\n\n{extra.get('message', '')}\n\n```\n{extra.get('lines', '')}\n```",
            "suggested_patch": extra.get("fix"),
            "_file_path": r.get("path"),
        })
    return out


def _custom_rules_yaml(rules: list[dict]) -> str | None:
    """UI-authored rules (org.settings.custom_rules) → a semgrep rule file.
    Only rules that look like semgrep patterns qualify; plain regexes go to pattern-regex."""
    out = []
    for i, r in enumerate(rules):
        if not r.get("enabled", True) or not r.get("pattern"):
            continue
        lang = _LANG.get((r.get("language") or "python").lower())
        if not lang:
            continue
        pat = r["pattern"]
        rule: dict = {
            "id": f"custom.{(r.get('id') or i)}".replace(" ", "-"),
            "languages": [lang],
            "severity": {"critical": "ERROR", "high": "ERROR", "medium": "WARNING"}.get(r.get("severity", "medium"), "INFO"),
            "message": r.get("message") or "custom rule",
            "metadata": {"category": r.get("category", "maintainability")},
        }
        if pat.startswith("re:") or pat.startswith("^"):
            rule["pattern-regex"] = pat.removeprefix("re:")
        else:
            rule["pattern"] = pat
            if r.get("pattern_not"):
                rule["pattern-not"] = r["pattern_not"]
        if r.get("fix"):
            rule["fix"] = r["fix"]
        out.append(rule)
    return yaml.safe_dump({"rules": out}, sort_keys=False) if out else None
