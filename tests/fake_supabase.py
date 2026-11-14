"""A small stand-in for Supabase Auth and PostgREST, for tests and local browser checks.

It speaks the few endpoints LabLess uses. Rows carry owner_id and every read or write is limited to the
caller's own rows, the way the row level security policies in supabase/migrations/*_accounts.sql do.
This proves the app sends each teacher's own token and never a shared key; the real policies are SQL.

Run on its own:  python tests/fake_supabase.py 54321   (add "confirm" to require email confirmation)
"""
import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ANON = "fake-anon-key"


class Store:
    def __init__(self, confirm=False):
        self.confirm = confirm
        self.users = {}     # email -> {id, email, password, meta, confirmed}
        self.tokens = {}    # token -> user id
        self.tables = {"profiles": [], "runs": [], "classes": []}
        self.seen_auth = []  # every Authorization header the REST side received
        self.lock = threading.Lock()

    def session(self, user):
        token = f"tok-{uuid.uuid4().hex}"
        self.tokens[token] = user["id"]
        return {"access_token": token, "refresh_token": f"ref-{token}", "expires_in": 3600, "token_type": "bearer",
                "user": {"id": user["id"], "email": user["email"], "user_metadata": user["meta"]}}


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body=None):
            data = b"" if body is None else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"null")

        def _uid(self):
            raw = self.headers.get("Authorization", "")
            return store.tokens.get(raw[7:] if raw.startswith("Bearer ") else "")

        def do_GET(self):
            url = urlparse(self.path)
            if self.headers.get("apikey") != ANON:
                return self._send(401, {"message": "No API key found in request"})
            if url.path == "/auth/v1/user":
                uid = self._uid()
                user = next((u for u in store.users.values() if u["id"] == uid), None)
                if not user:
                    return self._send(401, {"msg": "invalid JWT"})
                return self._send(200, {"id": user["id"], "email": user["email"], "user_metadata": user["meta"]})
            if url.path.startswith("/rest/v1/"):
                store.seen_auth.append(self.headers.get("Authorization", ""))
                uid = self._uid()
                table = url.path.split("/")[-1]
                if not uid:
                    return self._send(401, {"message": "JWT required"})
                rows = [r for r in store.tables.get(table, []) if r.get("owner_id", r.get("id")) == uid]
                q = parse_qs(url.query)
                if "id" in q:
                    want = q["id"][0].replace("eq.", "")
                    rows = [r for r in rows if r.get("id") == want]
                rows = sorted(rows, key=lambda r: r.get("_at", 0), reverse="created_at.desc" in url.query)
                return self._send(200, [{k: v for k, v in r.items() if k != "_at"} for r in rows])
            return self._send(404, {"message": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            if self.headers.get("apikey") != ANON:
                return self._send(401, {"message": "No API key found in request"})
            body = self._body() or {}
            with store.lock:
                if url.path == "/auth/v1/signup":
                    email = str(body.get("email", "")).lower()
                    if email in store.users:
                        return self._send(422, {"msg": "User already registered"})
                    if len(str(body.get("password", ""))) < 6:
                        return self._send(422, {"msg": "Password should be at least 6 characters"})
                    user = {"id": str(uuid.uuid4()), "email": email, "password": body["password"], "meta": body.get("data") or {}, "confirmed": not store.confirm}
                    store.users[email] = user
                    store.tables["profiles"].append({"id": user["id"], "display_name": user["meta"].get("display_name", ""), "school": user["meta"].get("school", "")})
                    if store.confirm:
                        return self._send(200, {"id": user["id"], "email": email, "user_metadata": user["meta"]})
                    return self._send(200, store.session(user))
                if url.path == "/auth/v1/token":
                    grant = parse_qs(url.query).get("grant_type", [""])[0]
                    if grant == "password":
                        user = store.users.get(str(body.get("email", "")).lower())
                        if not user or user["password"] != body.get("password"):
                            return self._send(400, {"error": "invalid_grant", "error_description": "Invalid login credentials"})
                        if not user["confirmed"]:
                            return self._send(400, {"error": "invalid_grant", "error_description": "Email not confirmed"})
                        return self._send(200, store.session(user))
                    if grant == "refresh_token":
                        uid = store.tokens.get(str(body.get("refresh_token", ""))[4:])
                        user = next((u for u in store.users.values() if u["id"] == uid), None)
                        return self._send(200, store.session(user)) if user else self._send(400, {"error_description": "Invalid Refresh Token"})
                if url.path in ("/auth/v1/recover", "/auth/v1/logout"):
                    return self._send(200, {})
                if url.path.startswith("/rest/v1/"):
                    store.seen_auth.append(self.headers.get("Authorization", ""))
                    uid = self._uid()
                    if not uid:
                        return self._send(401, {"message": "JWT required"})
                    table = url.path.split("/")[-1]
                    rows = body if isinstance(body, list) else [body]
                    conflict = parse_qs(url.query).get("on_conflict", [""])[0].split(",")
                    for row in rows:
                        owner = row.get("owner_id", row.get("id") if table == "profiles" else uid)
                        if owner != uid:  # with check (owner_id = auth.uid())
                            return self._send(403, {"message": "new row violates row-level security policy"})
                        row = {**row, "owner_id": uid, "_at": len(store.tables[table])} if table != "profiles" else row
                        existing = next((r for r in store.tables[table] if conflict[0] and all(r.get(c) == row.get(c) for c in conflict)), None)
                        if existing:
                            if "ignore-duplicates" not in (self.headers.get("Prefer") or ""):
                                existing.update(row)
                        else:
                            store.tables[table].append(row)
                    return self._send(201)
            return self._send(404, {"message": "not found"})

    return Handler


def serve(port=0, confirm=False):
    store = Store(confirm=confirm)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, store


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 54321
    server, _ = serve(port, confirm="confirm" in sys.argv)
    print(f"Fake Supabase on http://127.0.0.1:{port}  (anon key: {ANON})", flush=True)
    threading.Event().wait()
