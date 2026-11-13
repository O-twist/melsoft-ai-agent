"""What each agent is allowed to see. Run:  python -m unittest discover tests

The checks between agents only mean something if the agents are kept apart:
the Reviewer marks without the Marker's mark, the Marker and the Reviewer never see
who wrote the work, the Designer never sees a learner's name, and the Messenger is
only ever handed marks that are settled. These tests read everything each agent was sent.
"""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

from app import tools  # noqa: E402
from app.llm import Mock  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
THEORY = ("Mark the Grade 12 CAT theory papers against the rubric and send every learner personalised feedback. "
          "Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the "
          "class's weakest area with exercises.")
PRACTICAL = THEORY.replace("Grade 12 CAT theory papers", "PC assembly practical")
DESIGNER_TASKS = ("lesson", "fix_exercises", "align_lesson")


class Recorder(Mock):
    """The offline marker, keeping everything each agent was sent: the instructions, the prompt and the data."""

    def __init__(self, **changes):
        super().__init__()
        self.changes, self.sent = changes, []

    def call(self, task, system, prompt, data=None, log=None):
        self.sent.append({"task": task, "system": system, "prompt": prompt, "data": json.dumps(data, sort_keys=True)})
        reply = super().call(task, system, prompt, data, log)
        change = self.changes.get(task)
        return change(reply) if change else reply

    def to(self, *tasks):
        return [s for s in self.sent if s["task"] in tasks]


def run(goal, llm, assessment="essay", **kw):
    r = Run(llm, goal, DATA, tempfile.mkdtemp(), assessment=assessment, **kw)
    r._guarded()
    return r


def names():
    """Every first name and surname on the class list."""
    return sorted({part for sub in tools.load_submissions(DATA) for part in sub["learner"].split()})


def named(text):
    return [name for name in names() if re.search(rf"\b{re.escape(name)}\b", text, re.I)]


def harsher(reply):
    """A Marker who is far off on every script, so every mark is disputed."""
    for mark in reply["marks"]:
        first = next(iter(mark["scores"].values()))
        first["score"] = 0
    return reply


class ReviewerIsBlind(unittest.TestCase):
    def blind_input(self, assessment, **changes):
        llm = Recorder(**changes)
        r = run(THEORY if assessment == "essay" else PRACTICAL, llm, assessment)
        self.assertEqual(r.status, "done")
        return r, [(s["system"], s["prompt"], s["data"]) for s in llm.to("review")]

    def test_the_second_mark_is_asked_for_without_the_first(self):
        for assessment in ("essay", "practical"):
            with self.subTest(assessment=assessment):
                _, plain = self.blind_input(assessment)
                r, disputed = self.blind_input(assessment, mark=harsher)
                self.assertTrue(plain)
                # Whatever the Marker said, the Reviewer was sent exactly the same thing, word for word.
                self.assertEqual(plain, disputed)
                self.assertGreater(r.stats["sent_back"], 0)  # and the difference was still caught

    def test_the_reviewer_is_sent_only_the_work_and_the_rubric(self):
        for assessment in ("essay", "practical"):
            with self.subTest(assessment=assessment):
                llm = Recorder()
                run(THEORY if assessment == "essay" else PRACTICAL, llm, assessment, inject_fault=True)
                for sent in llm.to("review"):
                    data = json.loads(sent["data"])
                    self.assertEqual(set(data), {"rubric", "essays"})
                    for essay in data["essays"]:
                        self.assertEqual(set(essay), {"id", "text"})
                    self.assertIn("You have not seen any other marker's marks", sent["system"])
                    self.assertNotIn("Your mark", sent["prompt"])
                    self.assertNotIn("Marker's mark", sent["prompt"])

    def test_marking_is_anonymous(self):
        for assessment in ("essay", "practical"):
            with self.subTest(assessment=assessment):
                llm = Recorder()
                r = run(THEORY if assessment == "essay" else PRACTICAL, llm, assessment)
                written = " ".join(s["text"] for s in r.subs)  # a learner may name themselves in their own work
                for sent in llm.to("mark", "review", "remark", "verify"):
                    leaked = [n for n in named(sent["prompt"] + sent["data"]) if not re.search(rf"\b{n}\b", written, re.I)]
                    self.assertEqual(leaked, [], sent["task"])


class DesignerSeesNoNames(unittest.TestCase):
    def test_nothing_sent_to_the_designer_names_a_learner(self):
        for assessment in ("essay", "practical"):
            for fault in (False, True):  # a planted fault sends an exercise back, so the Designer is asked twice more
                with self.subTest(assessment=assessment, fault=fault):
                    llm = Recorder()
                    r = run(THEORY if assessment == "essay" else PRACTICAL, llm, assessment, inject_fault=fault)
                    self.assertEqual(r.status, "done")
                    asked = llm.to(*DESIGNER_TASKS)
                    self.assertIn("lesson", {s["task"] for s in asked})
                    self.assertIn("align_lesson", {s["task"] for s in asked})  # the Coach's diagnoses reach the Designer too
                    if fault:
                        self.assertIn("fix_exercises", {s["task"] for s in asked})
                    for sent in asked:
                        self.assertEqual(named(sent["prompt"]), [], sent["task"])
                        self.assertEqual(named(sent["data"]), [], sent["task"])
                        self.assertNotIn("@", sent["prompt"] + sent["data"])  # nor an email address

    def test_the_brief_is_class_figures_only(self):
        llm = Recorder()
        run(THEORY, llm)
        brief = json.loads(llm.to("lesson")[0]["data"])["brief"]
        self.assertEqual(set(brief), {"minutes", "weakest", "criteria_avg", "marked", "flagged", "causes"})
        self.assertNotRegex(json.dumps(brief), r"\bE\d\d\b")  # not even a learner's id


class MessengerSendsOnlySettledMarks(unittest.TestCase):
    def test_a_mark_still_in_dispute_never_reaches_the_messenger(self):
        def defended(reply):  # the Marker stands by a mark the Reviewer cannot accept
            for mark in reply["marks"]:
                mark["response"] = "defended"
            return reply

        def harsh_on_e01(reply):
            for mark in reply["marks"]:
                if mark["id"] == "E01":
                    mark["scores"]["content"]["score"] -= 12
            return reply

        def keep(reply):  # on the re-mark the Marker gives the same harsh mark again
            return defended(harsh_on_e01(reply))

        def rejected(reply):
            for verdict in reply["verdicts"]:
                verdict["approve"] = False
            return reply

        llm = Recorder(mark=harsh_on_e01, remark=keep, verify=rejected)
        r = run(THEORY, llm)
        held = next(s for s in r.subs if s["id"] == "E01")
        self.assertEqual(held["status"], "escalated")
        self.assertIsNone(held["feedback"])
        for sent in llm.to("feedback"):
            ids = {item["id"] for item in json.loads(sent["data"])["items"]}
            self.assertNotIn("E01", ids)
        self.assertFalse(list((r.out_dir / "outbox").glob("E01*")))
        settled = {s["id"] for s in r.subs if s["status"] == "delivered"}
        for sent in llm.to("feedback"):
            for item in json.loads(sent["data"])["items"]:
                self.assertIn(item["id"], settled)
                final = next(s for s in r.subs if s["id"] == item["id"])["final"]
                self.assertEqual(item["total"], final["total"])  # the mark sent is the mark both markers settled on


if __name__ == "__main__":
    unittest.main()
