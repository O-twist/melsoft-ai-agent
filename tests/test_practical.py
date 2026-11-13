"""The PC assembly practical: attempt logs marked like essays, with every mark held against what the log shows.

Run:  python -m unittest discover tests      Offline: the agents' replies come from the mock.
"""
import json
import os
import re
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

import run as server  # noqa: E402
from app import ingest, tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the PC assembly practical against the rubric and send every learner personalised feedback."
WHOLE_JOB = (GOAL + " Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on "
             "the class's weakest area with exercises.")


class Scripted(Mock):
    """The mock, recording what each agent was told, with chosen replies altered."""

    def __init__(self, **changes):
        super().__init__()
        self.changes, self.seen, self.told = changes, [], {}

    def call(self, task, system, prompt, data=None, log=None):
        self.seen.append(task)
        self.told.setdefault(task, []).append(system + "\n" + prompt)
        reply = super().call(task, system, prompt, data, log)
        change = self.changes.get(task)
        return change(reply, self.seen.count(task)) if change else reply


def run(goal=GOAL, llm=None, **kw):
    r = Run(llm or Mock(), goal, DATA, tempfile.mkdtemp(), assessment="practical", **kw)
    r._guarded()
    return r


def rubric():
    return tools.load_rubric(DATA, "practical")


def attempt(learner):
    return tools.clean_attempt(json.loads((DATA / "attempts" / f"{learner}.json").read_text(encoding="utf-8")), rubric()["parts"])


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


# ---- the attempt log, and what it allows ---------------------------------------------------------------

class AttemptLog(unittest.TestCase):
    def test_the_practical_has_its_own_rubric_and_outcomes_and_the_essay_keeps_its_own(self):
        r = rubric()
        self.assertEqual((r["kind"], r["work"], r["total"], r["parts"][0], r["parts"][-1]), ("practical", "practical attempt", 40, "motherboard", "PSU"))
        outcomes = tools.load_outcomes(DATA, r)
        self.assertEqual([o["id"] for o in outcomes], [f"H{n}" for n in range(1, 7)])
        self.assertTrue(all(o["criteria"] for o in outcomes))  # every hardware outcome serves part of the rubric
        essay = tools.load_rubric(DATA)
        self.assertEqual((essay["kind"], essay["work"]), ("essay", "essay"))
        self.assertEqual([o["id"] for o in tools.load_outcomes(DATA, essay)], [f"W{n}" for n in range(1, 9)])

    def test_an_attempt_is_replayed_against_the_correct_order(self):
        text = tools.render_attempt(attempt("E02"), rubric())
        self.assertIn("Correct order: motherboard, CPU, RAM, GPU, SSD, PSU.", text)
        self.assertIn("2. Wrong: placed the GPU before the CPU at 0:41. It was taken out again.", text)
        self.assertIn("3. Wrong: placed the RAM before the CPU at 0:58.", text)
        self.assertIn("4. Right: installed the CPU.", text)
        self.assertIn("Finished: yes. Installed: 6 of 6 parts.", text)
        unfinished = tools.render_attempt(attempt("E06"), rubric())
        self.assertIn("Not installed when the learner stopped: SSD, PSU.", unfinished)
        self.assertIn("1. Wrong: placed the CPU before the motherboard at 0:12.", unfinished)

    def test_facts_are_counted_in_code(self):
        parts = rubric()["parts"]
        self.assertEqual(tools.attempt_facts(attempt("E06"), parts),
                         {"installed": 4, "parts": 6, "wrong": 4, "mistakes": 4, "slot_misses": 0, "hints": 3, "completed": False, "seconds": 540})
        e03 = tools.attempt_facts(attempt("E03"), parts)  # a part dropped outside its slot is a mistake, not an order error
        self.assertEqual((e03["wrong"], e03["mistakes"], e03["slot_misses"], e03["completed"]), (0, 1, 1, True))
        claims = tools.clean_attempt({"order_tried": ["motherboard", "CPU"], "completed": True}, parts)
        self.assertFalse(tools.attempt_facts(claims, parts)["completed"])  # "completed" is not taken on trust
        for nonsense in (None, "x", {"order_tried": "all", "wrong_placements": [None, 3], "hints": "lots"}):
            a = tools.clean_attempt(nonsense, parts)
            self.assertEqual((a["order_tried"], a["hints"]), ([], 0))
            self.assertIn("Installed: 0 of 6 parts", tools.render_attempt(a, rubric()))

    def test_a_mark_above_what_the_log_allows_is_a_problem(self):
        r = rubric()
        facts = tools.attempt_facts(attempt("E06"), r["parts"])
        self.assertEqual({k: v[0] for k, v in tools.practical_ceilings(r, facts).items()}, {"order": 3, "correctness": 10, "efficiency": 4})
        mark = lambda o, c, e: {"scores": {"order": {"score": o}, "correctness": {"score": c}, "efficiency": {"score": e}}}
        self.assertEqual(tools.check_practical(mark(3, 10, 4), r, facts), [])
        problems = tools.check_practical(mark(15, 12, 9), r, facts)
        self.assertEqual(problems, [
            "Build order: 15 is more than the attempt log allows (at most 3, since 4 wrong placements in the log).",
            "Correct installation: 12 is more than the attempt log allows (at most 10, since only 4 of 6 parts were installed).",
            "Efficiency and independence: 9 is more than the attempt log allows (at most 4, since 3 hints used and 540 seconds is more than twice the target).",
        ])
        perfect = tools.attempt_facts(attempt("E01"), r["parts"])
        self.assertEqual(tools.check_practical(mark(15, 15, 10), r, perfect), [])

    def test_learners_get_their_own_attempt_and_nothing_from_the_essays(self):
        subs = tools.load_attempts(DATA, tools.load_submissions(DATA), rubric())
        by = {s["id"]: s for s in subs}
        self.assertEqual((by["E08"]["text"], by["E08"]["attempt"], by["E08"]["source"]), ("", None, None))  # no attempt on record
        self.assertTrue(by["E02"]["text"].startswith("PC assembly practical: attempt log"))
        self.assertEqual({s["previous"] for s in subs}, {None})  # essay marks say nothing about this practical
        self.assertEqual(by["E10"]["attempt"]["wrong"], 4)


# ---- the workflow ----------------------------------------------------------------------------------

class Workflow(unittest.TestCase):
    def test_the_essay_default_is_untouched(self):
        r = Run(Mock(), "Mark the essays and send every learner feedback.", DATA, tempfile.mkdtemp())
        r._guarded()
        self.assertEqual((r.assessment, r.rubric["kind"], r.noun), ("essay", "essay", "essay"))
        self.assertTrue(all("attempt" not in s for s in r.subs))
        self.assertEqual(r.stats["delivered"], 11)
        self.assertIn("11 essays marked", r.events[-1]["msg"])

    def test_attempts_are_marked_checked_against_the_log_and_delivered(self):
        llm = Scripted()
        r = run(llm=llm)
        self.assertEqual(r.status, "done")
        self.assertEqual(r.snapshot()["assessment"], "practical")
        by = {s["id"]: s for s in r.subs}
        self.assertEqual(by["E08"]["status"], "resubmit")
        self.assertEqual(by["E08"]["feedback"]["subject"], "Please redo the PC assembly practical")
        self.assertEqual((r.stats["delivered"], r.stats["sent_back"]), (11, 0))
        for s in r.subs:
            if not s["final"]:
                continue
            self.assertEqual(tools.check_practical(s["final"], r.rubric, s["attempt"]), [], s["id"])  # never above the log
            for c in r.rubric["criteria"]:  # every piece of evidence is a line of that learner's own log
                self.assertTrue(tools.quote_in_text(s["final"]["scores"][c["id"]]["evidence"], s["text"]), (s["id"], c["id"]))
            self.assertIn("practical", s["feedback"]["body"].lower())
        self.assertEqual((by["E01"]["final"]["total"], by["E06"]["final"]["total"]), (40, 15))
        self.assertIn("11 practical attempts marked", r.events[-1]["msg"])
        report = (r.out_dir / "class_report.md").read_text(encoding="utf-8")
        self.assertIn("across 11 practical attempts", report)
        self.assertEqual(len(list((r.out_dir / "outbox").glob("*.txt"))), 12)
        # every agent was told about attempt logs, not essays
        marker = llm.told["mark"][0]
        self.assertIn("=== ATTEMPT E01 ===", marker)
        self.assertNotRegex(marker, re.compile("essay", re.I))
        self.assertIn("Computer Applications Technology teacher", marker)
        self.assertIn("PC assembly practical", llm.told["feedback"][0])
        json.dumps(r.snapshot())

    def test_a_mark_the_log_does_not_allow_is_sent_back_and_corrected(self):
        def generous(reply, nth):
            if nth == 1:
                for m in reply["marks"]:
                    if m["id"] == "E02":
                        m["scores"]["order"]["score"] = 15  # E02 tried two parts out of order: at most 9
            return reply
        r = run(llm=Scripted(mark=generous))
        s = r._sub("E02")
        self.assertEqual((s["status"], s["final"]["scores"]["order"]["score"]), ("delivered", 9))
        self.assertEqual((r.stats["sent_back"], r.stats["fixed"]), (1, 1))
        reject = next(e for e in r.events if e["kind"] == "REJECT" and e["sid"] == "E02")
        self.assertIn("Build order: 15 is more than the attempt log allows (at most 9, since 2 wrong placements in the log).", reject["msg"])

    def test_evidence_that_is_not_in_the_log_is_caught(self):
        def invents(reply, nth):
            if nth == 1:
                for m in reply["marks"]:
                    if m["id"] == "E01":  # a perfect build: this never happened
                        m["scores"]["order"]["evidence"] = "placed the GPU before the motherboard"
            return reply
        r = run(llm=Scripted(mark=invents))
        reject = next(e for e in r.events if e["kind"] == "REJECT" and e["sid"] == "E01")
        self.assertIn("Build order: the quoted evidence does not appear in the attempt log.", reject["msg"])
        self.assertEqual(r._sub("E01")["status"], "delivered")
        self.assertTrue(tools.quote_in_text(r._sub("E01")["final"]["scores"]["order"]["evidence"], r._sub("E01")["text"]))

    def test_injected_fault_is_caught_by_the_log_and_the_blind_second_mark(self):
        clean = run()
        r = run(inject_fault=True)
        test = next(e for e in r.events if e["kind"] == "TEST" and e["sid"])
        self.assertIn("changed from 9 to 15", test["msg"])
        reject = next(e for e in r.events if e["kind"] == "REJECT" and e["sid"] == test["sid"])
        self.assertIn("more than the attempt log allows", reject["msg"])
        self.assertIn("the Reviewer gave 9", reject["msg"])
        self.assertEqual({s["id"]: s["final"] and s["final"]["total"] for s in r.subs},
                         {s["id"]: s["final"] and s["final"]["total"] for s in clean.subs})

    def test_coach_designer_and_the_cross_check_work_on_hardware(self):
        llm = Scripted()
        r = run(WHOLE_JOB, llm=llm)
        self.assertEqual(r.status, "done")
        flagged = {e["id"]: e for e in r.support["learners"]}
        self.assertEqual(list(flagged), ["E06", "E08", "E10"])
        self.assertEqual([s["kind"] for s in flagged["E06"]["signs"]], ["below", "weak_area", "weak_area"])
        hardware = {o["id"] for o in r.outcomes}
        for e in flagged.values():
            self.assertEqual(e["status"], "ready", e["id"])
            self.assertTrue({st["outcome"] for st in e["plan"]["steps"]} <= hardware)
            if e["plan"]["evidence"]:
                self.assertTrue(tools.quote_in_text(e["plan"]["evidence"], r._sub(e["id"])["text"]))
        self.assertIn("From the attempt log:", (r.out_dir / "support_plans.md").read_text(encoding="utf-8"))
        lesson = r.lesson
        self.assertEqual((lesson["status"], lesson["target"]["id"]), ("ready", "order"))
        self.assertTrue(set(lesson["outcomes"]) <= hardware)
        self.assertTrue(all(ex["check"]["outcome"] == ex["outcome"] for ex in lesson["exercises"] if ex["status"] != "dropped"))
        # Kabelo is also weak on efficiency: the first lesson had no support work for it, so it went back once
        self.assertEqual(r.consistency["status"], "agreed")
        self.assertEqual([item["agent"] for item in r.consistency["opened"]], ["DS"])
        self.assertIn("Efficiency and independence", r.consistency["opened"][0]["text"])
        self.assertTrue(all(item["exercise"] for item in r.consistency["coverage"]))
        self.assertEqual(llm.seen.count("align_lesson"), 1)
        self.assertNotRegex(llm.told["lesson"][0], re.compile("essay", re.I))
        self.assertEqual(r.files, ["support_plans.md", "lesson_plan.md", "marks.csv", "class_report.md"])
        self.assertIn("H6", (r.out_dir / "lesson_plan.md").read_text(encoding="utf-8"))

    def test_photographed_scripts_are_not_read_for_a_practical(self):
        root = tempfile.mkdtemp()
        batch = ingest.new_batch(root)
        ingest.add_pages(root, batch, ingest.sample_files(DATA))
        llm = Scripted()
        r = run(llm=llm, pages=ingest.load_pages(root, batch), batch=batch, inject_ocr_fault=True)
        self.assertEqual((r.status, r.intake, r.inject_ocr_fault), ("done", None, False))
        self.assertNotIn("CL", r.agent_state)
        self.assertFalse({"intake", "read_page"} & set(llm.seen))


# ---- the web server ---------------------------------------------------------------------------------

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

    def test_the_practical_is_offered_behind_a_flag(self):
        idle = self.request("/api/state")[1]
        self.assertEqual((idle["features"], idle["assessment"]), ({"practical": True}, "essay"))
        self.assertEqual(self.request("/api/run", {"goal": GOAL, "assessment": "poetry"})[0], 400)
        code, out = self.request("/api/run", {"goal": GOAL, "assessment": "practical", "scripts": {"batch": "abc", "order": []}})
        self.assertEqual((code, "Photographed scripts are essays" in out["error"]), (400, True))
        with mock.patch.dict(os.environ, {"PRACTICAL_LAB": "0"}):
            self.assertEqual(self.request("/api/state")[1]["features"], {"practical": False})
            self.assertEqual(self.request("/api/run", {"goal": GOAL, "assessment": "practical"})[0], 400)

        self.assertEqual(self.request("/api/run", {"goal": GOAL, "assessment": "practical", "inject_fault": True}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.request("/api/state?since=999999")[1]["status"] == "done", 30))
        done = self.request("/api/state")[1]
        self.assertEqual((done["assessment"], done["rubric"]["kind"], done["stats"]["fixed"]), ("practical", "practical", 1))
        self.assertEqual([o["id"] for o in done["outcomes"]], [f"H{n}" for n in range(1, 7)])


if __name__ == "__main__":
    unittest.main()
