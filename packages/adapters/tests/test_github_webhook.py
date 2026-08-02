"""GitHub webhook HMAC — the security-critical crypto path."""
import asyncio
import hashlib
import hmac

from crv_adapters.forge.github import GitHubAdapter


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    a = GitHubAdapter()
    body = b'{"action":"opened"}'
    ok = asyncio.run(a.verify_webhook({"x-hub-signature-256": _sig("s", body)}, body, "s"))
    assert ok is True


def test_wrong_secret_rejected():
    a = GitHubAdapter()
    body = b'{"action":"opened"}'
    ok = asyncio.run(a.verify_webhook({"x-hub-signature-256": _sig("wrong", body)}, body, "s"))
    assert ok is False


def test_missing_header_rejected():
    a = GitHubAdapter()
    assert asyncio.run(a.verify_webhook({}, b"x", "s")) is False


def test_tampered_body_rejected():
    a = GitHubAdapter()
    body = b'{"action":"opened"}'
    ok = asyncio.run(a.verify_webhook({"x-hub-signature-256": _sig("s", body)}, body + b" ", "s"))
    assert ok is False


def test_parse_event_ignores_unknown():
    a = GitHubAdapter()
    assert a.parse_event({"x-github-event": "star"}, {"action": "created", "repository": {"full_name": "o/r"}}) is None


def test_parse_event_maps_pull_request_opened():
    a = GitHubAdapter()
    ev = a.parse_event({"x-github-event": "pull_request"}, {"action": "opened", "repository": {"full_name": "o/r"}})
    assert ev is not None and ev.kind == "pr_opened" and ev.repo_full_name == "o/r"
