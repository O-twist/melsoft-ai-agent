"""The live virtual lab: PC assembly attempts recorded in the dashboard, checked, kept and marked.

Run:  python -m unittest discover tests      The assembly rules themselves are tested in web/ (npm test).
"""
import json
import os
import shutil
import subprocess
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
from app import tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web"
GOAL = "Mark the PC assembly practical against the rubric and send every learner personalised feedback."

# An attempt as the virtual lab writes it: the GPU tried before the CPU, then the CPU dropped off its slot once.
LIVE = {"learner_id": "E05", "order_tried": ["motherboard", "GPU", "CPU", "RAM", "GPU", "SSD", "PSU"], "mistakes": 2, "hints": 1,
        "wrong_placements": [{"part": "GPU", "expected": "CPU", "t": 33}], "completed": True, "duration_seconds": 198}


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


class Checks(unittest.TestCase):
    def setUp(self):
        self.rubric = tools.load_rubric(DATA, "practical")
        self.subs = tools.load_submissions(DATA)

    def problems(self, **change):
        return " | ".join(tools.check_attempt({**LIVE, **change}, self.subs, self.rubric)[1])

    def test_an_attempt_that_replays_is_kept(self):
        attempt, problems = tools.check_attempt(LIVE, self.subs, self.rubric)
        self.assertEqual(problems, [])
        facts = tools.attempt_facts(attempt, self.rubric["parts"])
        self.assertEqual((facts["wrong"], facts["slot_misses"], facts["completed"]), (1, 1, True))

    def test_an_attempt_that_does_not_replay_is_refused(self):
        self.assertIn("learner E99 is not on the class list", self.problems(learner_id="E99"))
        self.assertIn("parts that are not in the practical: Floppy drive", self.problems(order_tried=LIVE["order_tried"] + ["Floppy drive"]))
        self.assertIn("do not match the order of placements, which shows 1", self.problems(wrong_placements=[]))
        self.assertIn("counts 0 mistakes but lists 1 wrong placements", self.problems(mistakes=0))
        self.assertIn("says it was finished, but only 3 of 6 parts went in",
                      self.problems(order_tried=["motherboard", "GPU", "CPU", "RAM"]))
        self.assertIn("time taken is missing or impossible", self.problems(duration_seconds=0))
        self.assertEqual(tools.check_attempt(["not", "a", "dict"], self.subs, self.rubric), (None, ["the attempt is not a JSON object"]))

    def test_a_live_attempt_takes_the_place_of_the_sample_file(self):
        live = Path(tempfile.mkdtemp())
        (live / "E05.json").write_text(json.dumps(LIVE), encoding="utf-8")
        subs = tools.load_attempts(DATA, tools.load_submissions(DATA), self.rubric, live)
        by = {s["id"]: s for s in subs}
        self.assertEqual((by["E05"]["source"], by["E01"]["source"], by["E08"]["source"]), ("live", "practical", None))
        self.assertIn("2. Wrong: placed the GPU before the CPU at 0:33.", by["E05"]["text"])
        self.assertIn("1 dropped outside its slot", by["E05"]["text"])

    def test_a_run_marks_the_live_attempt(self):
        live = Path(tempfile.mkdtemp())
        (live / "E05.json").write_text(json.dumps(LIVE), encoding="utf-8")
        r = Run(Mock(), GOAL, DATA, tempfile.mkdtemp(), assessment="practical", live_attempts=live)
        r._guarded()
        s = r._sub("E05")
        self.assertEqual((r.status, s["status"], s["source"]), ("done", "delivered", "live"))
        self.assertIn("Recorded live in the lab today: E05.", r.events[0]["msg"])
        self.assertLessEqual(s["final"]["scores"]["order"]["score"], 12)  # one wrong placement: at most 15 - 3
        self.assertLess(s["final"]["total"], 40)  # Naledi's sample file is a perfect build; this attempt is not


@unittest.skipUnless(shutil.which("node"), "Node is needed to run the dashboard's assembly rules")
class SameSchemaBothSides(unittest.TestCase):
    def test_what_the_virtual_lab_writes_is_what_the_server_accepts(self):
        script = (
            "import { newAttempt, tryPart, takeHint, toRecord } from './src/assembly.js';"
            "let a = newAttempt('E07', 0); let w;"
            "for (const [p, ok, t] of [['motherboard', true, 5], ['RAM', true, 20], ['CPU', false, 26], ['CPU', true, 30],"
            " ['RAM', true, 40], ['GPU', true, 60], ['PSU', true, 70], ['SSD', true, 80], ['PSU', true, 95]]) {"
            " if (t === 60) a = takeHint(a); [a, w] = tryPart(a, p, ok, t * 1000); }"
            "console.log(JSON.stringify(toRecord(a, 100000)));"
        )
        out = subprocess.run(["node", "--input-type=module", "-e", script], cwd=WEB, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        record = json.loads(out.stdout)
        self.assertEqual(sorted(record), sorted(LIVE))  # exactly the Phase 2 schema
        rubric = tools.load_rubric(DATA, "practical")
        attempt, problems = tools.check_attempt(record, tools.load_submissions(DATA), rubric)
        self.assertEqual(problems, [])
        facts = tools.attempt_facts(attempt, rubric["parts"])
        self.assertEqual((facts["wrong"], facts["slot_misses"], facts["hints"], facts["completed"], facts["seconds"]), (2, 1, 1, True, 100))


class Assets(unittest.TestCase):
    def test_the_lab_pictures_and_the_3d_model_are_local_and_credited(self):
        for name in ("case-open", "motherboard", "cpu", "ram", "gpu", "ssd", "psu"):
            self.assertTrue((WEB / "public" / "pc-assembly" / f"{name}.png").read_bytes().startswith(b"\x89PNG"), name)
        glb = (WEB / "public" / "models" / "personal_computer.glb").read_bytes()
        self.assertEqual(glb[:4], b"glTF")
        length = int.from_bytes(glb[12:16], "little")
        extras = json.loads(glb[20:20 + length])["asset"]["extras"]
        self.assertIn("CC-BY-4.0", extras["license"])
        credits = (WEB / "public" / "models" / "CREDITS.md").read_text(encoding="utf-8")
        self.assertIn("alessiaspedicati", credits)
        self.assertIn("CC BY 4.0", credits)
        viewer = (WEB / "src" / "components" / "ModelViewer.jsx").read_text(encoding="utf-8")
        self.assertIn("/models/personal_computer.glb", viewer)  # a local file, not a download
        self.assertIn("alessiaspedicati", viewer)  # the credit is shown with the model
        self.assertNotIn("https://raw.githubusercontent.com", viewer)


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

    def request(self, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                out = r.read()
                return r.status, (r.headers, out) if raw else json.loads(out)
        except urllib.error.HTTPError as e:
            out = e.read()
            return e.code, (e.headers, out) if raw else json.loads(out)

    def test_an_attempt_from_the_lab_is_kept_then_marked(self):
        self.assertEqual(self.request("/api/attempts"), (200, {"attempts": []}))
        code, out = self.request("/api/attempt", {**LIVE, "mistakes": 0})
        self.assertEqual(code, 400)
        self.assertIn("The attempt was not kept", out["error"])
        self.assertFalse((server.OUTPUT / "attempts").exists())  # nothing was kept from a bad attempt
        code, out = self.request("/api/attempt", LIVE)
        self.assertEqual((code, out["ok"]), (200, True))
        self.assertIn("Wrong: placed the GPU before the CPU", out["log"])  # what the Marker will read
        self.assertTrue((server.OUTPUT / "attempts" / "E05.json").exists())
        self.assertEqual([a["learner_id"] for a in self.request("/api/attempts")[1]["attempts"]], ["E05"])
        with mock.patch.dict(os.environ, {"PRACTICAL_LAB": "0"}):
            self.assertEqual(self.request("/api/attempt", LIVE)[0], 400)

        self.assertEqual(self.request("/api/run", {"goal": GOAL, "assessment": "practical"}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.request("/api/state?since=999999")[1]["status"] == "done", 30))
        done = self.request("/api/state")[1]
        e05 = next(s for s in done["subs"] if s["id"] == "E05")
        self.assertEqual((e05["source"], e05["status"]), ("live", "delivered"))
        self.assertIn("Recorded live in the lab today: E05.", done["events"][0]["msg"])
        # an essay run is not affected by what was recorded in the lab
        self.assertEqual(self.request("/api/run", {"goal": "Mark the essays."}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.request("/api/state?since=999999")[1]["status"] == "done", 30))
        self.assertEqual(next(s for s in self.request("/api/state")[1]["subs"] if s["id"] == "E05")["source"], "typed")

    def test_the_3d_model_is_served_from_the_built_dashboard(self):
        code, out = self.request("/models/personal_computer.glb", raw=True)
        if code == 503:
            self.skipTest("the dashboard has not been built")
        headers, body = out
        self.assertEqual((code, headers["Content-Type"], body[:4]), (200, "model/gltf-binary", b"glTF"))
        self.assertEqual(self.request("/pc-assembly/case-open.png", raw=True)[0], 200)


if __name__ == "__main__":
    unittest.main()
