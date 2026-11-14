"""A run that finishes inside the request that starts it.  Run:  python -m unittest discover tests

On a serverless deployment (Vercel) a run cannot carry on after the reply, and the next request may land
on an instance that remembers nothing. So the whole loop happens in the one request, and the reply carries
the finished run with a picture of every moment on the way, for the browser to play back.
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

import run as server  # noqa: E402
from app import llm as llm_service  # noqa: E402
from app.llm import Fallback, Gemini, Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
PRACTICAL = ("Mark the PC assembly practical against the rubric and send every learner personalised feedback. "
             "Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the "
             "class's weakest area with exercises.")


class Recording(unittest.TestCase):
    def recorded(self, **kw):
        llm = Mock()
        llm.instant, llm.delay = True, 0.7
        r = Run(llm, PRACTICAL, DATA, tempfile.mkdtemp(), assessment="practical", record=True, **kw)
        r._guarded()
        return r, r.recording()

    def test_every_log_line_has_a_frame_and_the_last_one_is_the_end_of_the_run(self):
        # A frame is also kept each time an agent picks up or puts down work, so there are more frames than lines.
        r, rec = self.recorded()
        self.assertEqual(rec["status"], "done")
        frames = rec["frames"]
        counts = [f["n"] for f in frames]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(set(counts) - {0}, set(range(1, len(rec["events"]) + 1)))  # every log line has its moment
        times = [f["t"] for f in frames]
        self.assertEqual(times, sorted(times))  # the clock only moves forward
        last = frames[-1]
        self.assertEqual(last["stats"], rec["stats"])
        self.assertEqual({sid: at[0] for sid, at in last["subs"].items()}, {s["id"]: s["status"] for s in rec["subs"]})
        self.assertEqual(set(last["has"]), {"plan", "report", "support", "lesson", "consistency"})

    def test_the_frames_walk_through_the_loop_in_order(self):
        _, rec = self.recorded(inject_fault=True)
        frames = rec["frames"]
        self.assertEqual(frames[0]["has"], [])  # at the first line nothing is planned yet
        self.assertTrue(all(at == ["received", False, False, False, False] for at in frames[0]["subs"].values()))
        first = lambda test: next(i for i, f in enumerate(frames) if test(f))
        planned = first(lambda f: "plan" in f["has"])
        marked = first(lambda f: any(at[1] for at in f["subs"].values()))
        checked = first(lambda f: any(at[2] for at in f["subs"].values()))
        sent_back = first(lambda f: f["stats"]["sent_back"] > 0)
        corrected = first(lambda f: f["stats"]["fixed"] > 0)
        delivered = first(lambda f: any(at[4] for at in f["subs"].values()))
        self.assertEqual([planned, marked, checked, sent_back, corrected, delivered],
                         sorted([planned, marked, checked, sent_back, corrected, delivered]))
        self.assertLess(sent_back, corrected)
        working = {agent for f in frames for agent, state in f["agents"].items() if state == "working"}
        self.assertEqual(working, {"PL", "MK", "RV", "MS", "CO", "DS"})  # each of them was seen at work

    def test_the_run_clock_counts_the_pauses_it_did_not_take(self):
        r, rec = self.recorded()
        self.assertGreater(rec["elapsed"], 8)  # as long as the same run takes when it is watched live
        self.assertAlmostEqual(rec["frames"][-1]["t"], r.llm.calls * 0.7, delta=2)
        self.assertLess(r.ended - r.started, 5)  # but it really took almost no time
        spans = rec["spans"]
        self.assertTrue(all(s["end"] is not None and s["end"] >= s["start"] for s in spans))
        self.assertGreater(max(s["end"] for s in spans), 8)

    def test_the_text_files_travel_with_the_recording(self):
        _, rec = self.recorded(inject_fault=True)
        files = rec["file_texts"]
        self.assertEqual(set(files), {"marks.csv", "class_report.md", "support_plans.md", "lesson_plan.md", "corrections.md"})
        self.assertIn("E10", files["marks.csv"])
        self.assertIn("Fault injection is on", files["corrections.md"])
        self.assertFalse(list(k for k in files if "outbox" in k))  # learners' messages are not part of it

    def test_a_run_watched_live_is_not_recorded(self):
        r = Run(Mock(), PRACTICAL, DATA, tempfile.mkdtemp(), assessment="practical")
        r._guarded()
        self.assertEqual(r.frames, [])
        self.assertNotIn("frames", r.snapshot())


class InOneRequest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.OUTPUT = Path(tempfile.mkdtemp())
        server.current["run"] = None
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.current["run"] = None

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_on_vercel_the_reply_to_start_is_the_finished_run(self):
        with mock.patch.dict(os.environ, {"VERCEL": "1"}):
            code, out = self.request("/api/run", {"goal": PRACTICAL, "assessment": "practical", "inject_fault": True})
            self.assertEqual(code, 200)
            rec = out["run"]
            self.assertEqual(rec["status"], "done")
            self.assertEqual(rec["stats"]["delivered"], 11)
            self.assertEqual(rec["corrections"]["planted"], 2)
            self.assertTrue(rec["frames"])
            self.assertLess(len(json.dumps(out)), 1_000_000)  # small enough for one reply
            # The next request lands on an instance that remembers nothing: it must still answer, not fail.
            server.current["run"] = None
            code, state = self.request("/api/state")
            self.assertEqual((code, state["status"]), (200, "idle"))
            self.assertEqual(state["features"], {"practical": True, "uploads": False, "replay": True})
            bongani = next(row for row in state["risk"]["learners"] if row["id"] == "E10")
            self.assertEqual((bongani["risk"], bongani["band"], bongani["overall"], bongani["result"]), (53, "High", 57, "Pass"))
            # A second run straight after the first is not refused as "already running".
            self.assertEqual(self.request("/api/run", {"goal": PRACTICAL, "assessment": "practical"})[0], 200)

    def test_uploads_are_refused_where_files_do_not_outlive_a_request(self):
        with mock.patch.dict(os.environ, {"VERCEL": "1"}):
            for path in ("/api/ingest?sample=1", "/api/class"):
                code, out = self.request(path, {})
                self.assertEqual(code, 400)
                self.assertIn("switched off on this deployment", out["error"])

    def test_week_two_answers_in_one_request_too(self):
        with mock.patch.dict(os.environ, {"VERCEL": "1"}):
            server.current["run"] = None
            server.current["week2"] = None
            code, out = self.request("/api/week2", {"learner": "E10"})
            self.assertEqual(code, 200)
            row = next(c for c in out["changes"] if c["id"] == "E10")
            self.assertEqual((row["risk_before"], row["risk_after"], row["band_before"], row["band_after"],
                              row["overall_before"], row["overall_after"]), (53, 22, "High", "Low", 57, 78))
            server.current["week2"] = None

    def test_week_two_starts_from_week_one_as_marked_whatever_was_practised_since(self):
        server.current["run"] = None
        proofs = {"S1": "CAT Rescue", "S2": "Windows 11 Release", "S3": "Select a theme to apply", "S4": "Liber-V NS14A8"}
        self.assertEqual(self.request("/api/windows", {"learner_id": "E10", "answers": proofs})[0], 200)
        try:
            board = self.request("/api/risk")[1]
            now = next(row for row in board["learners"] if row["id"] == "E10")
            self.assertLess(now["risk"], 53)  # the practice counts on the board straight away
            code, out = self.request("/api/week2", {"learner": "E10"})
            row = next(c for c in out["changes"] if c["id"] == "E10")
            self.assertEqual((row["risk_before"], row["risk_after"], row["band_before"], row["band_after"],
                              row["overall_before"], row["overall_after"]), (53, 22, "High", "Low", 57, 78))
        finally:
            (server.live_windows() / "E10.json").unlink()
            server.current["week2"] = None

    def test_a_local_server_still_runs_in_the_background(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("VERCEL", None)
            os.environ.pop("RUN_IN_REQUEST", None)
            code, out = self.request("/api/run", {"goal": PRACTICAL, "assessment": "practical"})
            self.assertEqual((code, out), (200, {"ok": True}))  # no recording: the dashboard polls instead
            self.assertEqual(self.request("/api/state")[1]["features"]["uploads"], True)
            server.current["run"].work.acquire()  # wait for it to finish before the next test
            server.current["run"].work.release()


class LiveModelsInOneRequest(unittest.TestCase):
    def test_live_models_get_a_time_limit_and_the_offline_marker_never_waits(self):
        before = llm_service.HTTP_TIMEOUT
        try:
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g", "OPENROUTER_API_KEY": "o", "MOCK": ""}):
                os.environ.pop("LLM_DEADLINE", None)
                os.environ.pop("LLM_HTTP_TIMEOUT", None)
                llm = server.request_llm()
            self.assertIsInstance(llm, Fallback)
            self.assertEqual([b.name for b in llm.chain], ["gemini", "openrouter", "mock"])
            self.assertEqual(llm.deadline, 35)
            self.assertTrue(llm.chain[-1].instant)
            self.assertEqual([b.delays for b in llm.chain[:2]], [[2], [2]])
            self.assertEqual(llm_service.HTTP_TIMEOUT, 12)
            self.assertIsInstance(llm.chain[0], Gemini)
        finally:
            llm_service.HTTP_TIMEOUT = before

    def test_with_no_key_it_is_the_offline_marker_without_pauses(self):
        llm = server.request_llm()
        self.assertEqual((llm.name, llm.instant), ("mock", True))


if __name__ == "__main__":
    unittest.main()
