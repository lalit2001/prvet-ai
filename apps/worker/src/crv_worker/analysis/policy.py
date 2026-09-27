"""Pure review policy: fingerprints, dedupe, triage pre-rules, risk score, gate. No I/O."""
from __future__ import annotations

import hashlib
import re

SEV_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

_SKIP_EXT = (".lock", ".md", ".rst", ".txt", ".svg", ".png", ".jpg", ".gif", ".ico", ".snap", ".map")
_SKIP_NAMES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "uv.lock", "go.sum", "Cargo.lock")
_SENSITIVE = re.compile(r"auth|secret|token|crypt|passw|permission|acl|payment|billing|sql|migration|webhook|session|oauth|jwt|login", re.I)
_SIG_LINE = re.compile(r"^-\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|interface|type|public|private|protected)\b", re.M)


def triage_prefilter(path: str) -> str | None:
    """Decide without a model when it's obvious. None = ask the triage model."""
    low = path.lower()
    if low.endswith(_SKIP_EXT) or low.rsplit("/", 1)[-1] in _SKIP_NAMES or ".generated." in low or "/dist/" in low:
        return "skip"
    if _SENSITIVE.search(low):
        return "deep"
    return None


def signature_changed(patch: str) -> bool:
    return bool(_SIG_LINE.search(patch or ""))


def fingerprint(file_path: str, title: str, category: str, symbols: list[str] | None = None) -> str:
    """Stable across line shifts: file + enclosing symbols + category + title with digits stripped."""
    norm = re.sub(r"\d+", "#", (title or "").lower()).strip()
    key = f"{file_path}|{'|'.join(sorted(symbols or []))}|{category}|{norm}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def dedupe(sast: list[dict], llm: list[dict], slack: int = 2) -> list[dict]:
    """Prefer deterministic SAST evidence; drop an LLM finding that overlaps a SAST one
    in the same file+category, but carry the LLM explanation along."""
    keep = list(sast)
    for f in llm:
        dup = None
        for s in sast:
            if s.get("_file_path") != f.get("_file_path") or s.get("category") != f.get("category"):
                continue
            a, b = f.get("start_line") or 0, f.get("end_line") or f.get("start_line") or 0
            c, d = s.get("start_line") or 0, s.get("end_line") or s.get("start_line") or 0
            if a and c and a - slack <= d and c - slack <= b:
                dup = s
                break
        if dup is None:
            keep.append(f)
        else:
            dup["body"] = f"{dup.get('body', '')}\n\n**Reviewer note:** {f.get('body', '')}"
            if SEV_ORDER.get(f.get("severity", "low"), 0) > SEV_ORDER.get(dup.get("severity", "low"), 0):
                dup["severity"] = f["severity"]
    return keep


def risk_score(findings: list[dict], blast_count: int, signature_changes: int) -> int:
    weights = {"critical": 25, "high": 10, "medium": 3, "low": 1, "info": 0}
    s = sum(weights.get(f.get("severity", "low"), 0) for f in findings)
    s += min(20, blast_count) + min(10, signature_changes * 5)
    return max(0, min(100, s))


def risk_band(score: int) -> str:
    return "high" if score >= 50 else "medium" if score >= 20 else "low"


def gate(findings: list[dict], block_severity: str = "high") -> tuple[str, int, str]:
    threshold = SEV_ORDER.get(block_severity, 3)
    blocking = [f for f in findings if SEV_ORDER.get(f.get("severity", "low"), 0) >= threshold]
    if blocking:
        worst = max(blocking, key=lambda f: SEV_ORDER.get(f.get("severity"), 0))
        return "block", len(blocking), f"{len(blocking)} finding(s) at or above {block_severity}; worst: [{worst['severity']}] {worst.get('title', '')[:80]}"
    return "pass", 0, f"no findings at or above {block_severity}"


if __name__ == "__main__":
    assert triage_prefilter("pnpm-lock.yaml") == "skip"
    assert triage_prefilter("src/auth/session.py") == "deep"
    assert triage_prefilter("src/ui/button.tsx") is None
    assert signature_changed("-def foo(a):\n+def foo(a, b):") and not signature_changed("-    return 1\n+    return 2")
    assert fingerprint("a.py", "Bug at line 12", "bug") == fingerprint("a.py", "Bug at line 99", "bug")
    sast = [{"_file_path": "a.py", "category": "security", "severity": "high", "start_line": 10, "end_line": 10, "body": "s"}]
    llm = [{"_file_path": "a.py", "category": "security", "severity": "critical", "start_line": 11, "end_line": 12, "body": "l"},
           {"_file_path": "a.py", "category": "bug", "severity": "low", "start_line": 11, "end_line": 12, "body": "x"}]
    merged = dedupe(sast, llm)
    assert len(merged) == 2 and merged[0]["severity"] == "critical"
    assert gate([{"severity": "medium"}], "high")[0] == "pass" and gate([{"severity": "high"}], "high")[0] == "block"
    assert risk_band(risk_score([{"severity": "critical"}, {"severity": "high"}], 30, 1)) == "high"
    print("policy ok")
