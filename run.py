"""Start the Marking Colleague dashboard:  python run.py   then open http://localhost:8000"""
import json
import mimetypes
import time
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from app import classes, ingest, risk, store, story, tools, week2
from app import llm as llm_service
from app import windows as windows_station
from app.llm import make_llm
from app.orchestrator import AGENTS, Run

ROOT = Path(__file__).parent
DATA = os.getenv("DATA_DIR", str(ROOT / "data"))


def _output_dir():
    """Live files. On Vercel only /tmp can be written; the demo class stays in data/."""
    chosen = os.getenv("OUTPUT_DIR")
    if chosen:
        return Path(chosen)
    if os.getenv("VERCEL"):
        path = Path("/tmp/lablest-output")
        path.mkdir(parents=True, exist_ok=True)
        return path
    return ROOT / "output"


OUTPUT = _output_dir()
DIST = ROOT / "web" / "dist"
NOT_BUILT = (
    "<h1>Dashboard not built yet</h1><p>Run <code>npm install</code> and <code>npm run build</code> "
    "inside the <code>web</code> folder, then reload. The API is running.</p>"
)
mimetypes.add_type("model/gltf-binary", ".glb")  # the 3D model in the lesson view
DOWNLOADS = {".csv": "text/csv", ".md": "text/markdown", ".pdf": "application/pdf", ".txt": "text/plain"}
current = {"run": None, "week2": None}


def serverless():
    """True where a request cannot count on the next one reaching the same process (Vercel).

    There a run cannot carry on in the background after the reply, and what one instance wrote to disk is
    not there for the next. So the whole run happens inside the request that starts it, and the browser is
    handed the finished run to play back. RUN_IN_REQUEST=1 turns the same behaviour on anywhere, for testing.
    """
    return bool(os.getenv("VERCEL")) or os.getenv("RUN_IN_REQUEST") == "1"


def request_llm():
    """The model for a run that must finish inside one request: nothing waits, and live models get a time limit."""
    llm = make_llm()
    for backend in getattr(llm, "chain", [llm]):
        if backend.name == "mock":
            backend.instant = True
        else:
            backend.delays = [2]  # one short retry, then the next backend
    if hasattr(llm, "deadline") and not llm.deadline:
        llm.deadline = float(os.getenv("RUN_SECONDS", "35"))
    if not os.getenv("LLM_HTTP_TIMEOUT"):
        llm_service.HTTP_TIMEOUT = 12
    return llm


def features():
    """What this deployment can offer. Uploads need files that outlive a request, so they are local only."""
    return {"practical": practical_lab(), "uploads": not serverless(), "replay": serverless()}


def practical_lab():
    """The PC assembly practical is offered when its rubric is on disk, unless PRACTICAL_LAB=0 turns it off."""
    return os.getenv("PRACTICAL_LAB", "1") != "0" and (Path(DATA) / tools.RUBRIC_FILES["practical"]).exists()


def live_attempts():
    """Where attempts done in the dashboard's virtual lab are kept, apart from the sample files in data/attempts."""
    return OUTPUT / "attempts"


def live_windows():
    """Proof answers from the Windows checklist, apart from the sample rows in data/windows.json."""
    return OUTPUT / "windows"


def merged_windows(data_dir):
    """Sample station results, with a live checklist submission taking the place of that learner."""
    found = risk._load_windows(data_dir, None)
    folder = live_windows()
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("outcomes"), dict):
            found[str(data.get("learner_id") or path.stem)] = data["outcomes"]
    return found


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
                state["features"] = features()
                state["risk"] = self._risk_board(run, state.get("subs") if run else None)
                state["week2"] = current.get("week2") or store.load_week()
                return self._send(200, state)
            if url.path == "/api/risk":
                run = current["run"]
                return self._send(200, self._risk_board(run, run.subs if run else None))
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
            if url.path == "/api/windows":
                return self._send(200, {"tasks": windows_station.public_tasks()})
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
                data_dir = run.data_dir
                live = run.live_attempts or live_attempts()
                board = risk.assess(data_dir, overlay=overlay, assessment=run.assessment,
                                    live_dir=live, windows=merged_windows(data_dir))
            else:
                data_dir = DATA
                board = risk.assess(DATA, live_dir=live_attempts(), windows=merged_windows(DATA))
        except Exception as exc:
            return {"ok": False, "learners": [], "counts": {}, "error": f"{type(exc).__name__}: {exc}"}
        store.remember(board, data_dir)
        return board

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
            cid, summary = classes.create_class(class_root(), DATA, one("class_list"), essays, one("rubric"), one("outcomes"))
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

    def _class_dir(self):
        run = current["run"]
        return run.data_dir if run else DATA

    def _week2(self, body):
        """Simulate the rescue week and score the class again. Reset drops the comparison."""
        if body.get("reset"):
            current["week2"] = None
            store.clear_week()
            return self._send(200, {"ok": True})
        data_dir = self._class_dir()
        learner = str(body.get("learner") or "").strip() or None
        # Week 2 is measured from the class as it was marked in Week 1. Builds and Windows proofs handed in
        # from the lab since then are catch-up practice: they are part of the rescue week, not of its starting
        # point, so they are left out here. That keeps the before and after the same every time it is run.
        result = week2.project(data_dir, learner_id=learner)
        if not result.get("ok"):
            return self._send(400, {"error": result.get("error") or "Week 2 could not be scored."})
        current["week2"] = result
        store.remember_week(result, data_dir)
        return self._send(200, result)

    def _save_windows(self, body):
        """The Reviewer checks the proof answers and keeps them for the risk score."""
        data_dir = self._class_dir()
        learner = str(body.get("learner_id") or "").strip()
        known = {sub["id"] for sub in tools.load_submissions(data_dir)}
        if learner not in known:
            return self._send(400, {"error": "Choose a learner from the class list."})
        answers = body.get("answers") if isinstance(body.get("answers"), dict) else {}
        result = windows_station.review(answers, learner)
        folder = live_windows()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{learner}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        return self._send(200, result)

    def do_POST(self):
        try:
            url = urlparse(self.path)
            if url.path in ("/api/ingest", "/api/class") and serverless():
                self.rfile.read(int(self.headers.get("Content-Length") or 0))  # take the upload before refusing it
                return self._send(400, {"error": "Uploads are switched off on this deployment. Run LabLess on a computer to use your own class or photographed scripts."})
            if url.path == "/api/ingest":
                return self._ingest(parse_qs(url.query))
            if url.path == "/api/class":
                return self._upload_class()
            body = self._body()
            if url.path == "/api/attempt":
                return self._save_attempt(body)
            if url.path == "/api/week2":
                return self._week2(body)
            if url.path == "/api/windows":
                return self._save_windows(body)
            if url.path == "/api/run":
                run = current["run"]
                if run and run.status == "running":
                    return self._send(409, {"error": "A run is already in progress."})
                goal = str(body.get("goal") or "").strip()
                if not goal:
                    return self._send(400, {"error": "Give the colleague a goal."})
                scripts = body.get("scripts") if isinstance(body.get("scripts"), dict) else None
                assessment = str(body.get("assessment") or "essay")
                if assessment not in tools.RUBRIC_FILES or (assessment == "practical" and not practical_lab()):
                    return self._send(400, {"error": "That kind of assessment is not available."})
                if assessment == "practical" and scripts:
                    return self._send(400, {"error": "Photographed scripts are essays. Clear them to mark the PC assembly practical."})
                data_dir = DATA
                if body.get("class"):
                    if assessment == "practical":
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
                if serverless():
                    run = Run(request_llm(), goal, data_dir, OUTPUT, bool(body.get("inject_fault")),
                              assessment=assessment, live_attempts=live_attempts(), record=True)
                    current["run"] = run
                    run._guarded()  # the whole loop, inside this request
                    return self._send(200, {"ok": True, "run": run.recording()})
                current["run"] = Run(make_llm(), goal, data_dir, OUTPUT, bool(body.get("inject_fault")),
                                     pages=pages, batch=batch, inject_ocr_fault=bool(body.get("inject_ocr_fault")),
                                     assessment=assessment, live_attempts=live_attempts())
                current["run"].start()
                return self._send(200, {"ok": True})
            if url.path == "/api/resolve" and current["run"]:
                if body.get("kind") == "script":
                    ok = current["run"].resolve_script(str(body.get("id")), str(body.get("choice")), body.get("learner") or None)
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
        raise SystemExit(f"Cannot start on port {port}: {e}\nIs LabLess already running in another window? "
                         "Close it, or set PORT=8001 in .env.")
    backup = getattr(llm, "backup", None)
    print(f"LabLess on http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}  (LLM: {llm.name}, {llm.model}"
          + (f"; then {backup.name}, {backup.model}, if it cannot answer)" if backup else ")"))
    if llm.name == "mock":
        print("No GEMINI_API_KEY or OPENROUTER_API_KEY found: running in offline mock mode. Put a key in .env for real marking.")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
