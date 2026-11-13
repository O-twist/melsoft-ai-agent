"""Planner risk scores and the Matric Rescue score report.

The sample class must show the rescue story with no API key: at least three learners
in the high band, reasons a teacher can read, and a score report the Messenger can hand over.
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
from app import risk, tools  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
ATTEMPT = {
    "learner_id": "E01",
    "order_tried": ["RAM", "RAM", "motherboard", "CPU", "RAM", "GPU", "SSD", "PSU"],
    "mistakes": 2,
    "hints": 0,
    "wrong_placements": [],
    "completed": True,
    "duration_seconds": 200,
}


def board():
    return risk.assess(DATA)


def learner(report, sid):
    return next(row for row in report["learners"] if row["id"] == sid)


class Phrases(unittest.TestCase):
    def test_a_part_tried_twice_is_said_twice(self):
        self.assertIn("failed the RAM install step twice", risk.failure_phrases([("RAM", "CPU", 10), ("RAM", "CPU", 20)]))
        self.assertIn("placed the GPU before the CPU", risk.failure_phrases([("GPU", "CPU", 4)]))

    def test_the_repeated_step_lands_in_the_score_report(self):
        root = Path(tempfile.mkdtemp())
        (root / "essays").mkdir()
        (root / "attempts").mkdir()
        (root / "class.csv").write_text("id,name\nE01,Test Learner\n", encoding="utf-8")
        (root / "essays" / "E01.txt").write_text("Technology helps. " * 40, encoding="utf-8")
        (root / "rubric.json").write_text((DATA / "rubric.json").read_text(encoding="utf-8"), encoding="utf-8")
        (root / "practical_rubric.json").write_text((DATA / "practical_rubric.json").read_text(encoding="utf-8"), encoding="utf-8")
        (root / "attempts" / "E01.json").write_text(json.dumps(ATTEMPT), encoding="utf-8")
        row = risk.assess(root)["learners"][0]
        self.assertIn("failed the RAM install step twice", row["reason"] + " ".join(row["reasons"]))
        self.assertTrue(any("RAM" in (gap.get("quote") or "") or gap["outcome"] == "H3" for gap in row["gaps"]))


class SampleClass(unittest.TestCase):
    def test_at_least_three_sample_learners_are_high_risk(self):
        report = board()
        high = [row["id"] for row in report["learners"] if row["band"] == "High"]
        self.assertGreaterEqual(len(high), 3)
        self.assertTrue({"E06", "E08", "E10"} <= set(high))
        self.assertEqual(report["counts"]["High"], len(high))

    def test_the_class_is_sorted_with_scores_inside_the_scale(self):
        report = board()
        risks = [row["risk"] for row in report["learners"]]
        self.assertEqual(risks, sorted(risks, reverse=True))
        for row in report["learners"]:
            self.assertIn(row["band"], ("High", "Medium", "Low"))
            self.assertIn(row["result"], ("Pass", "Not yet"))
            self.assertTrue(0 <= row["risk"] <= 100)
            self.assertTrue(0 <= row["overall"] <= 100)
            self.assertTrue(any("pass line" in reason for reason in row["reasons"]))
            for area in row["areas"]:
                self.assertIn(area["label"], ("Strong", "Meeting", "Needs work"))

    def test_high_risk_reasons_name_the_pass_line_and_the_gap(self):
        report = board()
        kabelo, ruan, bongani = learner(report, "E06"), learner(report, "E08"), learner(report, "E10")
        self.assertIn("50% pass line", kabelo["reason"])
        self.assertIn("did not finish", kabelo["reason"])
        self.assertIn("pass line", ruan["reason"])
        self.assertIn("no PC assembly attempt", ruan["reason"])
        self.assertEqual(ruan["result"], "Not yet")
        self.assertIn("pass line", bongani["reason"])
        self.assertTrue("RAM" in bongani["reason"] or any("RAM" in reason for reason in bongani["reasons"]))
        self.assertGreater(kabelo["risk"], bongani["risk"])

    def test_the_score_report_has_evidence_tasks_and_a_moderation_note(self):
        row = learner(board(), "E06")
        self.assertTrue(row["strengths"])
        essay = (DATA / "essays" / "E06.txt").read_text(encoding="utf-8")
        attempt = json.loads((DATA / "attempts" / "E06.json").read_text(encoding="utf-8"))
        log = tools.render_attempt(tools.clean_attempt(attempt, tools.load_rubric(DATA, "practical")["parts"]), tools.load_rubric(DATA, "practical"))
        quoted = [item["quote"] for item in row["strengths"] + row["gaps"] if item.get("quote")]
        self.assertTrue(quoted)
        haystack = " ".join((essay + "\n" + log).split()).lower()
        for quote in quoted:
            self.assertIn(" ".join(quote.split()).lower(), haystack)
        self.assertTrue(all(gap["task"] and gap["outcome"] for gap in row["gaps"]))
        self.assertIn("Second-marked", row["moderation"])
        self.assertIn("1 mark", row["moderation"])
        self.assertIn("15%", row["moderation"])
        self.assertTrue(any(area["id"] == "pc" for area in row["areas"]))
        self.assertEqual([item["id"] for item in row["practical"]["outcomes"]], ["H1", "H2", "H3", "H4", "H5", "H6"])

    def test_weights_bands_and_the_windows_station_are_configurable(self):
        config = {**risk.RISK, "weights": {"theory": 1, "practical": 0}, "bands": {"high": 101, "medium": 100}}
        weighed = learner(risk.assess(DATA, config=config), "E01")
        plain = learner(board(), "E01")
        self.assertEqual(weighed["overall"], weighed["theory"]["percent"])
        self.assertNotEqual(weighed["overall"], plain["overall"])
        self.assertEqual(weighed["band"], "Low")  # nothing reaches a high band of 101

        with_windows = learner(risk.assess(DATA, windows={"E01": {"S1": 10, "S2": 10, "S3": 20, "S4": 0}}), "E01")
        self.assertGreater(with_windows["risk"], plain["risk"])
        self.assertLess(with_windows["overall"], plain["overall"])
        windows = next(area for area in with_windows["areas"] if area["id"] == "windows")
        self.assertEqual(windows["name"], "Windows")
        self.assertEqual(windows["label"], "Needs work")
        self.assertIn("S1", risk.RISK["stations"]["windows"]["outcomes"])

    def test_a_class_without_the_practical_still_scores(self):
        root = Path(tempfile.mkdtemp())
        (root / "essays").mkdir()
        (root / "class.csv").write_text("id,name\nL1,Ann Smith\n", encoding="utf-8")
        (root / "essays" / "L1.txt").write_text("Technology is useful for learners in rural schools. " * 20, encoding="utf-8")
        rubric = {"title": "Letter", "task": "Write.", "min_words": 20, "criteria": [
            {"id": "tone", "name": "Tone", "max": 10, "bands": []},
            {"id": "format", "name": "Format", "max": 10, "bands": []},
        ]}
        (root / "rubric.json").write_text(json.dumps(rubric), encoding="utf-8")
        row = risk.assess(root)["learners"][0]
        self.assertFalse(row["practical"]["in_class"])
        self.assertTrue(row["theory"]["marked"])
        self.assertIn(row["result"], ("Pass", "Not yet"))


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._output, cls._run = server.OUTPUT, server.current["run"]
        server.OUTPUT = Path(tempfile.mkdtemp())
        server.current["run"] = None
        cls.httpd = server.Server(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        server.OUTPUT = cls._output
        server.current["run"] = cls._run

    def test_risk_is_on_the_api_before_any_run(self):
        state = json.loads(urllib.request.urlopen(self.base + "/api/state", timeout=20).read())
        report = json.loads(urllib.request.urlopen(self.base + "/api/risk", timeout=20).read())
        self.assertGreaterEqual(state["risk"]["counts"]["High"], 3)
        self.assertEqual(report["learners"][0]["band"], "High")
        self.assertEqual(state["risk"]["learners"][0]["id"], report["learners"][0]["id"])
        json.dumps(state["risk"])


if __name__ == "__main__":
    unittest.main()
