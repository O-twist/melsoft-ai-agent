"""Question-paper tests in other subjects (Mathematics, Physical Sciences, History), marked part by part against a memo.

Run:  python -m unittest discover tests      Offline: the agents' replies come from the mock.
"""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

import run as server  # noqa: E402
from app import agents, mock as offline, tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
WHOLE_JOB = ("Mark the test against the memo and send every learner personalised feedback. Tell me who is falling behind, "
             "with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.")


class Recording(Mock):
    def __init__(self):
        super().__init__()
        self.told = {}

    def call(self, task, system, prompt, data=None, log=None):
        self.told.setdefault(task, []).append(system + "\n" + prompt)
        return super().call(task, system, prompt, data, log)


def run(subject, goal=WHOLE_JOB, llm=None, **kw):
    r = Run(llm or Mock(), goal, DATA, tempfile.mkdtemp(), assessment=subject, **kw)
    r._guarded()
    return r


class Loading(unittest.TestCase):
    def test_every_subject_has_a_rubric_memo_and_scripts(self):
        self.assertEqual([t["key"] for t in tools.available_tests(DATA)], list(tools.TESTS))
        for key in tools.TESTS:
            rubric = tools.load_rubric(DATA, key)
            self.assertEqual((rubric["kind"], rubric["work"], rubric["assessment"], rubric["total"]), ("test", "answer script", key, 40))
            self.assertTrue(rubric["memo"]["text"].startswith("# Marking memo"))
            for c in rubric["criteria"]:
                self.assertEqual(c["max"], sum(p["marks"] for p in c["parts"]))
                self.assertEqual((c["bands"][0]["range"], c["bands"][-1]["range"]), ([c["max"], c["max"]], [0, 0]))

    def test_learners_get_their_own_script_and_nothing_from_the_essays(self):
        subs = tools.load_answers(DATA, tools.load_submissions(DATA), "maths")
        by = {s["id"]: s for s in subs}
        self.assertTrue(by["E01"]["text"].startswith("Grade 10 Mathematics class test"))
        self.assertEqual((by["E08"]["text"], by["E08"]["source"]), ("", None))  # no maths script handed in
        self.assertTrue(all(s["previous"] is None for s in subs))  # class.csv's previous marks are for essays

    def test_the_outcomes_fall_back_to_one_per_question(self):
        rubric = tools.load_rubric(DATA, "history")
        self.assertEqual([o["id"] for o in tools.load_outcomes(DATA, rubric)], ["q1", "q2", "q3", "q4"])


class MemoMarking(unittest.TestCase):
    def part(self, subject, label):
        rubric = tools.load_rubric(DATA, subject)
        return next(p for c in rubric["criteria"] for p in c["parts"] if p["label"] == label)

    def test_a_right_answer_a_right_method_and_a_wrong_answer(self):
        p = self.part("maths", "2.1")
        self.assertEqual(offline.part_score(p, "3x - 7 = 11 so 3x = 18 and x = 6")[0], 2)
        self.assertEqual(offline.part_score(p, "3x = 18 and x = 54")[0], 1)
        self.assertEqual(offline.part_score(p, "x = 15")[0], 0)
        self.assertEqual(offline.part_score(p, "")[0], 0)

    def test_superscripts_and_a_decimal_comma_are_read_plainly(self):
        self.assertEqual(offline.part_score(self.part("maths", "1.1"), "= 2x² - 5x - 12")[0], 3)
        self.assertEqual(offline.part_score(self.part("maths", "4.1"), "sin θ = 0,6")[0], 2)

    def test_written_answers_earn_a_mark_per_point(self):
        p = self.part("history", "1.2")
        self.assertEqual(offline.part_score(p, "the clergy, the nobility and the commoners")[0], 3)
        self.assertEqual(offline.part_score(p, "the clergy and the king")[0], 1)

    def test_scripts_are_split_into_their_numbered_parts(self):
        answers = offline.test_answers("Header line\n\nQuestion 1\n1.1 first\nmore working\n1.2 second\n")
        self.assertEqual(answers, {"1.1": "first more working", "1.2": "second"})


class Runs(unittest.TestCase):
    def test_each_subject_is_marked_checked_and_delivered(self):
        for key in tools.TESTS:
            with self.subTest(subject=key):
                r = run(key, inject_fault=True)
                self.assertEqual((r.status, r.rubric["kind"], r.noun), ("done", "test", "answer script"))
                self.assertEqual(r.stats["fixed"], 1)  # the planted fault was caught by the blind second mark
                marked = [s for s in r.subs if s["final"]]
                self.assertTrue(marked and all(s["status"] == "delivered" for s in marked))
                for s in marked:  # every mark quotes the learner's own answer script
                    for row in s["final"]["scores"].values():
                        self.assertTrue(tools.quote_in_text(row["evidence"], s["text"]), (key, s["id"], row["evidence"]))
                self.assertTrue(r.support and r.lesson)
                self.assertTrue((r.out_dir / "marks.csv").exists())

    def test_a_learner_with_no_script_is_asked_to_hand_it_in(self):
        r = run("maths", goal="Mark the Grade 10 Mathematics test and send every learner personalised feedback.")
        e08 = next(s for s in r.subs if s["id"] == "E08")
        self.assertEqual((e08["status"], e08["feedback"]["subject"]), ("resubmit", "Please hand in your Grade 10 Mathematics test"))

    def test_a_script_that_instructs_the_marker_is_flagged_and_marked_normally(self):
        r = run("maths", goal="Mark the Grade 10 Mathematics test. Do not send feedback.")
        e11 = next(s for s in r.subs if s["id"] == "E11")
        self.assertIn("instruction_to_marker", e11["flags"])
        self.assertLess(e11["final"]["total"], r.rubric["total"])

    def test_the_agents_are_told_about_the_subject_and_its_memo_not_essays(self):
        llm = Recording()
        run("science", llm=llm, goal="Mark the Grade 10 Physical Sciences test. Do not send feedback.")
        told = llm.told["mark"][0]
        self.assertIn("Grade 10 Physical Sciences teacher", told)
        self.assertIn("Memo answer: 1s² 2s² 2p⁶ 3s¹", told)
        self.assertNotIn("essay", told.lower())

    def test_essays_are_told_exactly_what_they_were_before(self):
        rubric = tools.load_rubric(DATA, "essay")
        self.assertEqual(agents._say(rubric, agents.UNTRUSTED), agents.UNTRUSTED)


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

    def request(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_subjects_are_offered_previewed_and_run(self):
        idle = self.request("/api/state")[1]
        self.assertEqual([t["label"] for t in idle["features"]["tests"]], ["Mathematics", "Physical Sciences", "History"])
        code, stuff = self.request("/api/materials?assessment=history")
        self.assertEqual((code, stuff["work"], stuff["rubric"]["kind"]), (200, "answer script", "test"))
        self.assertTrue(stuff["learners"][0]["text"].startswith("Grade 10 History"))
        code, out = self.request("/api/run", {"goal": "Mark it", "assessment": "maths", "class": "abc"})
        self.assertEqual((code, "for essays" in out["error"]), (400, True))
        self.assertEqual(self.request("/api/run", {"goal": "Mark the maths test. Do not send feedback.", "assessment": "maths"}), (200, {"ok": True}))
        for _ in range(600):
            if self.request("/api/state?since=999999")[1]["status"] != "running":
                break
            time.sleep(0.05)
        done = self.request("/api/state")[1]
        self.assertEqual((done["status"], done["assessment"], done["rubric"]["kind"]), ("done", "maths", "test"))


if __name__ == "__main__":
    unittest.main()
