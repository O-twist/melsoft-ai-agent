"""Start the Marking Colleague dashboard:  python run.py   then open http://localhost:8000"""
import json
import mimetypes
import time
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app import classes, ingest, risk, story, tools
from app.llm import make_llm
from app.orchestrator import AGENTS, Run

ROOT = Path(__file__).parent
DATA = os.getenv("DATA_DIR", str(ROOT / "data"))
OUTPUT = Path(os.getenv("OUTPUT_DIR", str(ROOT / "output")))
DIST = ROOT / "web" / "dist"
NOT_BUILT = (
    "<h1>Dashboard not built yet</h1><p>Run <code>npm install</code> and <code>npm run build</code> "
    "inside the <code>web</code> folder, then reload. The API is running.</p>"
)
mimetypes.add_type("model/gltf-binary", ".glb")  # the 3D model in the lesson view
DOWNLOADS = {".csv": "text/csv", ".md": "text/markdown", ".pdf": "application/pdf", ".txt": "text/plain"}
current = {"run": None}


def practical_lab():
    """The PC assembly practical is offered when its rubric is on disk, unless PRACTICAL_LAB=0 turns it off."""
    return os.getenv("PRACTICAL_LAB", "1") != "0" and (Path(DATA) / tools.RUBRIC_FILES["practical"]).exists()


def offered(assessment):
    """Whether this kind of assessment can be marked: essays always, the practical behind its flag, a subject
    test when its rubric is on disk."""
    if assessment == "practical":
        return practical_lab()
    return assessment in tools.RUBRIC_FILES and (Path(DATA) / tools.RUBRIC_FILES[assessment]).exists()


def live_attempts():
    """Where attempts done in the dashboard's virtual lab are kept, apart from the sample files in data/attempts."""
    return OUTPUT / "attempts"


def class_root():
    """Where classes that teachers upload are kept, each in its own folder shaped like data/."""
    return OUTPUT / "_classes"


def uploads():
    """Where photographed pages wait between being uploaded and being read by a run."""
    return OUTPUT / "_uploads"


def idle_state():
    """What the dashboard shows before the first run: the class and rubric on disk, nothing marked."""
    llm = make_llm()
    rubric = tools.load_rubric(DATA)
    return {
        "id": None, "status": "idle", "goal": "", "inject_fault": False,
        "agents": {k: "waiting" for k in AGENTS}, "stats": {}, "plan": None, "report": None,
        "subs": tools.load_submissions(DATA), "rubric": rubric, "spans": [], "files": [],
        "support": None, "lesson": None, "consistency": None, "outcomes": tools.load_outcomes(DATA, rubric),
        "scripts": None, "inject_ocr_fault": False, "assessment": "essay", "corrections": None,
        "events": [], "next": 0, "llm": {"name": llm.name, "model": llm.model, "calls": 0,
                                         "backup": getattr(llm, "standby", None)},
        "where": None, "elapsed": None, "t": 0,
    }


class Server(ThreadingHTTPServer):
    # On Windows this flag would let a second copy of the app share the port and steal requests.
    allow_reuse_address = os.name != "nt"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        return body if isinstance(body, dict) else {}

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/state":
                run = current["run"]
                since = parse_qs(url.query).get("since", ["0"])[0]
                state = run.snapshot(int(since) if since.isdigit() else 0) if run else idle_state()
                state["features"] = {"practical": practical_lab(), "tests": tools.available_tests(DATA)}
                state["risk"] = self._risk_board(run, state.get("subs") if run else None)
                return self._send(200, state)
            if url.path == "/api/risk":
                run = current["run"]
                return self._send(200, self._risk_board(run, run.subs if run else None))
            if url.path == "/api/materials":
                return self._materials(parse_qs(url.query))
            if url.path == "/api/file":
                return self._download(parse_qs(url.query).get("name", [""])[0])
            if url.path == "/api/corrections.md":
                run = current["run"]
                if not run:
                    return self._send(404, {"error": "not found"})
                return self._send(200, story.to_markdown(run.corrections()).encode(), "text/markdown; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="corrections.md"'})
            if url.path == "/api/attempts":
                folder = live_attempts()
                rows = [{"learner_id": p.stem, "saved": round(p.stat().st_mtime)} for p in sorted(folder.glob("*.json"))] if folder.is_dir() else []
                return self._send(200, {"attempts": rows})
            if url.path == "/api/page":
                q = parse_qs(url.query)
                try:
                    path, mime = ingest.page_file(uploads(), q.get("batch", [""])[0], q.get("id", [""])[0])
                except ingest.IngestError:
                    return self._send(404, {"error": "not found"})
                return self._send(200, path.read_bytes(), mime, {"Cache-Control": "private, max-age=3600"})
            if url.path.startswith("/api/"):
                return self._send(404, {"error": "not found"})
            self._static(url.path)
        except (BrokenPipeError, ConnectionError):
            pass  # the browser went away
        except Exception as e:  # for example a class list or rubric that cannot be read
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def _risk_board(self, run, overlay):
        """Planner risk scores. A failure here must not take the rest of the dashboard down."""
        try:
            if run:
                return risk.assess(run.data_dir, overlay=overlay, assessment=run.assessment,
                                   live_dir=run.live_attempts or live_attempts())
            return risk.assess(DATA, live_dir=live_attempts())
        except Exception as exc:
            return {"ok": False, "learners": [], "counts": {}, "error": f"{type(exc).__name__}: {exc}"}

    def _materials(self, query):
        """The memo, the rubric and every learner's script: the current run's, or (before a run) what is on disk."""
        one = lambda key: query.get(key, [""])[0]
        run = current["run"]
        if one("source") == "run":
            if not run:
                return self._send(404, {"error": "There is no run yet."})
            return self._send(200, run.materials())
        assessment = one("assessment") or "essay"
        if not offered(assessment):
            return self._send(400, {"error": "That kind of assessment is not available."})
        data_dir = DATA
        if one("class") and assessment == "essay":
            try:
                data_dir = str(classes.class_folder(class_root(), one("class")))
            except classes.ClassError as e:
                return self._send(400, {"error": str(e)})
        rubric = tools.load_rubric(data_dir, assessment)
        subs = tools.load_submissions(data_dir)
        if assessment == "practical":
            tools.load_attempts(data_dir, subs, rubric, live_attempts())
        elif tools.is_test(assessment):
            tools.load_answers(data_dir, subs, assessment)
        tools.triage(subs, rubric)
        return self._send(200, tools.materials(subs, rubric))

    def _download(self, name):
        """Hand over a file the current run wrote (mark sheet, class report, catch-up plans, lesson plan). Only files the run recorded."""
        run = current["run"]
        if not run or name not in run.files:
            return self._send(404, {"error": "not found"})
        ctype = DOWNLOADS.get(Path(name).suffix, "application/octet-stream")
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        self._send(200, (run.out_dir / name).read_bytes(), ctype,
                   {"Content-Disposition": f'attachment; filename="{Path(name).name}"'})

    def _static(self, path):
        """Serve the built React dashboard from web/dist."""
        if not (DIST / "index.html").exists():
            return self._send(503, NOT_BUILT.encode(), "text/html; charset=utf-8")
        target = (DIST / unquote(path).lstrip("/")).resolve()
        if not target.is_file() or DIST.resolve() not in target.parents:
            if Path(path).suffix:  # a missing asset is a 404, not the app page
                return self._send(404, b"Not found", "text/plain; charset=utf-8")
            target = DIST / "index.html"
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".mjs"):
            ctype = "text/javascript"  # Windows registries sometimes map .js to text/plain
        self._send(200, target.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))

    def _ingest(self, query):
        """Keep photographed pages for the next run: uploaded files, or the sample scripts. Returns the batch so far."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > ingest.MAX_UPLOAD:
            return self._send(413, {"error": f"Upload at most {ingest.MAX_UPLOAD // (1024 * 1024)} MB at a time."})
        body = self.rfile.read(n) if n else b""
        root = uploads()
        root.mkdir(parents=True, exist_ok=True)
        try:
            if query.get("sample", [""])[0] == "1":
                files, batch = ingest.sample_files(DATA), None
                if not files:
                    return self._send(404, {"error": "There are no sample scripts in the data folder."})
            else:
                parts = ingest.parse_multipart(self.headers.get("Content-Type"), body)
                files = [(part["filename"], part["data"]) for part in parts if part["filename"] is not None]
                batch = next((part["data"].decode("ascii", "replace").strip() for part in parts if part["name"] == "batch"), None)
                if not files:
                    return self._send(400, {"error": "Choose at least one photo."})
            if not batch:
                ingest.clear_batches(root)
                batch = ingest.new_batch(root)
            pages = ingest.add_pages(root, batch, files)
        except ingest.IngestError as e:
            return self._send(400, {"error": str(e)})
        return self._send(200, {"batch": batch, "pages": pages})

    def _upload_class(self):
        """A teacher's own class list and essays (and, if they like, rubric and outcomes), checked before it is kept."""
        n = int(self.headers.get("Content-Length") or 0)
        if n > ingest.MAX_UPLOAD:
            return self._send(413, {"error": f"Upload at most {ingest.MAX_UPLOAD // (1024 * 1024)} MB at a time."})
        try:
            parts = ingest.parse_multipart(self.headers.get("Content-Type"), self.rfile.read(n) if n else b"")
        except ingest.IngestError as e:
            return self._send(400, {"error": str(e)})
        one = lambda field: next((p["data"] for p in parts if p["name"] == field and p["filename"] is not None and p["data"]), None)
        essays = [(p["filename"], p["data"]) for p in parts if p["name"] == "essays" and p["filename"]]
        if not one("class_list"):
            return self._send(400, {"error": "Choose the class list (a CSV file with id and name columns).", "problems": []})
        try:
            cid, summary = classes.create_class(class_root(), DATA, one("class_list"), essays, one("rubric"), one("outcomes"),
                                                one("memo"))
        except classes.ClassError as e:
            return self._send(400, {"error": "The class was not kept: " + str(e) + ".", "problems": e.problems})
        return self._send(200, summary)

    def _save_attempt(self, body):
        """Keep an attempt from the virtual lab, once code has checked it replays, for the next practical run."""
        if not practical_lab():
            return self._send(400, {"error": "The PC assembly practical is not available."})
        rubric = tools.load_rubric(DATA, "practical")
        subs = tools.load_submissions(DATA)
        attempt, problems = tools.check_attempt(body, subs, rubric)
        if problems:
            return self._send(400, {"error": "The attempt was not kept: " + "; ".join(problems) + "."})
        folder = live_attempts()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{attempt['learner_id']}.json").write_text(json.dumps(attempt, indent=1) + "\n", encoding="utf-8")
        return self._send(200, {"ok": True, "saved": round(time.time()), "log": tools.render_attempt(attempt, rubric)})

    def do_POST(self):
        try:
            url = urlparse(self.path)
            if url.path == "/api/ingest":
                return self._ingest(parse_qs(url.query))
            if url.path == "/api/class":
                return self._upload_class()
            body = self._body()
            if self.path == "/api/attempt":
                return self._save_attempt(body)
            if self.path == "/api/run":
                run = current["run"]
                if run and run.status == "running":
                    return self._send(409, {"error": "A run is already in progress."})
                goal = str(body.get("goal") or "").strip()
                if not goal:
                    return self._send(400, {"error": "Give the colleague a goal."})
                scripts = body.get("scripts") if isinstance(body.get("scripts"), dict) else None
                assessment = str(body.get("assessment") or "essay")
                if not offered(assessment):
                    return self._send(400, {"error": "That kind of assessment is not available."})
                what = "the PC assembly practical" if assessment == "practical" else f"the {tools.TESTS.get(assessment)} test"
                if assessment != "essay" and scripts:
                    return self._send(400, {"error": f"Photographed scripts are essays. Clear them to mark {what}."})
                data_dir = DATA
                if body.get("class"):
                    if assessment != "essay":
                        return self._send(400, {"error": "An uploaded class is for essays. Switch back to Essays, or use the sample class."})
                    try:
                        data_dir = str(classes.class_folder(class_root(), body.get("class")))
                    except classes.ClassError as e:
                        return self._send(400, {"error": str(e)})
                pages, batch = None, None
                if scripts:
                    batch, order = scripts.get("batch"), scripts.get("order")
                    try:
                        pages = ingest.load_pages(uploads(), batch, order if isinstance(order, list) else None)
                    except ingest.IngestError as e:
                        return self._send(400, {"error": str(e)})
                current["run"] = Run(make_llm(), goal, data_dir, OUTPUT, bool(body.get("inject_fault")),
                                     pages=pages, batch=batch, inject_ocr_fault=bool(body.get("inject_ocr_fault")),
                                     assessment=assessment, live_attempts=live_attempts(),
                                     review=bool(body.get("review")))
                current["run"].start()
                return self._send(200, {"ok": True})
            if self.path == "/api/review":
                run = current["run"]
                if not run or not run.approve(bool(body.get("go")), body.get("note") or ""):
                    return self._send(400, {"error": "The run is not waiting for the materials to be checked."})
                return self._send(200, {"ok": True})
            if self.path == "/api/resolve" and current["run"]:
                if body.get("kind") == "script":
                    ok = current["run"].resolve_script(str(body.get("id")), str(body.get("choice")), body.get("learner") or None,
                                                       body.get("name") or None, body.get("email") or None)
                    return self._send(200, {"ok": True}) if ok else self._send(400, {"error": "That script is not waiting for that decision."})
                ok = current["run"].resolve(str(body.get("id")), str(body.get("choice")))
                return self._send(200, {"ok": True}) if ok else self._send(400, {"error": "That essay is not waiting for a decision."})
            self._send(404, {"error": "not found"})
        except (BrokenPipeError, ConnectionError):
            pass
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    tools.load_env(ROOT / ".env")
    host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))
    llm = make_llm()
    try:
        server = Server((host, port), Handler)
    except OSError as e:
        raise SystemExit(f"Cannot start on port {port}: {e}\nIs Marking Colleague already running in another window? "
                         "Close it, or set PORT=8001 in .env.")
    backup = getattr(llm, "backup", None)
    print(f"Marking Colleague on http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}  (LLM: {llm.name}, {llm.model}"
          + (f"; {backup.name}, {backup.model} if Gemini is busy)" if backup else ")"))
    if llm.name == "mock":
        print("No GEMINI_API_KEY or OPENROUTER_API_KEY found: running in offline mock mode. Put a key in .env for real marking.")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
