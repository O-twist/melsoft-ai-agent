"""The teacher reads the memo, the rubric and every script before the Planner plans. Offline, on the mock."""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"

import run as server  # noqa: E402
from app import agents, classes, mock, tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the essays and send every learner feedback."


def wait_for(condition, seconds=10):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


class Recording(Mock):
    def __init__(self):
        super().__init__()
        self.prompts = {}

    def call(self, task, system, prompt, data=None, log=None):
        self.prompts.setdefault(task, []).append(prompt)
        return super().call(task, system, prompt, data, log)


class Memo(unittest.TestCase):
    def test_the_memo_is_loaded_with_the_rubric_and_given_to_both_markers(self):
        rubric = tools.load_rubric(DATA)
        self.assertEqual(rubric["memo"]["file"], "memo.md")
        self.assertIn("social media", rubric["memo"]["terms"])
        llm = Recording()
        r = Run(llm, GOAL, DATA, tempfile.mkdtemp())
        r._guarded()
        self.assertEqual(r.status, "done")
        for task in ("mark", "review"):
            self.assertTrue(all("MARKING MEMO" in p and "Points a learner may raise" in p for p in llm.prompts[task]), task)
        self.assertIn("Marking memo: provided", llm.prompts["plan"][0])

    def test_without_a_memo_the_rubric_alone_is_used(self):
        folder = Path(tempfile.mkdtemp())
        shutil.copytree(DATA, folder, dirs_exist_ok=True)
        (folder / "memo.md").unlink()
        rubric = tools.load_rubric(folder)
        self.assertIsNone(rubric["memo"])
        self.assertNotIn("MARKING MEMO", agents._rubric_text(rubric))
        self.assertEqual(tools.topic_terms(rubric), ["technology"])  # taken from the task that was set

    def test_the_topic_check_follows_the_memo_not_the_code(self):
        rubric = tools.load_rubric(DATA)
        soccer = (DATA / "essays" / "E06.txt").read_text(encoding="utf-8")
        on_tech = mock._score(soccer, rubric)["content"]["score"]
        rubric["memo"] = {**rubric["memo"], "terms": ["soccer", "chiefs", "pirates", "stadium"]}
        on_soccer = mock._score(soccer, rubric)["content"]["score"]
        self.assertGreater(on_soccer, on_tech)

    def test_the_canned_exercises_are_only_used_for_the_sample_topic(self):
        brief = {"weakest": {"id": "content", "name": "Content", "pct": 40}, "minutes": 45, "flagged": 0, "marked": 3}
        outcomes = tools.load_outcomes(DATA, tools.load_rubric(DATA))
        sample = mock._lesson({**brief, "task": tools.load_rubric(DATA)["task"]}, outcomes)
        other = mock._lesson({**brief, "task": "Write a letter to your principal about school uniforms."}, outcomes)
        self.assertTrue(any("Technology has done more good" in e["task"] for e in sample["exercises"]))
        self.assertFalse(any("Technology" in e["task"] for e in other["exercises"]))

    def test_a_class_with_its_own_rubric_does_not_get_the_sample_memo(self):
        root = Path(tempfile.mkdtemp())
        rubric = (DATA / "rubric.json").read_bytes()
        cls = b"id,name\nA1,Ann\n"
        _, own_rubric = classes.create_class(root, DATA, cls, [("A1.txt", b"x " * 100)], rubric=rubric)
        self.assertFalse(own_rubric["memo"])
        _, own_memo = classes.create_class(root, DATA, cls, [("A1.txt", b"x " * 100)], rubric=rubric,
                                           memo=b"# Memo\n\n## Key terms\n\nuniform, school\n")
        self.assertTrue(own_memo["own_memo"] and own_memo["memo"])
        _, sample = classes.create_class(root, DATA, cls, [("A1.txt", b"x " * 100)])
        self.assertTrue(sample["memo"] and not sample["own_memo"])
        with self.assertRaises(classes.ClassError):
            classes.create_class(root, DATA, cls, [], memo=b"   ")


class Gate(unittest.TestCase):
    def start(self, **kw):
        r = Run(Mock(), GOAL, DATA, tempfile.mkdtemp(), review=True, **kw)
        r.start()
        self.assertTrue(wait_for(lambda: r.review["waiting"]))
        return r

    def test_nothing_is_planned_until_the_teacher_says_go(self):
        r = self.start()
        time.sleep(0.2)
        self.assertIsNone(r.plan)
        self.assertEqual(r.agent_state["MK"], "waiting")
        m = r.materials()
        self.assertEqual(m["memo"]["file"], "memo.md")
        self.assertEqual(len(m["learners"]), 12)
        self.assertIn("too_short", next(x for x in m["learners"] if x["id"] == "E08")["flags"])
        self.assertTrue(all("text" in x for x in m["learners"]))
        self.assertIn("Waiting for the teacher", r.events[-1]["msg"])
        self.assertTrue(r.approve(True, "Be strict on language."))
        self.assertFalse(r.approve(True))  # only once
        self.assertTrue(wait_for(lambda: r.status == "done"))
        self.assertIsNotNone(r.plan)
        self.assertIn("Be strict on language.", r.goal)
        said = [e["msg"] for e in r.events if e["kind"] == "HUMAN"]
        self.assertTrue(any("said to go ahead" in s for s in said))

    def test_the_teacher_can_stop_before_planning(self):
        r = self.start()
        self.assertTrue(r.approve(False, "Wrong memo."))
        self.assertTrue(wait_for(lambda: r.status == "failed"))
        self.assertIsNone(r.plan)
        self.assertIn("before planning", r.events[-1]["msg"])

    def test_without_review_the_run_does_not_wait(self):
        r = Run(Mock(), GOAL, DATA, tempfile.mkdtemp())
        r._guarded()
        self.assertEqual(r.status, "done")
        self.assertFalse(r.approve(True))


class Api(unittest.TestCase):
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

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_materials_before_and_during_a_run(self):
        code, before = self.call("/api/materials?assessment=essay")
        self.assertEqual(code, 200)
        self.assertEqual((before["memo"]["file"], len(before["learners"])), ("memo.md", 12))
        self.assertEqual(self.call("/api/materials?assessment=practical")[1]["memo"]["file"], "practical_memo.md")
        self.assertEqual(self.call("/api/review", {"go": True})[0], 400)

        self.assertEqual(self.call("/api/run", {"goal": GOAL, "review": True})[0], 200)
        self.assertTrue(wait_for(lambda: self.call("/api/state")[1]["review"]["waiting"]))
        code, during = self.call("/api/materials?source=run")
        self.assertEqual((code, len(during["learners"])), (200, 12))
        self.assertIsNone(self.call("/api/state")[1]["plan"])
        self.assertEqual(self.call("/api/review", {"go": True}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.call("/api/state")[1]["status"] == "done"))


if __name__ == "__main__":
    unittest.main()
