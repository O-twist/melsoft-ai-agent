"""How we corrected ourselves: the run's self-corrections, rebuilt from its log.  Offline, on the mock."""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"

import run as server  # noqa: E402
from app import ingest, story  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the essays and send every learner feedback."
WHOLE_JOB = ("Mark the Grade 10 essays against the rubric and send every learner personalised feedback. Tell me who is "
             "falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.")
PRACTICAL = "Mark the PC assembly practical against the rubric and send every learner feedback."


class Scripted(Mock):
    def __init__(self, **changes):
        super().__init__()
        self.changes, self.seen = changes, []

    def call(self, task, system, prompt, data=None, log=None):
        self.seen.append(task)
        reply = super().call(task, system, prompt, data, log)
        change = self.changes.get(task)
        return change(reply, self.seen.count(task)) if change else reply


def run(goal=GOAL, llm=None, **kw):
    r = Run(llm or Mock(), goal, DATA, tempfile.mkdtemp(), **kw)
    r._guarded()
    return r


def stories(r):
    return r.corrections()["stories"]


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


class Stories(unittest.TestCase):
    def test_a_clean_run_has_nothing_to_tell(self):
        r = run()
        self.assertEqual(r.corrections(), {"stories": [], "counts": {}, "planted": 0})
        self.assertIn("Every check passed first time", (r.out_dir / "corrections.md").read_text(encoding="utf-8"))
        self.assertNotIn("corrections.md", r.files)  # the essay run's files are as they were

    def test_a_planted_mark_is_one_story_from_fault_to_fix(self):
        r = run(inject_fault=True)
        (s,) = stories(r)
        self.assertEqual((s["subject"], s["caught_by"], s["fixed_by"], s["outcome"]), (f"{s['sid']}: mark", "Reviewer", "Marker", "fixed"))
        self.assertEqual(s["how"], ["blind second mark"])
        self.assertIn("deliberately changed", s["planted"])
        self.assertEqual([st["kind"] for st in s["steps"]], ["TEST", "REJECT", "FIX", "APPROVE"])
        self.assertEqual(r.corrections()["counts"], {"fixed": 1})
        text = (r.out_dir / "corrections.md").read_text(encoding="utf-8")
        self.assertIn("1 time a check stopped work in this run: 1 fixed. 1 of them began with a fault planted on purpose.", text)
        self.assertIn("Caught by the Reviewer, by blind second mark. Fixed by the Marker.", text)

    def test_the_whole_team_and_the_clerk_each_tell_their_own_story(self):
        root = tempfile.mkdtemp()
        batch = ingest.new_batch(root)
        ingest.add_pages(root, batch, ingest.sample_files(DATA))
        r = run(WHOLE_JOB, inject_fault=True, pages=ingest.load_pages(root, batch), batch=batch, inject_ocr_fault=True)
        by = {s["subject"]: s for s in stories(r)}
        p01, p03, p05 = (by[f"Page {p} of the handwritten scripts"] for p in ("p01", "p03", "p05"))
        self.assertEqual((p01["outcome"], bool(p01["planted"]), p01["how"]), ("fixed", True, ["code check of the lines transcribed against the lines on the page"]))
        self.assertEqual((p03["outcome"], p03["how"]), ("fixed", ["code check of the name against the class list"]))
        self.assertEqual((p05["outcome"], p05["how"]), ("held", ["code check of the page numbers"]))
        exercise = by["Exercise X2 in the lesson"]
        self.assertEqual((exercise["outcome"], exercise["how"], exercise["fixed_by"], bool(exercise["planted"])),
                         ("fixed", ["blind trial by the Reviewer"], "Designer", True))
        align = by["The catch-up plans and the lesson"]
        self.assertEqual((align["outcome"], align["how"]), ("fixed", ["cross-check of the catch-up plans against the lesson"]))
        self.assertEqual(r.corrections()["planted"], 3)
        json.dumps(r.snapshot()["corrections"])

        self.assertTrue(r.resolve_script("S3", "accept"))  # the teacher settles the held script: its page's story ends there
        self.assertTrue(wait_for(lambda: r._sub("E10")["status"] == "delivered"))
        p05 = next(s for s in stories(r) if s["subject"].startswith("Page p05"))
        self.assertEqual((p05["outcome"], p05["steps"][-1]["kind"]), ("teacher", "HUMAN"))
        self.assertTrue(wait_for(lambda: "decided by the teacher" in (r.out_dir / "corrections.md").read_text(encoding="utf-8")))

    def test_a_practical_mark_is_caught_by_the_log_as_well_as_the_reviewer(self):
        r = run(PRACTICAL, inject_fault=True, assessment="practical")
        (s,) = stories(r)
        self.assertEqual(s["how"], ["code check against the attempt log", "blind second mark"])
        self.assertEqual(s["outcome"], "fixed")

    def test_held_dropped_prevented_and_teacher_endings(self):
        def wrong_mark(reply, nth):
            for m in reply["messages"]:
                if m["id"] == "E01":
                    m["body"] = m["body"].replace("/50", "/60")
            return reply
        r = run(llm=Scripted(feedback=wrong_mark))
        (s,) = stories(r)
        self.assertEqual((s["subject"], s["outcome"], s["how"]), ("E01: feedback message", "held", ["code check of the message"]))
        self.assertEqual([st["kind"] for st in s["steps"]], ["REJECT", "ESCALATE"])

        def nothing_to_work_on(reply, nth):
            reply["exercises"][3]["task"] = "Improve the paragraph that your teacher hands out in class."
            return reply
        r = run(GOAL + " Then draft a 30-minute lesson with exercises.", llm=Scripted(lesson=nothing_to_work_on))
        self.assertEqual([(s["subject"], s["outcome"]) for s in stories(r)], [("Exercise X4 in the lesson", "dropped")])

        def greedy(reply, nth):
            reply["exclude"] += [{"id": "E11", "reason": "It contains an instruction."}]
            return reply
        r = run(llm=Scripted(plan=greedy))
        (s,) = stories(r)
        self.assertEqual((s["subject"], s["outcome"], s["how"]), ("E11: what the plan left out", "prevented", ["a code guard"]))

        lower = lambda reply, nth: {"marks": [{**m, "scores": {**m["scores"], "content": {**m["scores"]["content"], "score": m["scores"]["content"]["score"] - 12}}}
                                              if m["id"] == "E01" else m for m in reply["marks"]]}
        rejects = lambda reply, nth: {"verdicts": [{**v, "approve": False, "reason": "Not convinced."} for v in reply["verdicts"]]}
        r = run(llm=Scripted(review=lower, verify=rejects))
        self.assertEqual(stories(r)[0]["outcome"], "held")
        self.assertTrue(r.resolve("E01", "reviewer"))
        self.assertTrue(wait_for(lambda: stories(r)[0]["outcome"] == "teacher"))

    def test_the_story_never_breaks_on_an_odd_log(self):
        odd = [{"t": 0, "agent": "RV", "kind": "REJECT", "msg": "Something unexpected.", "sid": None},
               {"t": 1, "agent": "XX", "kind": "APPROVE", "msg": "?", "sid": "E99"},
               {"t": 2, "agent": "RV", "kind": "REJECT", "msg": "Sent back to the Marker. Content: the quoted evidence does not appear in the essay.", "sid": "E01"}]
        out = story.corrections(odd)
        self.assertEqual([(s["subject"], s["how"], s["outcome"]) for s in out["stories"]],
                         [("E01: mark", ["code check that the quoted evidence is really there"], "open")])
        self.assertIn("## 1. E01: mark: still open", story.to_markdown(out))


class WebApi(unittest.TestCase):
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

    def test_the_panel_and_its_download(self):
        get = lambda path: urllib.request.urlopen(self.base + path, timeout=20)
        self.assertIsNone(json.loads(get("/api/state").read())["corrections"])
        req = urllib.request.Request(self.base + "/api/run", data=json.dumps({"goal": GOAL, "inject_fault": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20)
        self.assertTrue(wait_for(lambda: json.loads(get("/api/state?since=999999").read())["status"] == "done", 30))
        self.assertEqual(json.loads(get("/api/state").read())["corrections"]["counts"], {"fixed": 1})
        with get("/api/corrections.md") as r:
            self.assertEqual(r.headers["Content-Type"], "text/markdown; charset=utf-8")
            self.assertTrue(r.read().decode("utf-8").startswith("# How we corrected ourselves"))


if __name__ == "__main__":
    unittest.main()
