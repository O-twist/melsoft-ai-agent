"""Teacher accounts on Supabase Auth, with the standard library only.

The browser signs in with Supabase Auth and sends its access token as ``Authorization: Bearer <jwt>``.
The server checks the token with ``{SUPABASE_URL}/auth/v1/user`` and then calls PostgREST *with that same
token*, so row level security (``owner_id = auth.uid()``) keeps every teacher to their own rows. No service
role key is used or needed here. Without Supabase settings, accounts are off and nothing here is called.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

_users = {}  # token -> (expires_at, user): a short cache so every poll does not ask Supabase again
CACHE_SECONDS = 120
TIMEOUT = 6


class AuthError(Exception):
    """The token is missing, expired or refused. The reply is a 401."""


def settings():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    anon = os.getenv("SUPABASE_ANON_KEY", "").strip()
    return (url, anon) if url and anon else None


def public_config():
    """What the browser needs to sign in. The anon key is public by design; nothing secret is in here."""
    found = settings()
    if not found or os.getenv("ACCOUNTS", "1") == "0":
        return {"auth": False}
    return {"auth": True, "supabase_url": found[0], "anon_key": found[1]}


def token_from(headers):
    raw = (headers.get("Authorization") or headers.get("authorization") or "").strip()
    return raw[7:].strip() if raw.lower().startswith("bearer ") else ""


def _request(method, url, token, anon, payload=None, prefer=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"apikey": anon, "Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


def user_for(token):
    """The signed-in teacher for this token, checked with Supabase. Raises AuthError if it is not valid."""
    found = settings()
    if not found:
        raise AuthError("Accounts are not set up on this server.")
    if not token:
        raise AuthError("Sign in first.")
    hit = _users.get(token)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        user = _request("GET", f"{found[0]}/auth/v1/user", token, found[1])
    except urllib.error.HTTPError as exc:
        exc.close()
        raise AuthError("Your session has ended. Sign in again.") from None
    except (OSError, ValueError):
        raise AuthError("Cannot reach the sign-in service right now.") from None
    if not isinstance(user, dict) or not user.get("id"):
        raise AuthError("Your session has ended. Sign in again.")
    meta = user.get("user_metadata") or {}
    info = {"id": user["id"], "email": user.get("email") or "", "name": meta.get("display_name") or "", "school": meta.get("school") or ""}
    _users[token] = (time.time() + CACHE_SECONDS, info)
    if len(_users) > 500:
        for key in [k for k, (until, _) in _users.items() if until < time.time()]:
            _users.pop(key, None)
    return info


def _rest(method, path, token, payload=None, prefer=None):
    url, anon = settings()
    try:
        return _request(method, f"{url}/rest/v1/{path}", token, anon, payload, prefer)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        exc.close()
        raise RuntimeError(f"The database refused that ({exc.code}). {detail}") from None


def me(token):
    """Profile, saved runs and classes for the signed-in teacher. Missing tables give empty lists."""
    user = user_for(token)
    out = {"user": user, "profile": None, "runs": [], "classes": []}
    try:
        rows = _rest("GET", f"profiles?id=eq.{urllib.parse.quote(user['id'])}&select=display_name,school", token) or []
        out["profile"] = rows[0] if rows else {"display_name": user["name"], "school": user["school"]}
    except (RuntimeError, OSError, ValueError):
        out["profile"] = {"display_name": user["name"], "school": user["school"]}
    try:
        rows = _rest("GET", "runs?select=summary,created_at&order=created_at.desc&limit=30", token) or []
        out["runs"] = [r["summary"] for r in rows if isinstance(r.get("summary"), dict)]
    except (RuntimeError, OSError, ValueError):
        pass
    try:
        out["classes"] = _rest("GET", "classes?select=id,name,template,created_at&order=created_at", token) or []
    except (RuntimeError, OSError, ValueError):
        pass
    return out


def save_profile(token, body):
    user = user_for(token)
    row = {"id": user["id"], "display_name": str(body.get("display_name") or "")[:80], "school": str(body.get("school") or "")[:120]}
    _rest("POST", "profiles?on_conflict=id", token, [row], "resolution=merge-duplicates,return=minimal")
    return {"ok": True, "profile": {"display_name": row["display_name"], "school": row["school"]}}


SUMMARY_KEYS = ("id", "goal", "assessment", "status", "elapsed", "marked", "held", "sent_back", "fixed", "delivered", "planted", "plans", "when")


def save_run(token, body):
    """Keep a finished run's summary in the teacher's own history."""
    user = user_for(token)
    summary = {k: body.get(k) for k in SUMMARY_KEYS if k in body}
    if not summary.get("id"):
        raise ValueError("The run has no id.")
    summary["goal"] = str(summary.get("goal") or "")[:600]
    row = {"owner_id": user["id"], "run_key": str(summary["id"])[:64], "summary": summary}
    _rest("POST", "runs?on_conflict=owner_id,run_key", token, [row], "resolution=merge-duplicates,return=minimal")
    return {"ok": True}


def load_sample_class(token):
    """Copy the sample Grade 12 CAT class into the teacher's account (once)."""
    user = user_for(token)
    row = {"owner_id": user["id"], "name": "Grade 12 CAT", "template": "sample-grade12-cat"}
    _rest("POST", "classes?on_conflict=owner_id,template", token, [row], "resolution=ignore-duplicates,return=minimal")
    return {"ok": True}
