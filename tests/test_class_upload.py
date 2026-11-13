"""A teacher's own class: uploaded, checked in code, kept apart from the sample, and marked.  Offline, on the mock."""
import hashlib
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
os.environ["MOCK"] = "1"

import run as server  # noqa: E402
from app import classes, tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the essays and send every learner feedback."
ESSAY = (DATA / "essays" / "E03.txt").read_bytes()  # a full, on-topic essay to reuse
CLASS = "﻿id;name;email;previous\nA1;Precious Mabena;precious@example.com;71\nA2;Johan van Wyk;;\n\nA3;Lindiwe Shabalala;;55%\n".encode("utf-8")


def fingerprint(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


class Checks(unittest.TestCase):
    def test_a_class_list_from_excel_is_read(self):
        rows, problems = classes.parse_class_list(CLASS)  # semicolons, a byte-order mark, a blank line, "55%"
        self.assertEqual(problems, [])
        self.assertEqual([(r["id"], r["name"], r["previous"]) for r in rows], [("A1", "Precious Mabena", "71"), ("A2", "Johan van Wyk", ""), ("A3", "Lindiwe Shabalala", "55%")])
        cp1252 = "id,name\nB1,Zoë Müller\n".encode("cp1252")
        self.assertEqual(classes.parse_class_list(cp1252)[0][0]["name"], "Zoë Müller")

    def test_a_class_list_that_would_mark_wrongly_is_refused(self):
        problems = lambda text: " | ".join(classes.parse_class_list(text.encode())[1])
        self.assertIn("no id column", problems("learner,name\nA1,Ann\n"))
        self.assertIn("row 3: the id A1 is used twice", problems("id,name\nA1,Ann\nA1,Bob\n"))
        self.assertIn("row 3: the id a1 is the same as A1 apart from capital letters", problems("id,name\nA1,Ann\na1,Bob\n"))
        self.assertIn("must be letters, digits", problems("id,name\n../evil,Ann\n"))
        self.assertIn("“about 60” is not a percentage", problems("id,name,previous\nA1,Ann,about 60\n"))
        self.assertIn("no learners", problems("id,name\n\n"))
        self.assertIn("empty", problems(""))

    def test_essays_are_matched_to_learners_by_id(self):
        rows = classes.parse_class_list(CLASS)[0]
        files = [("A1.txt", b"first"), ("a2_Johan.TXT", b"second"), ("A1 copy.txt", b"again"), ("Z9.txt", b"?"), ("A3.docx", b"word")]
        matched, unmatched = classes.match_essays(files, rows)
        self.assertEqual(matched, {"A1": "first", "A2": "second"})
        self.assertEqual(unmatched, ["A1 copy.txt (a second essay for A1; the first one is used)", "Z9.txt (no learner on the class list has this id)",
                                     "A3.docx (only .txt essays can be read)"])

    def test_a_broken_rubric_is_refused(self):
        self.assertEqual(classes.check_rubric((DATA / "rubric.json").read_bytes()), [])
        self.assertIn("rubric.json is not valid JSON", classes.check_rubric(b"{nope")[0])
        bad = {"title": "T", "task": "", "criteria": [{"id": "c", "max": 0, "bands": []}, {"id": "c", "max": 5, "bands": [{"range": [0, 5], "text": "ok"}]}]}
        self.assertEqual(classes.check_rubric(json.dumps(bad).encode()), [
            "rubric.json has no task", "criterion c needs a whole-number max above 0",
            "criterion c needs bands, each with a range [low, high] and a text", "criterion 2 needs an id of its own"])

    def test_a_class_is_kept_in_its_own_folder_and_the_sample_is_untouched(self):
        before = fingerprint(DATA)
        root = tempfile.mkdtemp()
        cid, summary = classes.create_class(root, DATA, CLASS, [("A1.txt", ESSAY), ("A3_Lindiwe.txt", ESSAY), ("notes.txt", b"x")])
        folder = classes.class_folder(root, cid)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["class.csv", "essays", "outcomes.json", "practical_rubric.json", "rubric.json", "upload.json"])
        self.assertEqual((summary["learners"], summary["essays"], summary["missing"]), (3, 2, ["A2"]))
        self.assertEqual(summary["unmatched"], ["notes.txt (no learner on the class list has this id)"])
        self.assertEqual([(p["id"], p["flags"]) for p in summary["preview"]], [("A1", []), ("A2", ["missing", "too_short"]), ("A3", [])])
        self.assertEqual(tools.load_submissions(folder)[2]["previous"], 55.0)
        self.assertEqual(fingerprint(DATA), before)
        with self.assertRaises(classes.ClassError) as e:
            classes.create_class(root, DATA, b"id,name\nA1,Ann\nA1,Bob\n", [])
        self.assertEqual(e.exception.problems, ["row 3: the id A1 is used twice"])
        for bad in ("../" + cid, "", "zzz"):
            with self.assertRaises(classes.ClassError):
                classes.class_folder(root, bad)

    def test_the_whole_team_works_on_the_teachers_class(self):
        root = tempfile.mkdtemp()
        cid, _ = classes.create_class(root, DATA, CLASS, [("A1.txt", ESSAY), ("A3.txt", ESSAY)])
        r = Run(Mock(), GOAL + " Then tell me who is falling behind, with a catch-up plan for each of them.",
                str(classes.class_folder(root, cid)), tempfile.mkdtemp())
        r._guarded()
        by = {s["id"]: s for s in r.subs}
        self.assertEqual((r.status, list(by)), ("done", ["A1", "A2", "A3"]))
        self.assertEqual((by["A1"]["status"], by["A2"]["status"]), ("delivered", "resubmit"))
        self.assertIn("Hi Precious", by["A1"]["feedback"]["body"])
        self.assertIn("A2", [e["id"] for e in r.support["learners"]])  # nothing handed in: flagged, with a plan
        self.assertTrue((r.out_dir / "outbox" / "A1_Precious_Mabena.txt").exists())

    def test_a_class_with_its_own_rubric_is_marked_against_it(self):
        rubric = {"title": "Letter rubric (20)", "task": "Write a formal letter.", "min_words": 30, "criteria": [
            {"id": "tone", "name": "Tone", "max": 10, "bands": [{"range": [0, 5], "text": "Casual."}, {"range": [6, 10], "text": "Formal."}]},
            {"id": "format", "name": "Format", "max": 10, "bands": [{"range": [0, 5], "text": "Missing parts."}, {"range": [6, 10], "text": "Complete."}]}]}
        root = tempfile.mkdtemp()
        cid, summary = classes.create_class(root, DATA, b"id,name\nL1,Ann Smith\n", [("L1.txt", ESSAY)], json.dumps(rubric).encode())
        self.assertEqual((summary["rubric"], summary["own_rubric"]), ("Letter rubric (20)", True))
        r = Run(Mock(), GOAL, str(classes.class_folder(root, cid)), tempfile.mkdtemp())
        r._guarded()
        self.assertEqual((r.status, r.rubric["total"], set(r._sub("L1")["final"]["scores"])), ("done", 20, {"tone", "format"}))
        self.assertEqual([o["id"] for o in r.outcomes], ["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"])  # the sample's outcomes, filtered to this rubric
        self.assertTrue(all(o["criteria"] == [] for o in r.outcomes))


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

    def send(self, path, body, ctype="application/json"):
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def upload(self, files):
        body = b"".join(b"--XX\r\n" + f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n\r\n'.encode() + data + b"\r\n"
                        for field, name, data in files) + b"--XX--\r\n"
        return self.send("/api/class", body, "multipart/form-data; boundary=XX")

    def state(self):
        return json.loads(urllib.request.urlopen(self.base + "/api/state", timeout=20).read())

    def test_upload_check_and_mark_a_class(self):
        code, out = self.upload([("class_list", "c.csv", b"id,name\nA1,Ann\nA1,Bob\n")])
        self.assertEqual((code, out["problems"]), (400, ["row 3: the id A1 is used twice"]))
        self.assertEqual(self.upload([("essays", "A1.txt", ESSAY)])[0], 400)  # no class list
        code, out = self.upload([("class_list", "class.csv", CLASS), ("essays", "A1.txt", ESSAY), ("essays", "A3.txt", ESSAY)])
        self.assertEqual((code, out["learners"], out["essays"], out["missing"]), (200, 3, 2, ["A2"]))

        self.assertEqual(self.send("/api/run", {"goal": GOAL, "class": "nope"})[0], 400)
        self.assertEqual(self.send("/api/run", {"goal": GOAL, "class": out["class"], "assessment": "practical"})[0], 400)
        self.assertEqual(self.send("/api/run", {"goal": GOAL, "class": out["class"]}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.state()["status"] == "done", 30))
        done = self.state()
        self.assertEqual([s["id"] for s in done["subs"]], ["A1", "A2", "A3"])
        self.assertEqual(done["stats"]["delivered"], 2)
        # the next run without a class is the sample class again
        self.assertEqual(self.send("/api/run", {"goal": GOAL}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.state()["status"] == "done", 30))
        self.assertEqual(len(self.state()["subs"]), 12)


if __name__ == "__main__":
    unittest.main()
