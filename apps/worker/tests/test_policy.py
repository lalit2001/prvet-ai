from crv_worker.analysis import policy
from crv_worker.analysis.sast import _custom_rules_yaml, _parse


def test_triage_prefilter():
    assert policy.triage_prefilter("pnpm-lock.yaml") == "skip"
    assert policy.triage_prefilter("docs/README.md") == "skip"
    assert policy.triage_prefilter("src/auth/session.py") == "deep"
    assert policy.triage_prefilter("src/ui/button.tsx") is None


def test_fingerprint_is_line_stable():
    assert policy.fingerprint("a.py", "Bug at line 12", "bug", ["py::a.f"]) == policy.fingerprint("a.py", "Bug at line 99", "bug", ["py::a.f"])
    assert policy.fingerprint("a.py", "Bug", "bug") != policy.fingerprint("b.py", "Bug", "bug")


def test_dedupe_prefers_sast_and_keeps_worst_severity():
    sast = [{"_file_path": "a.py", "category": "security", "severity": "high", "start_line": 10, "end_line": 10, "body": "s"}]
    llm = [{"_file_path": "a.py", "category": "security", "severity": "critical", "start_line": 11, "end_line": 12, "body": "l"},
           {"_file_path": "a.py", "category": "bug", "severity": "low", "start_line": 11, "end_line": 12, "body": "x"}]
    merged = policy.dedupe(sast, llm)
    assert len(merged) == 2 and merged[0]["severity"] == "critical" and "Reviewer note" in merged[0]["body"]


def test_gate_and_risk():
    assert policy.gate([{"severity": "medium"}], "high")[0] == "pass"
    assert policy.gate([{"severity": "high", "title": "x"}], "high") == ("block", 1, "1 finding(s) at or above high; worst: [high] x")
    assert policy.risk_band(policy.risk_score([], 0, 0)) == "low"
    assert policy.risk_band(policy.risk_score([{"severity": "critical"}, {"severity": "high"}], 30, 1)) == "high"


def test_custom_rules_become_semgrep_yaml():
    y = _custom_rules_yaml([
        {"id": "no-print", "language": "python", "severity": "low", "category": "style", "message": "no print", "pattern": "print($X)", "pattern_not": "print('ok')"},
        {"id": "todo", "language": "typescript", "severity": "medium", "category": "maintainability", "message": "todo", "pattern": "re:TODO\\(\\w+\\)"},
        {"id": "off", "enabled": False, "language": "python", "pattern": "x"},
    ])
    assert y and "pattern: print($X)" in y and "pattern-not: print('ok')" in y and "pattern-regex" in y and "custom.off" not in y


def test_parse_semgrep_output():
    data = {"results": [{"check_id": "prvet.py.eval-exec", "path": "a.py", "start": {"line": 3}, "end": {"line": 3},
                         "extra": {"message": "eval is bad", "severity": "ERROR", "lines": "eval(x)", "metadata": {"category": "security", "cwe": "CWE-95"}}}]}
    f = _parse(data)[0]
    assert f["severity"] == "high" and f["category"] == "security" and f["_file_path"] == "a.py" and f["source"] == "sast"
