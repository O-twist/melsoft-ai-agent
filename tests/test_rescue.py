"""Week 2, the theory-pass line, catch-up links, and the Windows proof check.

The sample Grade 12 CAT class is scored with no API key. Week 2 must come out the same
every time, and it must not rewrite the sample files.
"""
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"

import run as server  # noqa: E402
from app import risk, tools, week2, windows  # noqa: E402

DATA = Path(__file__).parent.parent / "data"


def learner(report, sid):
    return next(row for row in report["learners"] if row["id"] == sid)


class TheoryPass(unittest.TestCase):
    def test_bongani_passed_theory_and_is_still_high_risk(self):
        row = learner(risk.assess(DATA), "E10")
        self.assertEqual((row["overall"], row["result"], row["band"]), (57, "Pass", "High"))
        self.assertGreaterEqual(row["theory"]["percent"], 50)
        self.assertIn("Passed theory, but the practical shows gaps", row["theory_pass_note"])
        self.assertIn("RAM", row["theory_pass_note"])
        self.assertTrue(row["windows"])
        self.assertIn("Windows", row["moderation"])

    def test_a_low_risk_pass_does_not_get_that_line(self):
        row = learner(risk.assess(DATA), "E01")
        self.assertEqual(row["theory_pass_note"], "")
        self.assertEqual(row["band"], "Low")

    def test_the_sample_class_has_three_or_four_high_risk_learners(self):
        report = risk.assess(DATA)
        high = {row["id"] for row in report["learners"] if row["band"] == "High"}
        self.assertTrue({"E06", "E08", "E10"} <= high)
        self.assertLessEqual(len(high), 4)
        self.assertEqual(len(report["learners"]), 12)


class CatchUpLinks(unittest.TestCase):
    def test_bongani_can_open_the_ram_model_and_a_windows_task(self):
        row = learner(risk.assess(DATA), "E10")
        ram = next(gap for gap in row["gaps"] if gap.get("link") and gap["link"].get("target") == "ram")
        self.assertEqual(ram["link"]["kind"], "model")
        self.assertEqual(ram["outcome"], "H3")
        windows_gap = next(gap for gap in row["gaps"] if gap.get("link") and gap["link"]["kind"] == "windows")
        self.assertIn(windows_gap["link"]["target"], ("S1", "S2", "S3", "S4"))
        lab = next(gap for gap in row["gaps"] if gap.get("link") and gap["link"]["kind"] == "lab")
        self.assertTrue(lab["link"]["target"])

    def test_windows_outcomes_stay_out_of_the_essay_and_the_practical(self):
        self.assertEqual([o["id"] for o in tools.load_outcomes(DATA, tools.load_rubric(DATA))], [f"W{n}" for n in range(1, 9)])
        self.assertEqual(
            [o["id"] for o in tools.load_outcomes(DATA, tools.load_rubric(DATA, "practical"))],
            [f"H{n}" for n in range(1, 7)],
        )


class WindowsProofs(unittest.TestCase):
    def test_the_reviewer_agrees_only_when_the_proof_matches(self):
        folder = windows.review_answer(windows.task_by_id("S1"), "CAT Rescue")
        self.assertEqual(folder["verdict"], "agreed")
        self.assertEqual(folder["percent"], 100)
        wrong = windows.review_answer(windows.task_by_id("S4"), "8 GB")
        self.assertEqual(wrong["verdict"], "disagreed")
        self.assertEqual(wrong["percent"], 0)
        half = windows.review_answer(windows.task_by_id("S4"), "Liber-V")
        self.assertEqual((half["verdict"], half["percent"]), ("partly", 50))
        full = windows.review({"S1": "CAT Rescue", "S2": "Windows 11 Release", "S3": "Select a theme to apply", "S4": "Liber-V NS14A8"}, "E10")
        self.assertEqual(full["agreed"], 4)
        self.assertEqual(full["outcomes"]["S4"]["percent"], 100)

    def test_the_checklist_does_not_give_the_answers_away(self):
        shown = json.dumps(windows.public_tasks())
        self.assertNotIn("ns14a8", shown.lower())
        self.assertNotIn("select a theme to apply", shown.lower())
        self.assertNotIn("windows 11 release", shown.lower())
        self.assertIn("What device name and model does System show?", shown)


class WeekTwo(unittest.TestCase):
    def test_week_two_is_deterministic_and_moves_bongani(self):
        before_text = (DATA / "attempts" / "E10.json").read_text(encoding="utf-8")
        first = week2.project(DATA)
        second = week2.project(DATA)
        self.assertEqual(
            [(row["id"], row["risk_after"], row["band_after"]) for row in first["changes"]],
            [(row["id"], row["risk_after"], row["band_after"]) for row in second["changes"]],
        )
        self.assertEqual((DATA / "attempts" / "E10.json").read_text(encoding="utf-8"), before_text)
        bongani = next(row for row in first["changes"] if row["id"] == "E10")
        self.assertGreater(bongani["risk_before"], bongani["risk_after"])
        self.assertNotEqual(bongani["band_before"], bongani["band_after"])
        self.assertEqual(bongani["result_before"], "Pass")
        self.assertEqual([step["id"] for step in first["loop"]], ["plan", "do", "check", "correct", "deliver"])
        after = learner(first["after"], "E10")
        self.assertLess(after["risk"], 45)

    def test_an_unknown_learner_is_refused(self):
        self.assertFalse(week2.project(DATA, learner_id="NOBODY")["ok"])


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._output, cls._run, cls._week = server.OUTPUT, server.current["run"], server.current.get("week2")
        server.OUTPUT = Path(tempfile.mkdtemp())
        server.current["run"] = None
        server.current["week2"] = None
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.OUTPUT = cls._output
        server.current["run"] = cls._run
        server.current["week2"] = cls._week

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read())

    def test_week_two_and_a_windows_proof_reach_the_risk_score(self):
        tasks = json.loads(urllib.request.urlopen(self.base + "/api/windows", timeout=20).read())
        self.assertEqual([task["id"] for task in tasks["tasks"]], ["S1", "S2", "S3", "S4"])
        self.assertNotIn("sample", tasks["tasks"][0])
        week = self.post("/api/week2", {})
        self.assertIn("Bongani", week["summary"])
        state = json.loads(urllib.request.urlopen(self.base + "/api/state", timeout=20).read())
        self.assertEqual(state["week2"]["changes"][0]["id"], week["changes"][0]["id"])
        saved = self.post("/api/windows", {"learner_id": "E01", "answers": {"S1": "wrong folder", "S4": "8 GB"}})
        self.assertEqual(saved["outcomes"]["S1"]["verdict"], "disagreed")
        report = json.loads(urllib.request.urlopen(self.base + "/api/risk", timeout=20).read())
        thandi = learner(report, "E01")
        self.assertLess(next(row["percent"] for row in thandi["windows"] if row["id"] == "S1"), 100)
        self.assertEqual(self.post("/api/week2", {"reset": True}), {"ok": True})


if __name__ == "__main__":
    unittest.main()
