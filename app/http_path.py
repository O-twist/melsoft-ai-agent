"""Turn a Vercel rewrite back into the /api path the browser asked for.

File-based Python functions are served at the file path, so every route is
rewritten onto api/index.py. Local `python run.py` never comes through here.
"""
from urllib.parse import parse_qs, quote, urlparse

ENTRY_PATHS = {"/api", "/api/", "/api/index", "/api/index.py"}
_ORIGINAL = ("x-forwarded-uri", "x-original-uri", "x-vercel-original-path")


def _header(headers, name):
    if not headers:
        return ""
    found = headers.get(name) or headers.get(name.upper()) or ""
    if found:
        return str(found).strip()
    lowered = name.lower()
    items = getattr(headers, "items", None)
    if not items:
        return ""
    for key, value in items():
        if str(key).lower() == lowered and value:
            return str(value).strip()
    return ""


def _original(headers):
    for name in _ORIGINAL:
        raw = _header(headers, name)
        if not raw:
            continue
        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urlparse(raw)
            raw = parsed.path + (("?" + parsed.query) if parsed.query else "")
        path = urlparse(raw).path
        if raw.startswith("/api/") and path not in ENTRY_PATHS:
            return raw
    return ""


def api_path(path, headers=None):
    """The path Handler expects. A path that is already /api/<route> is kept."""
    path = path or "/"
    parsed = urlparse(path)
    if parsed.path not in ENTRY_PATHS:
        return path
    original = _original(headers)
    if original:
        return original
    query = parse_qs(parsed.query, keep_blank_values=True)
    route = (query.get("route") or [""])[0].strip("/")
    if not route:
        return path
    rest = []
    for key, values in query.items():
        if key == "route":
            continue
        for value in values:
            rest.append(f"{quote(key, safe='')}={quote(value, safe='/')}")
    target = "/api/" + route
    return target + (("?" + "&".join(rest)) if rest else "")
