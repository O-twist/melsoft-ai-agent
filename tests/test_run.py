"""Offline end-to-end checks.  Run:  python -m unittest discover tests

Nothing here needs the internet: the workflow runs on the mock LLM, and the Gemini and OpenRouter
clients are exercised against small stand-in servers that speak the same JSON.
"""
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

os.environ["MOCK_DELAY"] = "0"
os.environ["MOCK"] = "1"  # never spend a real API key on tests

import run as server  # noqa: E402
from app import agents, tools  # noqa: E402
from app.llm import Busy, Fallback, Gemini, LLMError, Mock, OpenRouter, make_llm, parse_json  # noqa: E402
from app.orchestrator import Run  # noqa: E402

DATA = Path(__file__).parent.parent / "data"
GOAL = "Mark the essays and send every learner feedback."
SUPPORT_GOAL = GOAL + " Then tell me who is falling behind, with a catch-up plan for each of them."
LESSON_GOAL = GOAL + " Then draft a 30-minute lesson on the class's weakest area, with exercises."
WHOLE_JOB = (
    "Mark the Grade 10 essays against the rubric and send every learner personalised feedback. "
    "Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson "
    "on the class's weakest area with exercises."
)


class Scripted(Mock):
    """The mock, with chosen replies altered so that awkward model behaviour can be rehearsed."""

    def __init__(self, **changes):
        super().__init__()
        self.changes, self.seen, self.prompts = changes, [], {}

    def call(self, task, system, prompt, data=None, log=None):
        self.seen.append(task)
        self.prompts.setdefault(task, []).append(prompt)
        reply = super().call(task, system, prompt, data, log)
        change = self.changes.get(task)
        return change(reply, self.seen.count(task)) if change else reply


def run(goal=GOAL, llm=None, data=DATA, **kw):
    r = Run(llm or Mock(), goal, data, tempfile.mkdtemp(), **kw)
    r._guarded()
    return r


def wait_for(condition, seconds=5):
    for _ in range(int(seconds * 20)):
        if condition():
            return True
        time.sleep(0.05)
    return False


def without(essay_id):
    return lambda reply, nth: {"marks": [m for m in reply["marks"] if m["id"] != essay_id]}


def lower_content(essay_id, by):
    """Make one essay's content mark differ, as if this marker judged it much more harshly."""
    def change(reply, nth):
        for m in reply["marks"]:
            if m["id"] == essay_id:
                m["scores"]["content"]["score"] -= by
        return reply
    return change


class Tools(unittest.TestCase):
    def test_quote_must_exist(self):
        text = "Technology is a tool, and it depends\non the person holding it. I dont think so."
        self.assertTrue(tools.quote_in_text('"it depends on the person"', text))
        self.assertTrue(tools.quote_in_text("Technology is a tool ... person holding it", text))
        self.assertTrue(tools.quote_in_text("Technology is a tool and it depends", text))  # a tidied comma is not an invention
        self.assertTrue(tools.quote_in_text("I don't think so", text))
        self.assertFalse(tools.quote_in_text("technology changed my whole life", text))
        self.assertFalse(tools.quote_in_text("a tool", text))  # too short to prove anything
        self.assertFalse(tools.quote_in_text("", text))
        self.assertFalse(tools.quote_in_text(None, text))

    def test_clean_mark_recomputes_total_and_flags_problems(self):
        rubric = tools.load_rubric(DATA)
        raw = {"scores": {"content": {"score": 99, "evidence": "made up words here", "reason": ""},
                          "language": {"score": "10", "evidence": "the essay text itself", "reason": ""}}}
        mark, problems = tools.clean_mark(raw, rubric, "This is the essay text itself, nothing more.")
        self.assertEqual(mark["total"], 30 + 10 + 0)
        self.assertEqual(len(problems), 3)  # out of range, fake quote, missing criterion

    def test_clean_mark_survives_nonsense(self):
        rubric = tools.load_rubric(DATA)
        for raw in (None, [], "42", {"scores": []}, {"scores": {"content": "high"}},
                    {"scores": {"content": {"score": float("inf"), "evidence": "x"}}}):
            mark, problems = tools.clean_mark(raw, rubric, "Some essay text.")
            self.assertEqual(mark["total"], 0)
            self.assertTrue(problems)

    def test_feedback_must_state_the_exact_mark(self):
        rubric = tools.load_rubric(DATA)
        subs = tools.load_submissions(DATA)
        sub = subs[0]
        sub["final"] = {"total": 4}
        first = sub["learner"].split()[0]
        filler = " ".join(["word"] * 60)
        ok = {"body": f"Hi {first}, you scored 4 / 50. {filler}"}
        self.assertEqual(tools.check_feedback(ok, sub, subs, rubric), [])
        wrong = {"body": f"Hi {first}, you scored 34/50. {filler}"}
        self.assertIn("does not state the final mark 4/50", tools.check_feedback(wrong, sub, subs, rubric))
        other = subs[1]["learner"].split()[0]
        leak = {"body": f"Hi {first}, you scored 4/50, better than {other}. {filler}"}
        self.assertIn(f"mentions another learner ({other})", tools.check_feedback(leak, sub, subs, rubric))
        self.assertTrue(tools.check_feedback(None, sub, subs, rubric))
        self.assertTrue(tools.check_feedback({"body": ["not", "text"]}, sub, subs, rubric))

    def test_warning_signs_follow_fixed_rules(self):
        rubric = tools.load_rubric(DATA)

        def kinds(scores, previous=None, status="agreed", words=200):
            final = scores and {"scores": {k: {"score": v} for k, v in zip(("content", "language", "structure"), scores)}, "total": sum(scores)}
            sub = {"final": final, "previous": previous, "status": status, "words": words}
            return [sign["kind"] for sign in tools.support_signs(sub, rubric)]

        self.assertEqual(kinds((24, 12, 4)), [])  # 80%, and nothing on record to compare it with
        self.assertEqual(kinds((24, 12, 4), previous=94), [])  # 14 points down: inside the allowance
        self.assertEqual(kinds((24, 12, 4), previous=95), ["dropped"])
        self.assertEqual(kinds((12, 9, 3)), ["below"])  # 48%
        self.assertEqual(kinds((20, 5, 4)), ["weak_area"])  # 58% overall, but language at 33%
        self.assertEqual(kinds((6, 5, 4), previous=70), ["below", "dropped", "weak_area", "weak_area"])
        self.assertEqual(kinds(None, status="resubmit", words=0), ["missing"])
        self.assertEqual(kinds(None, status="escalated"), [])  # no settled mark yet, so nothing to judge

    def test_catch_up_plan_must_fit_the_learner(self):
        rubric = tools.load_rubric(DATA)
        outcomes = tools.load_outcomes(DATA, rubric)
        subs = tools.load_submissions(DATA)
        sub = subs[1]
        sub["final"] = {"scores": {"content": {"score": 20}, "language": {"score": 4}, "structure": {"score": 4}}, "total": 28}
        step = lambda outcome, minutes=15: {"outcome": outcome, "activity": "Read the essay aloud and correct every slip.", "minutes": minutes}
        good = {"why": "Basic language slips are pulling the mark down.", "evidence": "we use phones every day",
                "strength": "", "check": "", "steps": [step("W6"), step("W8"), step("W1")]}
        problems = lambda **change: " | ".join(tools.check_support_plan({**good, **change}, sub, subs, rubric, outcomes))
        self.assertEqual(problems(), "")
        self.assertIn("has 2 steps", problems(steps=good["steps"][:2]))
        self.assertIn("not on the list (W99)", problems(steps=[step("W6"), step("W99"), step("W1")]))
        self.assertIn("weakest area (Language", problems(steps=[step("W1"), step("W2"), step("W4")]))
        self.assertIn("takes 90 minutes", problems(steps=[step("W6", 90), step("W8"), step("W1")]))
        self.assertIn("does not appear in the learner's essay", problems(evidence="technology changed my whole life"))
        self.assertIn("does not explain why", problems(why="Needs work."))
        other = subs[0]["learner"].split()[0]
        self.assertIn(f"mentions another learner ({other})", problems(check=f"Pair up with {other}."))
        for nonsense in (None, "a plan", {"steps": "three"}, {"steps": [None, {"minutes": "soon"}]}):
            self.assertTrue(tools.check_support_plan(tools.clean_support_plan(nonsense), sub, subs, rubric, outcomes))

    def test_lesson_must_add_up_and_cover_what_it_claims(self):
        rubric = tools.load_rubric(DATA)
        outcomes = tools.load_outcomes(DATA, rubric)
        weakest = {"id": "content", "name": "Content and planning", "pct": 60}
        ex = lambda n, outcome, level: {"id": f"X{n}", "outcome": outcome, "level": level, "answer": "One clear idea.",
                                        "task": "Rewrite this paragraph so that it has one clear main idea."}
        raw = {"title": "Paragraphs", "outcomes": ["W2", "W5"],
               "phases": [{"name": "Start", "minutes": 10}, {"name": "Practise", "minutes": 25}, {"name": "Close", "minutes": 10}],
               "exercises": [ex(1, "W2", "support"), ex(2, "W2", "core"), ex(3, "W5", "core"), ex(4, "W5", "extension")]}
        check = lambda **change: tools.check_lesson(tools.clean_lesson({**raw, **change}, 45), outcomes, weakest, 45)
        self.assertEqual(check(), ([], {}))
        self.assertIn("has phases that add up to 35 minutes, not 45", check(phases=raw["phases"][:2])[0])
        self.assertIn("does not target the class's weakest area (Content and planning)", check(outcomes=["W5"])[0])
        self.assertIn("names outcomes that are not on the list (W99)", check(outcomes=["W2", "W5", "W99"])[0])
        self.assertIn("has no exercise for outcome W5", check(exercises=raw["exercises"][:2] + [ex(3, "W2", "core")])[0])
        self.assertIn("has no support exercise for learners who are behind", check(exercises=raw["exercises"][1:] + [ex(5, "W2", "core")])[0])
        self.assertEqual(check(exercises=raw["exercises"][:3] + [{**ex(4, "W6", "hard"), "answer": ""}])[1], {"X4": [
            "it is labelled W6, which is not one of the lesson's outcomes", "it has no level (support, core or extension)", "it has no model answer"]})
        lesson = tools.clean_lesson(raw, 45)
        lesson["exercises"][3]["status"] = "dropped"  # a lesson can lose an exercise and still stand
        self.assertEqual(tools.check_lesson(lesson, outcomes, weakest, 45), ([], {}))
        lesson["exercises"][0]["status"] = "dropped"  # but not the only one for learners who are behind
        self.assertTrue(tools.check_lesson(lesson, outcomes, weakest, 45)[0])
        self.assertTrue(tools.check_lesson(tools.clean_lesson("no lesson", 45), outcomes, weakest, 45)[0])

    def test_exercise_label_is_held_against_a_blind_attempt(self):
        outcomes = tools.load_outcomes(DATA, tools.load_rubric(DATA))
        exercise = tools.clean_exercise({"outcome": "W2", "level": "core", "task": "Rewrite the paragraph.", "answer": "x"}, "X1")
        problems = lambda attempt: " | ".join(tools.blind_check(exercise, attempt, outcomes)[1])
        self.assertEqual(problems({"outcome": "W2", "answer": "Done.", "problem": "None."}), "")
        self.assertIn("judged that it practises W6", problems({"outcome": "W6"}))
        self.assertIn("could not match it to an outcome on the list (grammar)", problems({"outcome": "grammar"}))
        self.assertIn("could not do it as written: There is no paragraph.", problems({"outcome": "W2", "problem": "There is no paragraph."}))
        self.assertIn("returned no attempt", problems(None))

    def test_outcomes_fall_back_to_the_rubric(self):
        rubric = tools.load_rubric(DATA)
        self.assertEqual([o["id"] for o in tools.load_outcomes(DATA, rubric)], [f"W{n}" for n in range(1, 9)])
        fallback = tools.load_outcomes(tempfile.mkdtemp(), rubric)  # a class with no outcomes.json
        self.assertEqual([(o["id"], o["criteria"]) for o in fallback], [(c["id"], [c["id"]]) for c in rubric["criteria"]])

    def test_parse_json_tolerates_fences(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(parse_json('Here you go: {"a": 1} done'), {"a": 1})

    def test_replies_are_read_whatever_their_wrapper(self):
        row = {"id": "E01", "scores": {}}
        for reply in ({"marks": [row]}, [row], {"results": [row]}, {"marks": {"E01": {"scores": {}}}}, row):
            self.assertEqual(list(agents._rows(reply, "marks")), ["E01"], reply)
        for reply in (None, "sorry", 7, {"marks": "none"}, {"marks": [None, "x", {"scores": {}}]}):
            self.assertEqual(agents._rows(reply, "marks"), {}, reply)
        self.assertEqual(agents._obj([{"a": 1}]), {"a": 1})
        self.assertEqual(agents._obj("nope"), {})

    def test_consistency_catches_a_gap_and_an_unmapped_step(self):
        rubric = tools.load_rubric(DATA)
        outcomes = tools.load_outcomes(DATA, rubric)
        task = "Rewrite this paragraph so that it has one clear main idea."
        lesson = tools.clean_lesson({
            "title": "Plans", "outcomes": ["W1", "W2"],
            "phases": [{"minutes": 15}, {"minutes": 15}, {"minutes": 15}],
            "exercises": [
                {"id": "X1", "outcome": "W1", "level": "support", "task": task, "answer": "One idea."},
                {"id": "X2", "outcome": "W1", "level": "core", "task": task, "answer": "One idea."},
                {"id": "X3", "outcome": "W2", "level": "core", "task": task, "answer": "One idea."},
                {"id": "X4", "outcome": "W6", "level": "core", "task": task, "answer": "Corrected."},
            ],
        }, 45)
        for exercise in lesson["exercises"]:
            exercise["status"] = "ok"
        learners = [{
            "id": "E02", "status": "ready", "weakest": {"id": "language"},
            "signs": [{"kind": "weak_area", "criterion": "language"}],
            "plan": {"steps": [{"outcome": "W6"}, {"outcome": "NOPE"}, {"outcome": "W1"}]},
        }]
        report = tools.consistency_issues(learners, lesson, outcomes, rubric)
        self.assertTrue(any("Language" in problem and "E02" in problem for problem in report["lesson"]))
        self.assertIn("NOPE", report["plans"]["E02"][0])
        # W6 is practised, but only by a core exercise, so the step maps and the support work still does not
        self.assertEqual([step["where"] for step in report["steps"]], ["exercise", "none", "lesson"])
        self.assertIsNone(next(item["exercise"] for item in report["coverage"] if item["id"] == "language"))
        lesson["exercises"].append({**lesson["exercises"][0], "id": "X5", "outcome": "W6", "level": "support"})
        learners[0]["plan"]["steps"][1]["outcome"] = "W8"
        report = tools.consistency_issues(learners, lesson, outcomes, rubric)
        self.assertEqual((report["lesson"], report["plans"]), ([], {}))
        self.assertEqual(next(item["exercise"] for item in report["coverage"] if item["id"] == "language"), "X5")
        self.assertEqual([step["where"] for step in report["steps"]], ["exercise", "outcomes", "lesson"])


class Workflow(unittest.TestCase):
    def test_full_run(self):
        r = run()
        self.assertEqual(r.status, "done")
        by = {s["id"]: s for s in r.subs}
        self.assertEqual(by["E08"]["status"], "resubmit")
        self.assertIn("instruction_to_marker", by["E11"]["flags"])
        self.assertLess(by["E11"]["final"]["total"], 40)  # the planted instruction earned nothing
        self.assertEqual(r.stats["delivered"], 11)
        self.assertEqual(len(list((r.out_dir / "outbox").glob("*.txt"))), 12)
        self.assertTrue((r.out_dir / "marks.csv").exists())
        self.assertTrue((r.out_dir / "class_report.md").exists())
        self.assertEqual(r.files, ["marks.csv", "class_report.md"])
        self.assertEqual({a["id"] for a in r.report["attention"]}, {"E08", "E11"})
        # every stretch of agent work is on the timeline, closed, and in order
        self.assertTrue(r.spans and all(s["end"] is not None and s["end"] >= s["start"] for s in r.spans))
        self.assertEqual({s["agent"] for s in r.spans}, {"PL", "MK", "RV", "MS"})
        # the goal did not ask who is falling behind or for a lesson, so the Coach and the Designer stayed out of it
        self.assertEqual(r.agent_state, {"PL": "done", "MK": "done", "RV": "done", "MS": "done", "CO": "off", "DS": "off"})
        self.assertEqual((r.support, r.lesson), (None, None))
        json.dumps(r.snapshot())  # the dashboard must be able to read all of it

    def test_injected_fault_is_caught_and_fixed(self):
        clean = run()
        r = run(inject_fault=True)
        self.assertEqual(r.stats["sent_back"], 1)
        self.assertEqual(r.stats["fixed"], 1)
        self.assertEqual({s["id"]: s["final"] and s["final"]["total"] for s in r.subs},
                         {s["id"]: s["final"] and s["final"]["total"] for s in clean.subs})
        hit = [s for s in r.subs if s["rejected"]]
        self.assertEqual(len(hit), 1)  # the spoiled mark is kept for the record, and is not the final mark
        self.assertNotEqual(hit[0]["rejected"]["total"], hit[0]["final"]["total"])

    def test_goal_changes_the_plan(self):
        r = run("Mark the essays but do not send feedback, I only want the mark sheet.")
        self.assertFalse(r.plan["deliver"]["feedback"])
        self.assertEqual(r.stats["delivered"], 0)
        self.assertFalse((r.out_dir / "outbox").exists())
        self.assertTrue((r.out_dir / "marks.csv").exists())

    def test_teacher_resolves_escalation(self):
        r = run()
        s = r.subs[0]
        s["status"], s["feedback"] = "escalated", None
        r.stats["escalated"] += 1
        self.assertTrue(r.resolve(s["id"], "reviewer"))
        self.assertTrue(wait_for(lambda: s["status"] == "delivered"))
        self.assertEqual(s["final"], s["reviewer"])
        self.assertEqual(r.stats["human_interventions"], 1)
        self.assertFalse(r.resolve(s["id"], "reviewer"))  # already settled
        self.assertFalse(r.resolve("nobody", "marker"))
        self.assertFalse(r.resolve(r.subs[1]["id"], "teacher"))

    def test_left_out_essay_is_asked_for_again(self):
        llm = Scripted(mark=lambda reply, nth: without("E02")(reply, nth) if nth == 1 else reply)
        r = run(llm=llm)
        self.assertEqual(r.status, "done")
        self.assertEqual(llm.seen.count("mark"), 3 + 1)  # three batches, plus one request for the essay left out
        self.assertEqual(r.stats["delivered"], 11)
        self.assertEqual(r.stats["sent_back"], 0)

    def test_missing_second_mark_goes_to_the_teacher(self):
        r = run(llm=Scripted(review=without("E03")))
        s = next(x for x in r.subs if x["id"] == "E03")
        self.assertEqual(s["status"], "escalated")
        self.assertIsNone(s["reviewer"])
        self.assertIn("no second mark", s["issue"])
        self.assertEqual(r.stats["delivered"], 10)
        self.assertEqual(r.stats["escalated"], 1)
        self.assertFalse(r.resolve("E03", "reviewer"))  # there is no Reviewer mark to choose
        self.assertTrue(r.resolve("E03", "marker"))
        self.assertTrue(wait_for(lambda: s["status"] == "delivered"))
        self.assertEqual((r.stats["escalated"], r.stats["delivered"], r.stats["marked"]), (0, 11, 11))
        self.assertIsNone(s["issue"])

    def test_defence_the_reviewer_rejects_goes_to_the_teacher(self):
        rejects = lambda reply, nth: {"verdicts": [{**v, "approve": False, "reason": "Not convinced."} for v in reply["verdicts"]]}
        r = run(llm=Scripted(review=lower_content("E01", 12), verify=rejects))
        s = r.subs[0]
        self.assertEqual(s["status"], "escalated")
        self.assertIsNone(s["final"])
        self.assertIn("still disagree", s["issue"])
        self.assertEqual((r.stats["sent_back"], r.stats["fixed"], r.stats["escalated"]), (1, 0, 1))
        self.assertNotIn("E01", {p.name[:3] for p in (r.out_dir / "outbox").glob("*.txt")})  # nothing uncertain was sent
        self.assertIn("E01", {a["id"] for a in r.report["attention"]})
        self.assertTrue(r.resolve("E01", "reviewer"))
        self.assertTrue(wait_for(lambda: s["status"] == "delivered"))
        self.assertEqual(s["final"], s["reviewer"])
        self.assertTrue(wait_for(lambda: "E01" not in {a["id"] for a in r.report["attention"]}))

    def test_defence_the_reviewer_accepts_stands(self):
        r = run(llm=Scripted(review=lower_content("E01", 12)))  # the mock Reviewer accepts every defence
        s = r.subs[0]
        self.assertEqual(s["status"], "delivered")
        self.assertEqual(s["final"], s["marker"])
        self.assertEqual((r.stats["sent_back"], r.stats["fixed"], r.stats["escalated"]), (1, 0, 0))

    def test_teacher_decision_during_marking_is_delivered_exactly_once(self):
        llm = Scripted(review=without("E03"))
        r = Run(llm, GOAL, DATA, tempfile.mkdtemp())
        decide = lambda reply, nth: (r.resolve("E03", "marker"), reply)[1] if nth == 2 else reply
        llm.changes["mark"] = decide  # the teacher clicks while batch 2 is being marked
        r._guarded()
        time.sleep(0.2)  # a wrongly started late pass would show up here
        s = next(x for x in r.subs if x["id"] == "E03")
        self.assertEqual(s["status"], "delivered")
        self.assertEqual((r.stats["delivered"], r.stats["marked"], r.stats["escalated"], r.stats["human_interventions"]), (11, 11, 0, 1))
        self.assertEqual(llm.seen.count("report"), 1)  # the run finished the essay itself; no second pass
        self.assertEqual(len(list((r.out_dir / "outbox").glob("E03*"))), 1)

    def test_plan_cannot_drop_an_essay_that_can_be_marked(self):
        def greedy(reply, nth):
            reply["exclude"] += [{"id": "E11", "reason": "It contains an instruction."}, {"id": "E08", "reason": "Again."}]
            return reply
        r = run(llm=Scripted(plan=greedy))
        by = {s["id"]: s for s in r.subs}
        self.assertEqual(by["E11"]["status"], "delivered")
        self.assertEqual(by["E08"]["status"], "resubmit")
        self.assertEqual(r.stats["resubmit"], 1)  # listed twice by the plan, set aside once
        self.assertEqual([e["id"] for e in r.plan["exclude"]], ["E08"])
        self.assertTrue(any(e["kind"] == "GUARD" and e["sid"] == "E11" for e in r.events))

    def test_learner_with_no_essay_is_asked_to_resubmit_even_if_the_plan_forgets(self):
        data = Path(tempfile.mkdtemp()) / "data"
        shutil.copytree(DATA, data)
        with open(data / "class.csv", "a", encoding="utf-8") as f:
            f.write("E13,Lwazi Cele,lwazi.cele@example.com\n\n")
        forgetful = lambda reply, nth: {**reply, "exclude": []}
        r = run(llm=Scripted(plan=forgetful), data=data)
        self.assertEqual(r.status, "done")
        by = {s["id"]: s for s in r.subs}
        self.assertEqual(len(by), 13)  # the blank line is not a learner
        self.assertEqual(by["E13"]["status"], "resubmit")
        self.assertIn("I have not received it", by["E13"]["feedback"]["body"])
        self.assertEqual(by["E08"]["status"], "delivered")  # short, but the plan chose to mark it, which is allowed

    def test_feedback_that_fails_twice_is_held(self):
        def wrong_mark(reply, nth):
            for m in reply["messages"]:
                if m["id"] == "E01":
                    m["body"] = m["body"].replace("/50", "/60")
            return reply
        r = run(llm=Scripted(feedback=wrong_mark))
        s = r.subs[0]
        self.assertEqual(s["status"], "escalated")
        self.assertIn("failed its checks twice", s["issue"])
        self.assertEqual((r.stats["delivered"], r.stats["feedback_redone"], r.stats["escalated"], r.stats["marked"]), (10, 1, 1, 10))
        self.assertFalse(list((r.out_dir / "outbox").glob("E01*")))

    def test_broken_model_reply_stops_the_run_with_a_reason(self):
        def boom(reply, nth):
            raise LLMError("Gemini HTTP 429: quota exceeded")
        with mock.patch("traceback.print_exc"):  # the run prints its failure for the operator; not needed here
            r = run(llm=Scripted(review=boom))
        self.assertEqual(r.status, "failed")
        self.assertIn("quota exceeded", r.events[-1]["msg"])
        self.assertTrue(all(s["end"] is not None for s in r.spans))
        self.assertTrue(all(v == "waiting" for v in r.agent_state.values()))


class CoachAndDesigner(unittest.TestCase):
    """The two colleagues who work only when the goal asks: catch-up plans, and the next lesson."""

    def entry(self, r, sid):
        return next(e for e in r.support["learners"] if e["id"] == sid)

    def test_plan_brings_them_in_only_on_a_clear_yes(self):
        vague = lambda reply, nth: {**reply, "deliver": {"feedback": True, "support": "maybe", "lesson": 1}, "lesson_minutes": "a double period"}
        r = run(llm=Scripted(plan=vague))
        self.assertEqual(r.plan["deliver"], {"feedback": True, "csv": True, "report": True, "support": False, "lesson": False})
        self.assertEqual(r.plan["lesson_minutes"], 45)

    def test_learners_falling_behind_get_a_checked_plan(self):
        r = run(SUPPORT_GOAL)
        self.assertEqual(r.status, "done")
        flagged = {e["id"]: e for e in r.support["learners"]}
        self.assertEqual(list(flagged), ["E02", "E04", "E06", "E08", "E10"])
        self.assertEqual((r.support["checked"], r.support["waiting"]), (12, 0))
        self.assertEqual([s["kind"] for s in flagged["E04"]["signs"]], ["dropped"])
        self.assertEqual([s["kind"] for s in flagged["E06"]["signs"]], ["below", "weak_area"])
        self.assertEqual([s["kind"] for s in flagged["E08"]["signs"]], ["missing"])
        outcomes = {o["id"]: o for o in r.outcomes}
        for e in flagged.values():
            sub, plan = r._sub(e["id"]), e["plan"]
            self.assertEqual((e["status"], len(plan["steps"])), ("ready", 3), e["id"])
            if sub["final"]:  # the plan quotes this learner's essay and works on this learner's weakest area
                self.assertTrue(tools.quote_in_text(plan["evidence"], sub["text"]))
                self.assertTrue(any(e["weakest"]["id"] in outcomes[st["outcome"]]["criteria"] for st in plan["steps"]))
        self.assertEqual(flagged["E06"]["plan"]["steps"][0]["outcome"], "W3")  # written off the topic, so staying on it comes first
        text = (r.out_dir / "support_plans.md").read_text(encoding="utf-8")
        self.assertIn("## E06 Kabelo Mahlangu", text)
        self.assertNotIn("## E01", text)
        self.assertEqual(r.files, ["support_plans.md", "marks.csv", "class_report.md"])
        self.assertIn("CO", {s["agent"] for s in r.spans})
        self.assertEqual((r.agent_state["CO"], r.agent_state["DS"], r.lesson), ("done", "off", None))
        json.dumps(r.snapshot())

    def test_plan_that_fails_its_checks_goes_back_to_the_coach(self):
        def invented_quote(reply, nth):
            for plan in reply["plans"]:
                if plan["id"] == "E06" and nth == 1:
                    plan["evidence"] = "technology changed my whole life"
            return reply
        llm = Scripted(support=invented_quote)
        r = run(SUPPORT_GOAL, llm=llm)
        self.assertEqual(self.entry(r, "E06")["status"], "ready")
        self.assertEqual(llm.seen.count("support"), 2 + 1)  # five learners in batches of four, then E06 again
        self.assertIn("Your earlier plans were rejected", llm.prompts["support"][2])
        self.assertTrue(any(e["kind"] == "REJECT" and e["sid"] == "E06" and "does not appear in the learner's essay" in e["msg"] for e in r.events))

    def test_plan_that_fails_twice_is_held_and_the_teacher_is_told(self):
        def names_a_classmate(reply, nth):
            for plan in reply["plans"]:
                if plan["id"] == "E10":
                    plan["check"] = "Pair up with Thandi and compare essays."
            return reply
        r = run(SUPPORT_GOAL, llm=Scripted(support=names_a_classmate))
        e = self.entry(r, "E10")
        self.assertEqual((r.status, e["status"], e["plan"]), ("done", "held", None))
        self.assertEqual(e["problems"], ["mentions another learner (Thandi)"])
        text = (r.out_dir / "support_plans.md").read_text(encoding="utf-8")
        self.assertIn("No plan is offered", text)
        self.assertNotIn("Pair up with Thandi", text)  # the plan that failed is not put in front of the teacher
        self.assertIn("catch-up plan failed its checks", next(a["why"] for a in r.report["attention"] if a["id"] == "E10"))
        self.assertEqual(self.entry(r, "E02")["status"], "ready")  # one bad plan does not hold up the others

    def test_learner_whose_mark_the_teacher_settles_later_is_checked_then(self):
        r = run(SUPPORT_GOAL, llm=Scripted(review=without("E10")))
        self.assertEqual((r.support["checked"], r.support["waiting"]), (11, 1))
        self.assertNotIn("E10", [e["id"] for e in r.support["learners"]])
        self.assertTrue(r.resolve("E10", "marker"))
        self.assertTrue(wait_for(lambda: r._sub("E10")["status"] == "delivered"))
        self.assertEqual([e["id"] for e in r.support["learners"]], ["E02", "E04", "E06", "E08", "E10"])
        self.assertEqual((self.entry(r, "E10")["status"], r.support["waiting"]), ("ready", 0))
        self.assertIn("## E10", (r.out_dir / "support_plans.md").read_text(encoding="utf-8"))

    def test_lesson_aims_at_the_weakest_area_and_every_exercise_is_tried_blind(self):
        llm = Scripted()
        r = run(LESSON_GOAL, llm=llm)
        lesson = r.lesson
        self.assertEqual((r.status, lesson["status"], lesson["minutes"]), ("done", "ready", 30))
        self.assertEqual(lesson["target"]["id"], min(r.report["criteria_avg"], key=lambda c: c["avg_pct"])["id"])
        self.assertEqual(sum(p["minutes"] for p in lesson["phases"]), 30)
        self.assertEqual([ex["status"] for ex in lesson["exercises"]], ["ok"] * 4)
        self.assertTrue(all(ex["check"]["outcome"] == ex["outcome"] for ex in lesson["exercises"]))
        shown = llm.prompts["try"][0]  # the Reviewer saw the tasks, and nothing that gives the answers away
        for ex in lesson["exercises"]:
            self.assertIn(ex["task"], shown)
            self.assertNotIn(ex["answer"], shown)
            self.assertNotIn(ex["level"], shown.split("EXERCISES")[1])
        self.assertEqual((llm.seen.count("lesson"), llm.seen.count("try"), llm.seen.count("fix_exercises")), (1, 1, 0))
        self.assertNotIn("Thandi", llm.prompts["lesson"][0])  # the Designer works from class figures, not from learners
        text = (r.out_dir / "lesson_plan.md").read_text(encoding="utf-8")
        self.assertIn("## Model answers", text)
        self.assertIn("lesson_plan.md", r.files)
        self.assertEqual((r.agent_state["CO"], r.agent_state["DS"], r.support), ("off", "done", None))
        json.dumps(r.snapshot())

    def test_mislabelled_exercise_is_caught_blind_and_put_right(self):
        clean = run(LESSON_GOAL).lesson
        r = run(LESSON_GOAL, inject_fault=True)
        lesson = r.lesson
        self.assertEqual(lesson["status"], "ready")
        self.assertEqual([ex["status"] for ex in lesson["exercises"]], ["ok", "fixed", "ok", "ok"])
        self.assertEqual([ex["outcome"] for ex in lesson["exercises"]], [ex["outcome"] for ex in clean["exercises"]])
        self.assertIn("judged that it practises W1", lesson["exercises"][1]["problems"][0])  # why it was sent back stays on record
        self.assertEqual(r.stats["sent_back"], 1)  # the wrong mark planted in the same run; exercises are not essays

    def test_exercise_that_still_fails_is_dropped_and_the_lesson_stands_without_it(self):
        def nothing_to_work_on(reply, nth):
            reply["exercises"][3]["task"] = "Improve the paragraph that your teacher hands out in class."
            return reply
        r = run(LESSON_GOAL, llm=Scripted(lesson=nothing_to_work_on))
        lesson = r.lesson
        self.assertEqual((lesson["status"], [ex["status"] for ex in lesson["exercises"]]), ("ready", ["ok", "ok", "ok", "dropped"]))
        self.assertTrue(any(e["kind"] == "DROP" and "X4" in e["msg"] for e in r.events))
        text = (r.out_dir / "lesson_plan.md").read_text(encoding="utf-8")
        self.assertIn("**X3**", text)
        self.assertNotIn("**X4**", text)

    def test_outcome_that_no_checked_exercise_practises_comes_off_the_lesson(self):
        def overclaims(reply, nth):
            reply["outcomes"].append("W3")
            reply["exercises"][3]["outcome"] = "W3"  # the task really practises W2, as the blind attempt will show
            return reply
        r = run(LESSON_GOAL, llm=Scripted(lesson=overclaims))
        self.assertEqual((r.lesson["status"], r.lesson["outcomes"]), ("ready", ["W1", "W2"]))
        self.assertEqual((r.lesson["exercises"][3]["status"], r.lesson["exercises"][3]["outcome"]), ("fixed", "W2"))
        self.assertTrue(any(e["kind"] == "GUARD" and e["msg"].startswith("W3 taken off") for e in r.events))

    def test_lesson_that_does_not_add_up_is_sent_back_then_held(self):
        def runs_over(always):
            def change(reply, nth):
                if always or nth == 1:
                    reply["phases"][0]["minutes"] += 10
                return reply
            return change
        llm = Scripted(lesson=runs_over(always=False))
        r = run(LESSON_GOAL, llm=llm)
        self.assertEqual((r.lesson["status"], llm.seen.count("lesson")), ("ready", 2))  # one redraft put it right
        self.assertIn("add up to 40 minutes, not 30", llm.prompts["lesson"][1])

        llm = Scripted(lesson=runs_over(always=True))
        r = run(LESSON_GOAL, llm=llm)
        self.assertEqual((r.status, r.lesson["status"], llm.seen.count("lesson")), ("done", "held", 2))
        self.assertEqual(r.lesson["problems"], ["has phases that add up to 40 minutes, not 30"])
        self.assertNotIn("try", llm.seen)  # nothing was checked further, and nothing was written
        self.assertFalse((r.out_dir / "lesson_plan.md").exists())
        self.assertNotIn("lesson_plan.md", r.files)
        self.assertEqual(r.stats["delivered"], 11)  # the marking was delivered all the same

    def test_other_outcomes_than_the_ones_shipped_still_give_a_lesson_and_plans(self):
        data = Path(tempfile.mkdtemp()) / "data"
        shutil.copytree(DATA, data)
        (data / "outcomes.json").unlink()  # the rubric's own criteria now stand in as outcomes
        r = run(SUPPORT_GOAL + " Also draft a lesson with exercises.", data=data)
        self.assertEqual((r.status, r.lesson["status"]), ("done", "ready"))
        self.assertEqual({e["status"] for e in r.support["learners"]}, {"ready"})
        self.assertTrue(set(r.lesson["outcomes"]) <= {"content", "language", "structure"})

    def test_support_gap_is_sent_back_to_the_designer_and_corrected(self):
        llm = Scripted()
        r = run(WHOLE_JOB, llm=llm)
        self.assertEqual((r.status, r.consistency["status"]), ("done", "agreed"))
        self.assertEqual([item["agent"] for item in r.consistency["opened"]], ["DS"])
        self.assertIn("Language", r.consistency["opened"][0]["text"])
        self.assertIn("E02", r.consistency["opened"][0]["text"])
        self.assertIn("E10", r.consistency["opened"][0]["text"])
        language = next(item for item in r.consistency["coverage"] if item["id"] == "language")
        self.assertTrue(language["exercise"])
        self.assertTrue(all(item["exercise"] for item in r.consistency["coverage"]))
        self.assertIn(language["exercise"], (r.out_dir / "lesson_plan.md").read_text(encoding="utf-8"))
        self.assertEqual({step["where"] for step in r.consistency["steps"]} & {"lesson", "outcomes"}, {"lesson", "outcomes"})
        self.assertTrue(all(step["where"] != "none" for step in r.consistency["steps"]))
        self.assertEqual((llm.seen.count("align_lesson"), llm.seen.count("align_support"), llm.seen.count("try")), (1, 0, 2))
        self.assertTrue(any(span["agent"] == "RV" and "catch-up plans against the lesson" in span["what"] for span in r.spans))
        self.assertTrue(any(span["agent"] == "DS" and "support work matches" in span["what"] for span in r.spans))
        report = (r.out_dir / "class_report.md").read_text(encoding="utf-8")
        self.assertIn("## Catch-up and the lesson", report)
        self.assertIn("Sent back to the Designer once", report)
        self.assertEqual(r.files, ["support_plans.md", "lesson_plan.md", "marks.csv", "class_report.md"])
        self.assertEqual(len(list((r.out_dir / "outbox").glob("*.txt"))), 12)
        self.assertIn("now agree", r.events[-1]["msg"])
        json.dumps(r.snapshot())

    def test_injected_fault_and_the_consistency_gap_are_both_corrected(self):
        r = run(WHOLE_JOB, inject_fault=True)
        self.assertEqual((r.status, r.stats["sent_back"], r.stats["fixed"]), ("done", 1, 1))
        self.assertEqual(r.consistency["status"], "agreed")
        self.assertEqual(r.lesson["status"], "ready")
        self.assertIn("fixed", [ex["status"] for ex in r.lesson["exercises"]])
        self.assertTrue(any(item["exercise"] for item in r.consistency["coverage"] if item["id"] == "language"))
        self.assertTrue(any(e["kind"] == "TEST" and e["sid"] for e in r.events))
        self.assertTrue(any(e["kind"] == "REJECT" and "support exercise" in e["msg"] for e in r.events))
        for name in ("marks.csv", "class_report.md", "support_plans.md", "lesson_plan.md"):
            self.assertTrue((r.out_dir / name).exists(), name)
        self.assertEqual(len(list((r.out_dir / "outbox").glob("*.txt"))), 12)
        self.assertEqual(set(r.agent_state.values()), {"done"})

    def test_lesson_that_stays_inconsistent_is_held_for_the_teacher(self):
        def undo(reply, nth):
            reply["outcomes"] = [outcome for outcome in reply["outcomes"] if outcome in ("W1", "W2")]
            reply["exercises"] = [ex for ex in reply["exercises"] if ex["outcome"] in ("W1", "W2")]
            return reply
        r = run(WHOLE_JOB, llm=Scripted(align_lesson=undo))
        self.assertEqual((r.status, r.lesson["status"], r.consistency["status"]), ("done", "held", "held"))
        self.assertTrue(any("Language" in problem for problem in r.lesson["problems"]))
        self.assertNotIn("lesson_plan.md", r.files)
        self.assertFalse((r.out_dir / "lesson_plan.md").exists())
        self.assertTrue((r.out_dir / "support_plans.md").exists())
        self.assertIn("held for the teacher", (r.out_dir / "class_report.md").read_text(encoding="utf-8").lower())
        self.assertEqual(r.stats["delivered"], 11)
        self.assertTrue(any(e["kind"] == "ESCALATE" and "still disagree" in e["msg"] for e in r.events))

    def test_unmapped_step_is_sent_back_to_the_coach_and_corrected(self):
        llm = Scripted()
        r = run(WHOLE_JOB, llm=llm)
        entry = next(e for e in r.support["learners"] if e["id"] == "E02")
        entry["plan"]["steps"][0]["outcome"] = "NOPE"
        r._align()
        self.assertEqual((entry["status"], r.consistency["status"]), ("ready", "agreed"))
        self.assertNotEqual(entry["plan"]["steps"][0]["outcome"], "NOPE")
        self.assertIn(entry["plan"]["steps"][0]["outcome"], r.lesson["outcomes"])
        self.assertEqual([item["agent"] for item in r.consistency["opened"]], ["DS", "CO"])
        self.assertEqual(llm.seen.count("align_support"), 1)
        self.assertIn(entry["plan"]["steps"][0]["outcome"], (r.out_dir / "support_plans.md").read_text(encoding="utf-8"))

    def test_unmapped_step_is_sent_back_to_the_coach_once_then_held(self):
        llm = Scripted()
        r = run(WHOLE_JOB, llm=llm)
        entry = next(e for e in r.support["learners"] if e["id"] == "E02")
        entry["plan"]["steps"][0]["outcome"] = "NOPE"

        def still_wrong(reply, nth):
            for plan in reply["plans"]:
                plan["steps"][0]["outcome"] = "NOPE"
            return reply
        llm.changes["align_support"] = still_wrong
        r._align()
        self.assertEqual(entry["status"], "held")
        self.assertTrue(any("NOPE" in problem for problem in entry["problems"]))
        self.assertEqual(llm.seen.count("align_support"), 1)
        text = (r.out_dir / "support_plans.md").read_text(encoding="utf-8")
        self.assertIn("No plan is offered", text)
        self.assertNotIn("Outcome NOPE", text)
        self.assertEqual(next(e["status"] for e in r.support["learners"] if e["id"] == "E06"), "ready")
        self.assertEqual(r.lesson["status"], "ready")
        r._align()  # a plan already sent back once is not sent back again
        self.assertEqual((llm.seen.count("align_support"), r.consistency["status"], entry["status"]), (1, "held", "held"))


# ---- the Gemini client, against a stand-in server -------------------------------------------

def answer(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return 200, {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def error(code, message):
    return code, {"error": {"code": code, "message": message}}


class FakeGemini(BaseHTTPRequestHandler):
    script, seen, models = [], [], []

    def log_message(self, *a):
        pass

    def _reply(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeGemini.seen.append({"path": self.path, "body": body, "key": self.headers.get("x-goog-api-key")})
        self._reply(*FakeGemini.script.pop(0))

    def do_GET(self):
        self._reply(200, {"models": [{"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]} for n in FakeGemini.models]})


class GeminiClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeGemini)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        os.environ["GEMINI_API_BASE"] = f"http://127.0.0.1:{cls.httpd.server_address[1]}/v1beta"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        del os.environ["GEMINI_API_BASE"]

    def client(self, script, model=None):
        FakeGemini.script, FakeGemini.seen = list(script), []
        g = Gemini("test-key", model)
        g.min_gap, g.delays = 0, [0, 0]
        self.notes = []
        return g

    def ask(self, g):
        return g.call("mark", "You are the Marker.", "Mark this.", log=self.notes.append)

    def test_request_and_reply(self):
        g = self.client([answer({"marks": []})])
        self.assertEqual(self.ask(g), {"marks": []})
        sent = FakeGemini.seen[0]
        self.assertEqual(sent["path"], "/v1beta/models/gemini-3.8-flash:generateContent")
        self.assertEqual(sent["key"], "test-key")
        self.assertEqual(sent["body"]["systemInstruction"]["parts"][0]["text"], "You are the Marker.")
        self.assertEqual(sent["body"]["contents"][0]["parts"][0]["text"], "Mark this.")
        self.assertEqual(sent["body"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertNotIn("temperature", sent["body"]["generationConfig"])  # deprecated on current models

    def test_waits_and_retries_when_gemini_is_busy(self):
        g = self.client([error(429, "Resource exhausted."), error(503, "Overloaded."), answer({"ok": True})])
        self.assertEqual(self.ask(g), {"ok": True})
        self.assertEqual(g.calls, 3)
        self.assertEqual(len(self.notes), 2)

    def test_gives_up_with_the_reason_when_the_quota_is_gone(self):
        g = self.client([error(429, "Quota exceeded for this model.")] * 3)
        with self.assertRaisesRegex(LLMError, "HTTP 429: Quota exceeded"):
            self.ask(g)

    def test_switches_model_when_the_configured_one_is_gone(self):
        FakeGemini.models = ["gemini-2.5-flash", "gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.10-flash-lite",
                             "gemini-3.5-flash-lite", "gemini-omni-1.2-flash", "gemini-3-flash-preview", "gemini-4-carbon"]
        g = self.client([error(404, "models/gemini-2.5-flash is no longer available."), answer({"ok": True})], model="gemini-2.5-flash")
        self.assertEqual(self.ask(g), {"ok": True})
        self.assertEqual(g.model, "gemini-3.8-flash")  # newest plain Flash: not lite, preview or a video model
        self.assertIn("gemini-3.8-flash", FakeGemini.seen[-1]["path"])

    def test_no_usable_model_is_explained(self):
        FakeGemini.models = ["gemini-omni-1.2-flash", "gemini-4-carbon"]
        g = self.client([error(404, "Not found.")], model="gemini-9-flash")
        with self.assertRaisesRegex(LLMError, "GEMINI_MODEL"):
            self.ask(g)

    def test_drops_settings_gemini_rejects(self):
        g = self.client([error(400, "Unknown name thinkingConfig."), error(400, "Unknown name responseMimeType."),
                         answer('```json\n{"ok": true}\n```')])
        self.assertEqual(self.ask(g), {"ok": True})
        bodies = [s["body"] for s in FakeGemini.seen]
        self.assertIn("thinkingConfig", bodies[0]["generationConfig"])
        self.assertEqual(bodies[1]["generationConfig"], {"responseMimeType": "application/json"})
        self.assertNotIn("generationConfig", bodies[2])
        FakeGemini.script = [answer({"again": 1})]
        self.assertEqual(self.ask(g), {"again": 1})  # and it remembers what worked
        self.assertNotIn("generationConfig", FakeGemini.seen[-1]["body"])

    def test_bad_key_fails_at_once_with_advice(self):
        g = self.client([error(400, "API key not valid. Please pass a valid API key.")])
        with self.assertRaisesRegex(LLMError, "GEMINI_API_KEY"):
            self.ask(g)
        self.assertEqual(g.calls, 1)

    def test_asks_again_for_invalid_json_then_gives_up(self):
        g = self.client([answer("I think the mark is"), answer({"ok": True})])
        self.assertEqual(self.ask(g), {"ok": True})
        g = self.client([answer("no"), answer("still no"), answer("")])
        with self.assertRaisesRegex(LLMError, "valid JSON"):
            self.ask(g)

    def test_blocked_prompt_is_reported(self):
        g = self.client([(200, {"promptFeedback": {"blockReason": "SAFETY"}})])
        with self.assertRaisesRegex(LLMError, "SAFETY"):
            self.ask(g)

    def test_unreachable_server_is_reported(self):
        g = self.client([])
        g.api = "http://127.0.0.1:9/v1beta"  # nothing listens here
        with self.assertRaisesRegex(LLMError, "Cannot reach Gemini"):
            self.ask(g)


def chat(content, model="some/free-model"):
    """An OpenRouter reply carrying `content` (a dict is sent as JSON text)."""
    text = content if isinstance(content, str) else json.dumps(content)
    return 200, {"model": model, "choices": [{"message": {"role": "assistant", "content": text}}]}


class FakeOpenRouter(FakeGemini):
    script, seen = [], []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOpenRouter.seen.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
        self._reply(*FakeOpenRouter.script.pop(0))


class OpenRouterClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gemini = ThreadingHTTPServer(("127.0.0.1", 0), FakeGemini)
        cls.router = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenRouter)
        for s in (cls.gemini, cls.router):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        os.environ["GEMINI_API_BASE"] = f"http://127.0.0.1:{cls.gemini.server_address[1]}/v1beta"
        os.environ["OPENROUTER_API_BASE"] = f"http://127.0.0.1:{cls.router.server_address[1]}/api/v1"

    @classmethod
    def tearDownClass(cls):
        for s in (cls.gemini, cls.router):
            s.shutdown()
            s.server_close()
        del os.environ["GEMINI_API_BASE"], os.environ["OPENROUTER_API_BASE"]

    def setUp(self):
        FakeGemini.script, FakeGemini.seen, FakeOpenRouter.script, FakeOpenRouter.seen = [], [], [], []
        self.notes = []

    def router_client(self, script, model=None):
        FakeOpenRouter.script = list(script)
        o = OpenRouter("router-key", model)
        o.min_gap, o.delays = 0, [0, 0]
        return o

    def both(self, gemini_script, router_script):
        FakeGemini.script = list(gemini_script)
        g = Gemini("gemini-key")
        g.min_gap, g.delays = 0, [0, 0, 0, 0]
        return Fallback(g, self.router_client(router_script))

    def ask(self, llm):
        return llm.call("mark", "You are the Marker.", "Mark this.", log=self.notes.append)

    def test_request_and_reply(self):
        o = self.router_client([chat({"marks": []}, model="vendor/picked:free")])
        self.assertEqual(self.ask(o), {"marks": []})
        sent = FakeOpenRouter.seen[0]
        self.assertEqual(sent["path"], "/api/v1/chat/completions")
        self.assertEqual(sent["auth"], "Bearer router-key")
        self.assertEqual(sent["body"]["model"], "openrouter/free")
        self.assertEqual(sent["body"]["messages"], [{"role": "system", "content": "You are the Marker."},
                                                    {"role": "user", "content": "Mark this."}])
        self.assertEqual(sent["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(o.served, "vendor/picked:free")

    def test_drops_json_mode_when_the_model_rejects_it(self):
        o = self.router_client([error(400, "response_format is not supported."), chat('Here you go: {"ok": true}')])
        self.assertEqual(self.ask(o), {"ok": True})
        self.assertNotIn("response_format", FakeOpenRouter.seen[1]["body"])

    def test_busy_then_answers(self):
        o = self.router_client([error(429, "Rate limited."), (200, {"error": {"code": 502, "message": "Upstream failed."}}),
                                chat({"ok": True})])
        self.assertEqual(self.ask(o), {"ok": True})
        self.assertEqual(o.calls, 3)

    def test_bad_key_and_used_up_allowance_are_explained(self):
        with self.assertRaisesRegex(LLMError, "OPENROUTER_API_KEY"):
            self.ask(self.router_client([error(401, "No auth credentials found.")]))
        o = self.router_client([error(429, "Rate limit exceeded: free-models-per-day.")])
        with self.assertRaisesRegex(Busy, "daily free limit"):
            self.ask(o)
        self.assertEqual(o.calls, 1)  # no point waiting for tomorrow

    def test_empty_reply_is_asked_again(self):
        o = self.router_client([chat(""), chat({"ok": True})])
        self.assertEqual(self.ask(o), {"ok": True})

    def test_openrouter_takes_over_when_gemini_is_busy(self):
        llm = self.both([error(503, "This model is currently experiencing high demand.")] * 3,
                        [chat({"first": 1}), chat({"second": 2})])
        self.assertEqual((llm.name, llm.standby), ("gemini", "openrouter/free"))
        self.assertEqual(self.ask(llm), {"first": 1})
        self.assertEqual(len(FakeGemini.seen), 3)  # tried, waited twice (not four times), then switched
        self.assertTrue(any("Switching to OpenRouter" in n for n in self.notes))
        self.assertEqual(self.ask(llm), {"second": 2})  # and it stays on OpenRouter for the rest of the run
        self.assertEqual(len(FakeGemini.seen), 3)
        self.assertEqual((llm.name, llm.standby, llm.calls), ("openrouter", None, 5))

    def test_gemini_keeps_the_work_while_it_answers(self):
        llm = self.both([answer({"ok": True})], [])
        self.assertEqual(self.ask(llm), {"ok": True})
        self.assertEqual((llm.name, FakeOpenRouter.seen), ("gemini", []))

    def test_openrouter_takes_over_when_the_gemini_key_is_refused(self):
        llm = self.both([error(400, "API key not valid.")], [chat({"ok": True})])
        self.assertEqual(self.ask(llm), {"ok": True})

    def test_when_both_fail_the_openrouter_reason_is_given(self):
        llm = self.both([error(503, "Overloaded.")] * 3, [error(503, "Overloaded too.")] * 3)
        with self.assertRaisesRegex(Busy, "OpenRouter HTTP 503"):
            self.ask(llm)

    def test_keys_in_env_pick_the_backend(self):
        def pick(**env):
            with mock.patch.dict(os.environ, env):
                for k in ("MOCK", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
                    if k not in env:
                        os.environ.pop(k, None)
                llm = make_llm()
                return [backend.name for backend in getattr(llm, "chain", [llm])]
        self.assertEqual(pick(), ["mock"])
        # Whenever a live model is used, the offline marker stands behind it.
        self.assertEqual(pick(GEMINI_API_KEY="g"), ["gemini", "mock"])
        self.assertEqual(pick(OPENROUTER_API_KEY="o"), ["openrouter", "mock"])
        self.assertEqual(pick(GEMINI_API_KEY="g", OPENROUTER_API_KEY="o"), ["gemini", "openrouter", "mock"])
        self.assertEqual(pick(GEMINI_API_KEY="g", OPENROUTER_API_KEY="o", MOCK="1"), ["mock"])
        self.assertEqual(os.environ.get("MOCK"), "1")  # the tests' own setting is restored

    def test_a_run_finishes_on_openrouter_when_gemini_is_busy(self):
        class Busy503(Gemini):
            def call(self, *a, **k):
                self.calls += 1
                raise Busy("Gemini HTTP 503: high demand")

        class Router(Mock):  # OpenRouter's place, answering with the offline replies
            name, model, served = "openrouter", "openrouter/free", "vendor/picked:free"

        llm = Fallback(Busy503("k"), Router())
        r = Run(llm, GOAL, DATA, tempfile.mkdtemp())
        r._guarded()
        self.assertEqual(r.status, "done")
        self.assertEqual(r.snapshot()["llm"]["name"], "openrouter")
        self.assertEqual(llm.primary.calls, 1)  # Gemini was asked once, not once per step
        self.assertTrue(any("Switching to OpenRouter" in e["msg"] for e in r.events))

    def test_the_offline_marker_takes_over_when_no_live_model_answers(self):
        FakeGemini.script = [error(503, "Overloaded.")] * 3
        g = Gemini("gemini-key")
        g.min_gap, g.delays = 0, [0, 0, 0, 0]
        llm = Fallback(g, self.router_client([error(429, "Rate limit exceeded: free-models-per-day.")]), Mock())
        self.assertEqual((llm.name, llm.standby), ("gemini", "openrouter/free"))
        reply = llm.call("intake", "You are the Planner.", "Read them?", {"goal": "Mark the essays.", "pages": 2}, log=self.notes.append)
        self.assertIn("ingest", reply)  # the offline marker answered
        self.assertEqual((llm.name, llm.standby), ("mock", None))
        self.assertEqual((len(FakeGemini.seen), len(FakeOpenRouter.seen)), (3, 1))
        self.assertTrue(any("Gemini could not answer" in n and "Switching to OpenRouter" in n for n in self.notes))
        self.assertTrue(any("OpenRouter could not answer" in n and "offline demo marker" in n for n in self.notes))

    def test_a_run_finishes_offline_when_every_live_model_fails(self):
        class Down(Gemini):
            def call(self, *a, **k):
                self.calls += 1
                raise Busy("Gemini HTTP 503: high demand")

        class Refused(OpenRouter):
            def call(self, *a, **k):
                self.calls += 1
                raise LLMError("OpenRouter refused the API key (HTTP 401).")

        for live in ([Down("k"), Refused("k")], [Down("k")], [Refused("k")]):
            llm = Fallback(*live, Mock())
            r = Run(llm, GOAL, DATA, tempfile.mkdtemp())
            r._guarded()
            self.assertEqual(r.status, "done")
            self.assertEqual(r.stats["delivered"], 11)
            snap = r.snapshot()["llm"]
            self.assertEqual((snap["name"], snap["switched"]), ("mock", True))
            self.assertEqual([backend.calls for backend in live], [1] * len(live))  # each was asked once, not once per step
            self.assertTrue(any("offline demo marker" in e["msg"] for e in r.events))  # and the log says so
            self.assertFalse(any(e["kind"] == "ERROR" for e in r.events))

    def test_a_model_that_answers_nonsense_is_replaced_too(self):
        FakeGemini.script = [answer("no"), answer("still no"), answer("nope")]
        g = Gemini("gemini-key")
        g.min_gap = 0
        llm = Fallback(g, Mock())
        reply = llm.call("intake", "You are the Planner.", "Read them?", {"goal": "Mark the essays.", "pages": 2}, log=self.notes.append)
        self.assertIn("ingest", reply)
        self.assertEqual(llm.name, "mock")

    def test_live_models_are_given_a_time_limit_when_one_is_set(self):
        class Slow(Mock):
            name, model = "gemini", "gemini-test"

        llm = Fallback(Slow(), Mock(), deadline=0.05)
        llm.call("intake", "s", "p", {"goal": "Mark the essays.", "pages": 2}, log=self.notes.append)
        self.assertEqual(llm.name, "gemini")  # inside the limit the live model keeps the work
        time.sleep(0.1)
        llm.call("intake", "s", "p", {"goal": "Mark the essays.", "pages": 2}, log=self.notes.append)
        self.assertEqual(llm.name, "mock")
        self.assertTrue(any("offline demo marker" in n for n in self.notes))
        untimed = Fallback(Slow(), Mock(), deadline=0)
        untimed.call("intake", "s", "p", {"goal": "Mark the essays.", "pages": 2})
        time.sleep(0.1)
        untimed.call("intake", "s", "p", {"goal": "Mark the essays.", "pages": 2})
        self.assertEqual(untimed.name, "gemini")  # no limit unless one is set


# ---- the web server the dashboard talks to ---------------------------------------------------

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

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def state(self, since=0):
        return json.loads(self.get(f"/api/state?since={since}")[2])

    def test_a_run_from_start_to_download(self):
        idle = self.state()
        self.assertEqual((idle["status"], idle["id"], len(idle["subs"])), ("idle", None, 12))
        self.assertEqual((idle["support"], idle["lesson"], len(idle["outcomes"]), len(idle["agents"])), (None, None, 8, 6))
        self.assertEqual(self.get("/api/file?name=marks.csv")[0], 404)
        self.assertEqual(self.post("/api/run", {"goal": "  "})[0], 400)
        self.assertEqual(self.post("/api/resolve", {"id": "E01", "choice": "marker"})[0], 404)

        self.assertEqual(self.post("/api/run", {"goal": GOAL, "inject_fault": True}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.state(10 ** 6)["status"] == "done", 20))
        done = self.state()
        self.assertEqual(done["stats"]["fixed"], 1)
        self.assertEqual(done["next"], len(done["events"]))
        self.assertEqual(self.state(done["next"] - 2)["events"], done["events"][-2:])
        self.assertEqual(self.state("abc")["next"], done["next"])  # a bad cursor is not an error
        self.assertEqual(done["elapsed"], self.state()["elapsed"])  # the clock stops when the run does

        code, headers, body = self.get("/api/file?name=marks.csv")
        self.assertEqual(code, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(len(body.decode().strip().splitlines()), 13)  # header + 12 learners
        self.assertEqual(self.get("/api/file?name=class_report.md")[0], 200)
        for name in ("../run.py", "outbox", "..%2F..%2Frun.py", ""):
            self.assertEqual(self.get(f"/api/file?name={name}")[0], 404, name)

        self.assertEqual(self.post("/api/resolve", {"id": "E01", "choice": "marker"})[0], 400)  # nothing is waiting
        self.assertEqual(self.post("/api/resolve", {"id": "nobody", "choice": "marker"})[0], 400)
        self.assertEqual(self.get("/api/nothing")[0], 404)

        # A second goal that calls on the whole team: the dashboard gets the plans and the lesson, and both files.
        self.assertEqual(self.get("/api/file?name=lesson_plan.md")[0], 404)  # the first run wrote none
        goal = SUPPORT_GOAL + " Also draft a 45-minute lesson with exercises."
        self.assertEqual(self.post("/api/run", {"goal": goal}), (200, {"ok": True}))
        self.assertTrue(wait_for(lambda: self.state(10 ** 6)["status"] == "done", 20))
        done = self.state()
        self.assertEqual((len(done["support"]["learners"]), done["lesson"]["status"]), (5, "ready"))
        self.assertEqual(set(done["agents"].values()), {"done"})
        for name in ("support_plans.md", "lesson_plan.md"):
            code, headers, body = self.get(f"/api/file?name={name}")
            self.assertEqual((code, headers["Content-Type"]), (200, "text/markdown; charset=utf-8"))
            self.assertTrue(body.decode("utf-8").startswith("# "))

    def test_pages_and_assets(self):
        code, headers, body = self.get("/")
        self.assertIn(code, (200, 503))  # 503 only when the dashboard has not been built yet
        if code == 200:
            self.assertIn("text/html", headers["Content-Type"])
            self.assertEqual(self.get("/some/app/route")[0], 200)  # the app page, for any in-app address
        self.assertIn(self.get("/assets/missing-file.js")[0], (404, 503))
        self.assertIn(self.get("/..%2Frun.py")[0], (404, 503))  # nothing outside the built dashboard is served


if __name__ == "__main__":
    unittest.main()
