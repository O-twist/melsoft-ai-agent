"""Runs the agent team on one goal and records everything that happens."""
import copy
import itertools
import re
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

from . import agents, ingest, risk, story, tools
from .llm import LLMError

AGENTS = {"PL": "Planner", "MK": "Marker", "RV": "Reviewer", "MS": "Messenger", "CO": "Coach", "DS": "Designer"}
CLERK = "CL"  # the Clerk is on the team only for a run that was given photographed scripts
FLAG_TEXT = {
    "missing": "nothing was submitted",
    "too_short": "shorter than the minimum length",
    "instruction_to_marker": "contains text that tries to instruct the marker (it was marked normally)",
}
_run_numbers = itertools.count(1)


class Stopped(Exception):
    """The teacher stopped the run while checking the materials, before anything was planned."""


def _n(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


class Run:
    def __init__(self, llm, goal, data_dir="data", out_dir="output", inject_fault=False,
                 pages=None, batch=None, inject_ocr_fault=False, assessment="essay", live_attempts=None,
                 review=False, record=False):
        self.llm, self.goal, self.inject_fault = llm, goal, inject_fault
        # record: keep a small picture of the run at every log line, so a run that finished inside one web
        # request (a serverless deployment) can be played back in the browser step by step.
        self.record, self.frames = record, []
        self.owner = None  # the teacher who started the run (None for a guest, or when accounts are off)
        # review: the teacher reads the memo, the rubric and every script before the Planner plans anything.
        self.review = {"wanted": bool(review), "waiting": False, "materials": None, "choice": None, "note": ""}
        self._reviewed = threading.Event()
        # What is being marked: the essays (the default), or the PC assembly practical's attempt logs.
        self.assessment = assessment if assessment in tools.RUBRIC_FILES else "essay"
        self.live_attempts = live_attempts  # attempts recorded in the dashboard's virtual lab, which replace the files
        if self.assessment != "essay":
            pages = None  # photographed scripts are essays; a practical has none
        self.pages, self.batch, self.inject_ocr_fault = list(pages or []), batch, bool(inject_ocr_fault and pages)
        self.intake = None  # the Clerk's work on the photographed scripts, when there is any
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.id = f"{stamp}-{next(_run_numbers)}"
        self.data_dir, self.out_dir = data_dir, Path(out_dir) / stamp
        self.where = f"{Path(out_dir).name}/{stamp}"  # how the output folder is named in messages
        self.events, self.spans, self.files = [], [], []
        self.subs, self.plan, self.report = [], None, None
        self.support, self.lesson = None, None  # the Coach's and the Designer's work, when the goal asks for it
        self.consistency = None  # whether those two agree, once both have finished
        self._lesson_revised = False  # the cross-check sends the lesson back at most once
        self._plans_revised = set()
        self.status = "running"
        self.agent_state = {k: "waiting" for k in AGENTS}
        if self.pages:  # the Clerk works between the Planner and the Marker
            self.agent_state = {"PL": "waiting", CLERK: "waiting", **{k: "waiting" for k in AGENTS if k != "PL"}}
        self.stats = {"marked": 0, "sent_back": 0, "fixed": 0, "escalated": 0, "resubmit": 0,
                      "feedback_redone": 0, "delivered": 0, "human_interventions": 0}
        self.started, self.ended = time.time(), None
        self.lock = threading.RLock()  # guards the state the web server reads while agents work
        self.work = threading.Lock()   # agent work happens one piece at a time: the run, then any late teacher decisions
        self._closing = False          # True once marking is over and feedback and delivery have begun
        self.rubric = tools.load_rubric(data_dir, self.assessment)
        self.outcomes = tools.load_outcomes(data_dir, self.rubric)
        self.noun = self.rubric.get("work", "essay")  # "essay", or "practical attempt"

    # ---- bookkeeping -------------------------------------------------
    def _skipped(self):
        """Seconds of pacing the offline marker left out, which the run's clock still counts."""
        return getattr(self.llm, "skipped", 0.0)

    def _t(self):
        return round(time.time() - self.started + self._skipped(), 1)

    def emit(self, agent, kind, msg, sid=None):
        with self.lock:
            self.events.append({"t": self._t(), "agent": agent, "kind": kind, "msg": msg, "sid": sid})
            self._keep_frame()

    def _keep_frame(self):
        if self.record:
            with self.lock:
                self.frames.append(self._frame())

    def _frame(self):
        """Where the run stands now, taken at every log line and whenever an agent picks up or puts down work:
        enough for the dashboard to show this moment again later."""
        return {
            "t": self._t(), "n": len(self.events), "agents": dict(self.agent_state), "stats": dict(self.stats),
            "spans": len(self.spans),
            "subs": {s["id"]: [s["status"]] + [bool(s.get(k)) for k in ("marker", "reviewer", "final", "feedback")]
                     for s in self.subs},
            "has": [k for k in ("plan", "report", "support", "lesson", "consistency", "intake") if getattr(self, k)],
        }

    def recording(self):
        """The finished run for a browser to play back: the last snapshot, each moment on the way, and the text files."""
        files = {}
        for name in self.files:
            path = self.out_dir / name
            if path.suffix in (".csv", ".md", ".txt") and path.is_file() and path.stat().st_size < 300_000:
                files[name] = path.read_text(encoding="utf-8")
        files["corrections.md"] = story.to_markdown(self.corrections())
        return {**self.snapshot(), "frames": self.frames, "file_texts": files}

    @contextmanager
    def _busy(self, agent, what):
        """Mark an agent as working, and record the stretch of work for the run's timeline."""
        span = {"agent": agent, "what": what, "start": self._t(), "end": None}
        before = self.agent_state[agent]
        with self.lock:
            if self.ended is None:  # the timeline shows the run itself, not decisions the teacher makes later
                self.spans.append(span)
            self.agent_state[agent] = "working"
            self._keep_frame()
        try:
            yield
        finally:
            span["end"] = self._t()
            self.agent_state[agent] = "waiting" if before == "working" else before
            self._keep_frame()

    def _log(self, agent):
        return lambda msg: self.emit(agent, "WAIT", msg)

    def _sub(self, sid):
        return next((s for s in self.subs if s["id"] == sid), None)

    def snapshot(self, since=0):
        with self.lock:
            now = time.time()
            return {
                "id": self.id, "status": self.status, "goal": self.goal, "inject_fault": self.inject_fault,
                "agents": self.agent_state, "stats": self.stats, "plan": self.plan, "report": self.report,
                "subs": self.subs, "rubric": self.rubric, "spans": self.spans, "files": self.files,
                "support": self.support, "lesson": self.lesson, "consistency": self.consistency, "outcomes": self.outcomes,
                "scripts": self.intake, "inject_ocr_fault": self.inject_ocr_fault, "assessment": self.assessment,
                "corrections": self.corrections(),
                "review": {k: v for k, v in self.review.items() if k != "materials"},
                "events": self.events[max(0, since):], "next": len(self.events),
                "llm": {"name": self.llm.name, "model": self.llm.model, "calls": self.llm.calls,
                        "served": getattr(self.llm, "served", None), "backup": getattr(self.llm, "standby", None),
                        "switched": bool(getattr(self.llm, "switched", None))},
                "where": self.where,
                "elapsed": round((self.ended or now) - self.started + self._skipped()),
                "t": round(now - self.started + self._skipped(), 1),
            }

    def start(self):
        threading.Thread(target=self._guarded, daemon=True).start()

    def _guarded(self):
        with self.work:
            try:
                self._main()
                self.status = "done"
            except Stopped as e:
                self.emit("PL", "ERROR", f"Run stopped: {e}")
                self.status = "failed"
            except Exception as e:  # surface every failure in the run log
                traceback.print_exc()
                self.emit("PL", "ERROR", f"Run stopped: {e}")
                self.status = "failed"
            finally:
                self.ended = time.time()
                for k, state in self.agent_state.items():  # an agent the goal did not call on stays "off"
                    self.agent_state[k] = "waiting" if self.status != "done" else state if state == "off" else "done"
                self._write_corrections()

    # ---- the teacher checks the materials before planning ------------------
    def materials(self):
        """What the team works from (memo, rubric, every learner's script), as the teacher is shown it."""
        with self.lock:
            if self.review["materials"]:
                return self.review["materials"]
            preview = copy.deepcopy(self.subs)
        return tools.materials(preview, self.rubric, self.pages, self.batch)

    def approve(self, go, note=""):
        """The teacher's answer while the run waits on the materials: go ahead and plan, or stop. False if not waiting."""
        with self.lock:
            if not self.review["waiting"] or self._reviewed.is_set():
                return False
            self.review["choice"] = "plan" if go else "stop"
            self.review["note"] = str(note or "").strip()[:500]
        self._reviewed.set()
        return True

    def _teacher_review(self):
        """Show the teacher what the team will work from and wait for a go-ahead. Planning starts only after it."""
        if not self.review["wanted"]:
            return
        preview = copy.deepcopy(self.subs)
        if not any(s["flags"] for s in preview):
            tools.triage(preview, self.rubric)  # the same checks the run makes, so the teacher sees what they found
        stuff = tools.materials(preview, self.rubric, self.pages, self.batch)
        memo = self.rubric.get("memo")
        empty = sum(1 for s in preview if not s["text"])
        crit = len(self.rubric["criteria"])
        parts = [f"the memo ({memo['file']})" if memo else "no memo (marking from the rubric alone)",
                 f"the rubric ({self.rubric['total']} marks, {crit} criteri{'on' if crit == 1 else 'a'})",
                 f"{len(preview)} learners' {'scripts' if self.noun == 'essay' else self.noun + 's'}"
                 + (f", {empty} with nothing handed in" if empty else "")]
        if self.pages:
            parts.append(_n(len(self.pages), "photographed page"))
        with self.lock:
            self.review.update(materials=stuff, waiting=True)
        self.emit("PL", "WAIT", "Materials loaded: " + ", ".join(parts) + ". Waiting for the teacher to check them before I plan.")
        self._reviewed.wait()
        with self.lock:
            self.review["waiting"] = False
            choice, note = self.review["choice"], self.review["note"]
        if choice != "plan":
            self.emit("PL", "HUMAN", "The teacher stopped the run to change the materials." + (f" Note: {note}" if note else ""))
            raise Stopped("the teacher stopped it before planning, to change the materials")
        self.emit("PL", "HUMAN", "The teacher checked the memo, the rubric and the scripts and said to go ahead."
                  + (f" Note for the team: {note}" if note else ""))
        if note:
            self.goal = f"{self.goal} The teacher added, after checking the materials: {note}"

    def corrections(self):
        """How we corrected ourselves: every time a check stopped work, as a story built from the log."""
        with self.lock:
            return story.corrections(self.events, self.intake, self.support, self.subs)

    def _write_corrections(self):
        """The stories as output/<run>/corrections.md, rewritten whenever the run or a late decision ends."""
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "corrections.md").write_text(story.to_markdown(self.corrections()), encoding="utf-8")
        except OSError:
            traceback.print_exc()

    # ---- the workflow --------------------------------------------------
    def _main(self):
        rubric = self.rubric
        self.subs = tools.load_submissions(self.data_dir)
        if self.assessment == "practical":
            tools.load_attempts(self.data_dir, self.subs, rubric, self.live_attempts)
            tools.triage(self.subs, rubric)
            found = sum(1 for s in self.subs if s["attempt"])
            live = [s["id"] for s in self.subs if s["source"] == "live"]
            self.emit("PL", "INFO", f"Goal received. {rubric['title']} loaded. {_n(found, 'attempt')} in the virtual lab's "
                                    f"logs for {_n(len(self.subs), 'learner')} on the class list."
                                    + (f" Recorded live in the lab today: {', '.join(live)}." if live else ""))
            self._teacher_review()
        elif self.pages:
            self.emit("PL", "INFO", f"Goal received. {rubric['title']} loaded. {_n(len(self.subs), 'learner')} on the class list, "
                                    f"and {_n(len(self.pages), 'photographed page')} of handwritten work.")
            self._teacher_review()
            self._intake()
            tools.triage(self.subs, rubric)
        else:
            tools.triage(self.subs, rubric)
            self.emit("PL", "INFO", f"Goal received. {rubric['title']} loaded. {_n(len(self.subs), 'submission')} found.")
            self._teacher_review()
        for s in self.subs:
            if "instruction_to_marker" in s["flags"]:
                self.emit("PL", "FLAG", "Essay contains text that tries to instruct the marker. It will be marked normally and reported to the teacher.", s["id"])

        with self._busy("PL", "Reading the goal and planning the work"):
            inventory = [{"id": s["id"], "words": s["words"], "flags": s["flags"],
                          **({"source": s["source"]} if self.intake else {})} for s in self.subs]
            raw = agents.plan(self.llm, self.goal, rubric, inventory, self._log("PL"))
        self.plan = self._clean_plan(raw)
        want = self.plan["deliver"]
        for agent, job in (("CO", "support"), ("DS", "lesson")):
            if not want[job]:
                self.agent_state[agent] = "off"
        self.emit("PL", "PLAN", self.plan["understanding"])
        for i, step in enumerate(self.plan["steps"], 1):
            self.emit("PL", "PLAN", f"Step {i}: {step}")
        self._announce_risk()
        self._set_aside()

        todo = [s for s in self.subs if s["status"] == "received"]
        size = self.plan["batch_size"]
        batches = [todo[i:i + size] for i in range(0, len(todo), size)]
        self.emit("PL", "PLAN", f"{_n(len(todo), self.noun)} split into {len(batches)} batch{'' if len(batches) == 1 else 'es'} of up to {size}.")
        for n, batch in enumerate(batches, 1):
            self._mark_batch(n, batch)
        self._consistency_note(batches)

        with self.lock:  # a teacher's decision made after this point gets its own late pass (see resolve)
            self._closing = True
            ready = [s for s in self.subs if s["status"] == "agreed"]
        if want["feedback"]:
            for i in range(0, len(ready), size):
                self._write_feedback(ready[i:i + size])
        if want["support"]:
            self._support(self.subs)
        if want["lesson"]:
            self._lesson()
        if want["support"] and want["lesson"]:
            self._align()  # the Reviewer checks the two colleagues against each other, then either may revise once
        self._deliver(ready)

        st = self.stats
        set_aside = "asked to resubmit" if want["feedback"] else "set aside unmarked"
        done = (f"{_n(st['marked'], self.noun)} marked, {st['sent_back']} sent back, {st['fixed']} corrected, "
                f"{st['escalated']} waiting for the teacher, {st['resubmit']} {set_aside}, "
                f"{_n(st['delivered'], 'feedback message')} delivered.")
        if self.support:
            flagged = self.support["learners"]
            plans = sum(e["status"] == "ready" for e in flagged)
            done += f" {_n(len(flagged), 'learner')} flagged as falling behind, {_n(plans, 'catch-up plan')} ready."
        if self.lesson:
            kept = sum(ex["status"] != "dropped" for ex in self.lesson["exercises"])
            done += (f" Lesson plan ready with {_n(kept, 'checked exercise')}." if self.lesson["status"] == "ready"
                     else " The lesson draft failed its checks and was held back.")
        if self.intake:
            done = self.intake["summary"] + " " + done
        if self.consistency and self.consistency["status"] == "held":
            done += " The catch-up plans and the lesson still disagree, so that part was held for the teacher."
        elif self.consistency and self.consistency["opened"]:
            done += " The Reviewer found a mismatch between the catch-up plans and the lesson, sent it back once, and they now agree."
        elif self.consistency and self.consistency["status"] == "agreed":
            done += " The catch-up plans and the lesson agree."
        self.emit("PL", "DONE", done)

    def _clean_plan(self, raw):
        ids = {s["id"] for s in self.subs}
        deliver = raw.get("deliver") if isinstance(raw.get("deliver"), dict) else {}
        try:
            size = max(2, min(8, int(raw.get("batch_size", 4))))
        except (TypeError, ValueError):
            size = 4
        try:
            minutes = max(20, min(120, int(raw.get("lesson_minutes", 45))))
        except (TypeError, ValueError):
            minutes = 45
        steps = raw.get("steps") if isinstance(raw.get("steps"), list) else []
        exclude = raw.get("exclude") if isinstance(raw.get("exclude"), list) else []
        return {
            "understanding": str(raw.get("understanding") or "Mark the essays and report back."),
            "batch_size": size,
            "exclude": [e for e in exclude if isinstance(e, dict) and e.get("id") in ids],
            # Marking and its paperwork happen unless the goal says otherwise. The Coach and the Designer work only when asked.
            "deliver": {**{k: bool(deliver.get(k, True)) for k in ("feedback", "csv", "report")},
                        **{k: deliver.get(k) is True for k in ("support", "lesson")}},
            "lesson_minutes": minutes,
            "steps": [str(s) for s in steps][:9],
        }

    def _announce_risk(self):
        """The Planner states each high-risk learner and the reason, from the same rules the landing screen uses."""
        try:
            board = risk.assess(self.data_dir, overlay=self.subs, assessment=self.assessment, live_dir=self.live_attempts)
        except Exception:
            traceback.print_exc()
            self.emit("PL", "PLAN", "Risk scores could not be worked out on this run.")
            return
        counts = board["counts"]
        self.emit("PL", "PLAN", (
            f"Risk scores are in for {len(board['learners'])} learners: "
            f"{counts.get('High', 0)} high, {counts.get('Medium', 0)} medium, {counts.get('Low', 0)} low. "
            f"Pass line {board['config']['pass_line']}%."
        ))
        for learner in board["learners"]:
            if learner["band"] != "High":
                continue
            self.emit("PL", "PLAN", f"{learner['learner']}: risk {learner['risk']} ({learner['band']}). {learner.get('theory_pass_note') or learner['reason']}.", learner["id"])

    def _set_aside(self):
        """Apply the Planner's exclusions, inside limits that are enforced in code."""
        min_words = self.rubric.get("min_words", 50)
        reasons = {}
        for ex in self.plan["exclude"]:
            s = self._sub(ex["id"])
            if s["status"] == "escalated":  # a script the Clerk held stays with the teacher
                continue
            if s["words"] >= min_words:  # only work that is too short to judge may be set aside
                self.emit("PL", "GUARD", f"The plan left this {self.noun} out, but at {s['words']} words it is long enough to mark, so it stays in.", s["id"])
            else:
                reasons.setdefault(s["id"], str(ex.get("reason") or "Too short to mark fairly."))
        for s in self.subs:
            if not s["words"] and s["status"] != "escalated":  # there is nothing to mark, whatever the plan says
                reasons.setdefault(s["id"], "Nothing was submitted.")
        self.plan["exclude"] = [{"id": sid, "reason": why} for sid, why in reasons.items()]
        for sid, why in reasons.items():
            s = self._sub(sid)
            s["status"] = "resubmit"
            s["history"].append({"who": "Planner", "what": f"Not marked: {why}"})
            self.stats["resubmit"] += 1
            self.emit("PL", "DECIDE", f"Will not be marked: {why}", sid)

    def _marks(self, agent, essays, blind=False):
        """Ask for marks. If the reply leaves essays out, ask once more for just those."""
        raw = agents.mark(self.llm, self.rubric, essays, self._log(agent), blind_review=blind)
        missing = [e for e in essays if e["id"] not in raw]
        if missing:
            self.emit(agent, "WAIT", f"The reply left out {', '.join(e['id'] for e in missing)}. Asking again for {'it' if len(missing) == 1 else 'those'}.")
            raw.update(agents.mark(self.llm, self.rubric, missing, self._log(agent), blind_review=blind))
        return raw

    def _mark_batch(self, n, batch, label=None):
        rubric = self.rubric
        essays = [{"id": s["id"], "text": s["text"]} for s in batch]  # no names: marking is anonymous
        ids = ", ".join(s["id"] for s in batch)
        label = label or f"Batch {n}"

        with self._busy("MK", f"{label}: marking {ids}"):
            self.emit("MK", "ACT", f"{label}: marking {ids} against the rubric.")
            raw = self._marks("MK", essays)
        problems = {}
        for s in batch:
            s["marker"], problems[s["id"]] = self._clean(raw.get(s["id"]), s)
            s["status"] = "marked"
            s["history"].append({"who": "Marker", "what": f"First mark {s['marker']['total']}/{rubric['total']}."})
            self.emit("MK", "MARK", f"Marked {s['marker']['total']}/{rubric['total']}.", s["id"])

        if self.inject_fault and n == 1:
            self._corrupt_one_mark(batch)

        with self._busy("RV", f"{label}: blind second mark of {ids}"):
            self.emit("RV", "CHECK", f"{label}: second-marking {ids} without seeing the Marker's marks.")
            raw = self._marks("RV", essays, blind=True)
        disputed = []
        for s in batch:
            if s["id"] not in raw:
                self._escalate(s, "The Reviewer returned no second mark, so the Marker's mark has not been checked.")
                continue
            s["reviewer"], _ = self._clean(raw[s["id"]], s)
            diffs = tools.disagreements(rubric, s["marker"], s["reviewer"])
            if s.get("attempt"):  # the Marker's mark as it stands now, held against what the attempt log allows
                problems[s["id"]] = list(dict.fromkeys(problems[s["id"]] + tools.check_practical(s["marker"], rubric, s["attempt"])))
            issues = problems[s["id"]] + [
                f"{d['name']}: you gave {d['marker']}, the Reviewer gave {d['reviewer']} (allowed difference {d['tolerance']})." for d in diffs]
            if issues:
                s["status"], s["rejected"] = "disputed", s["marker"]
                s["history"].append({"who": "Reviewer", "what": "Sent back: " + " ".join(issues)})
                self.stats["sent_back"] += 1
                self.emit("RV", "REJECT", "Sent back to the Marker. " + " ".join(issues), s["id"])
                disputed.append((s, issues))
            else:
                self._agree(s, f"Agrees with the Marker within tolerance ({s['reviewer']['total']} vs {s['marker']['total']}).")
        if disputed:
            self._resolve_disputes(disputed)

    def _corrupt_one_mark(self, batch):
        """Test mode: quietly spoil one of the Marker's marks, to prove the Reviewer catches it unprompted."""
        s = batch[min(1, len(batch) - 1)]
        c = self.rubric["criteria"][0]
        if self.assessment == "practical":  # full marks for build order to someone whose log shows parts out of order
            s = next((x for x in batch if x.get("attempt") and x["attempt"]["wrong"]), s)
        mark = copy.deepcopy(s["marker"])
        cur = mark["scores"][c["id"]]["score"]
        shift = max(1, round(c["max"] * 0.45))
        wrong = cur - shift if cur >= c["max"] / 2 else cur + shift
        if self.assessment == "practical" and cur < c["max"]:
            wrong = c["max"]
        mark["scores"][c["id"]]["score"] = wrong
        mark["total"] += wrong - cur
        s["marker"] = mark
        s["history"].append({"who": "Test", "what": f"Fault injected: {c['name']} changed from {cur} to {wrong}."})
        self.emit("PL", "TEST", f"Fault injection is on: {c['name']} mark deliberately changed from {cur} to {wrong}. Nobody told the Reviewer.", s["id"])

    def _agree(self, s, why):
        s["final"], s["status"] = s["marker"], "agreed"
        s["history"].append({"who": "Reviewer", "what": f"Approved {s['final']['total']}/{self.rubric['total']}. {why}"})
        self.stats["marked"] += 1
        self.emit("RV", "APPROVE", why, s["id"])

    def _resolve_disputes(self, disputed):
        rubric = self.rubric
        cases = [{"id": s["id"], "text": s["text"], "your_mark": s["marker"], "problems": issues, "reviewer_mark": s["reviewer"]}
                 for s, issues in disputed]
        ids = ", ".join(c["id"] for c in cases)
        with self._busy("MK", f"Re-marking {ids} after the Reviewer's objections"):
            self.emit("MK", "FIX", f"Re-marking {ids} with the Reviewer's objections.")
            raw = agents.remark(self.llm, rubric, cases, self._log("MK"))
        to_verify = []
        for s, _ in disputed:
            before, reply = s["marker"], raw.get(s["id"])
            if reply is None:
                self._escalate(s, "The Marker returned no revised mark.")
                continue
            s["marker"], problems = self._clean(reply, s)
            note = str(reply.get("note") or "").strip()
            changed = any(s["marker"]["scores"][c["id"]]["score"] != before["scores"][c["id"]]["score"] for c in rubric["criteria"])
            did = f"Corrected the mark: {before['total']} → {s['marker']['total']}." if changed else f"Kept the mark at {before['total']}."
            s["history"].append({"who": "Marker", "what": f"{did} {note}".strip()})
            self.emit("MK", "FIX", f"{did} {note}".strip(), s["id"])
            diffs = tools.disagreements(rubric, s["marker"], s["reviewer"])
            if problems:
                self._escalate(s, "The mark still fails checks after one correction: " + " ".join(problems))
            elif not diffs:
                self.stats["fixed"] += 1
                self._agree(s, (f"Corrected mark {s['marker']['total']} now agrees with the second mark {s['reviewer']['total']}." if changed else
                                f"The mark {s['marker']['total']} now passes the checks and agrees with the second mark {s['reviewer']['total']}."))
            else:
                to_verify.append({"id": s["id"], "text": s["text"], "marker_mark": s["marker"], "note": note,
                                  "reviewer_mark": s["reviewer"], "differences": diffs})
        if not to_verify:
            return
        ids = ", ".join(c["id"] for c in to_verify)
        with self._busy("RV", f"Ruling on the Marker's defence of {ids}"):
            self.emit("RV", "CHECK", f"Ruling on defended marks: {ids}.")
            verdicts = agents.verify(self.llm, rubric, to_verify, self._log("RV"))
        for c in to_verify:
            s, v = self._sub(c["id"]), verdicts.get(c["id"]) or {}
            reason = str(v.get("reason") or "").strip()
            if v.get("approve") is True:
                self._agree(s, f"Accepts the Marker's defence. {reason}".strip())
            else:
                self._escalate(s, f"Marker and Reviewer still disagree. {reason}".strip())

    def _escalate(self, s, why):
        s["status"], s["issue"] = "escalated", why
        s["history"].append({"who": "Reviewer", "what": f"Escalated to the teacher. {why}"})
        self.stats["escalated"] += 1
        marks = f"Marker {s['marker']['total']}" + (f", Reviewer {s['reviewer']['total']}" if s["reviewer"] else "")
        self.emit("RV", "ESCALATE", f"Needs the teacher's decision ({marks}). {why}", s["id"])

    def _consistency_note(self, batches):
        """Compare batch averages so drift between batches is visible."""
        means = []
        for b in batches:
            totals = [s["final"]["total"] for s in b if s["final"]]
            if totals:
                means.append(round(sum(totals) / len(totals), 1))
        if len(means) > 1:
            spread = round(max(means) - min(means), 1)
            self.emit("RV", "CHECK", f"Consistency across batches: averages {', '.join(str(m) for m in means)}; spread {spread} marks.")

    def _write_feedback(self, batch):
        rubric = self.rubric
        if not batch:
            return

        def item(s):
            return {"id": s["id"], "first_name": s["learner"].split()[0], "total": s["final"]["total"], "max": rubric["total"],
                    "scores": [{"name": c["name"], "max": c["max"], **s["final"]["scores"][c["id"]]} for c in rubric["criteria"]]}

        ids = ", ".join(s["id"] for s in batch)
        with self._busy("MS", f"Writing feedback for {ids}"):
            self.emit("MS", "ACT", f"Writing feedback for {ids}.")
            pending, notes = batch, None
            for attempt in (1, 2):
                raw = agents.feedback(self.llm, rubric, [item(s) for s in pending], self._log("MS"), notes)
                failed, notes = [], {}
                for s in pending:
                    msg = raw.get(s["id"])
                    bad = tools.check_feedback(msg, s, self.subs, rubric)
                    if not bad:
                        s["feedback"] = {"subject": str(msg.get("subject") or f"Your {self.noun} feedback").strip(), "body": str(msg["body"]).strip()}
                        continue
                    failed.append(s)
                    notes[s["id"]] = bad
                    if attempt == 1:
                        self.stats["feedback_redone"] += 1
                        s["history"].append({"who": "Reviewer", "what": "Feedback draft rejected: it " + "; ".join(bad) + "."})
                        self.emit("RV", "REJECT", "Feedback draft rejected: it " + "; ".join(bad) + ". Sent back to the Messenger.", s["id"])
                pending = failed
                if not pending:
                    break
            for s in pending:  # still failing after a retry: hold it rather than send something wrong
                s["status"] = "escalated"
                s["issue"] = "The feedback message failed its checks twice (it " + "; ".join(notes[s["id"]]) + "), so nothing was sent."
                s["history"].append({"who": "Reviewer", "what": "Feedback held for the teacher after failing checks twice."})
                self.stats["escalated"] += 1
                self.stats["marked"] -= 1
                self.emit("RV", "ESCALATE", "Feedback failed checks twice. Held for the teacher instead of being sent.", s["id"])

    # ---- learners falling behind (the Coach) ------------------------------
    def _support(self, subs):
        """Spot which of these learners are falling behind, then have the Coach work out why and plan a week of catch-up.

        Who is flagged is decided by fixed rules in code, never by a model. A plan that fails its checks goes
        back to the Coach once; if it fails again no plan is offered and the teacher is told why.
        """
        rubric = self.rubric
        found = []
        for s in subs:
            signs = tools.support_signs(s, rubric)
            if not signs:
                continue
            final = s["final"]
            found.append({
                "id": s["id"], "learner": s["learner"], "signs": signs,
                "now": round(100 * final["total"] / rubric["total"]) if final else None, "previous": s["previous"],
                "weakest": tools.weakest_criterion(final, rubric) if final else None,
                "status": "working", "plan": None, "problems": [],
            })
        can_check = lambda s: bool(s["final"]) or s["status"] == "resubmit"  # otherwise the mark is still with the teacher
        waiting = sum(1 for s in self.subs if not can_check(s))
        place = {s["id"]: i for i, s in enumerate(self.subs)}
        with self.lock:
            again = {s["id"] for s in subs}
            kept = [e for e in (self.support or {}).get("learners", []) if e["id"] not in again]
            self.support = {"checked": len(self.subs) - waiting, "waiting": waiting, "rules": tools.support_rules(rubric),
                            "learners": sorted(kept + found, key=lambda e: place[e["id"]])}
        note = f" {_n(waiting, self.noun)} still waiting for the teacher, so not checked yet." if waiting else ""
        self.emit("CO", "CHECK", f"Checked {_n(sum(map(can_check, subs)), 'learner')} against the warning signs: {len(found)} flagged.{note}")
        if not found:
            if "support_plans.md" in self.files:  # a learner who was flagged earlier no longer is
                tools.write_support_plans(self.out_dir, self.support["learners"], self.outcomes, **self._evidence())
            return
        for e in found:
            what = "; ".join(sign["text"] for sign in e["signs"])
            self._sub(e["id"])["history"].append({"who": "Coach", "what": f"Flagged as falling behind: {what}."})
            self.emit("CO", "FLAG", f"Falling behind: {what}.", e["id"])

        def case(e):
            s = self._sub(e["id"])
            final = s["final"]
            return {
                "id": e["id"], "first_name": s["learner"].split()[0], "signs": [sign["text"] for sign in e["signs"]],
                "now": f"{final['total']}/{rubric['total']} ({e['now']}%)" if final else "not marked",
                "previous": "not recorded" if s["previous"] is None else f"{round(s['previous'])}%",
                "weakest": f"{e['weakest']['name']} ({e['weakest']['pct']}%)" if e["weakest"] else "not known",
                "scores": [{"id": c["id"], "name": c["name"], "max": c["max"], "score": final["scores"][c["id"]]["score"],
                            "reason": final["scores"][c["id"]]["reason"]} for c in rubric["criteria"]] if final else [],
                "text": s["text"],
            }

        ids, size = ", ".join(e["id"] for e in found), self.plan["batch_size"]
        task = f"Working out why {ids} {'is' if len(found) == 1 else 'are'} behind"
        with self._busy("CO", task):
            self.emit("CO", "ACT", f"{task} and planning a week of catch-up.")
            pending, notes = found, None
            for attempt in (1, 2):
                raw = {}
                for i in range(0, len(pending), size):
                    group = pending[i:i + size]
                    fix = {e["id"]: notes[e["id"]] for e in group} if notes else None
                    raw.update(agents.support(self.llm, rubric, self.outcomes, [case(e) for e in group], self._log("CO"), fix))
                failed, notes = [], {}
                for e in pending:
                    s = self._sub(e["id"])
                    plan = tools.clean_support_plan(raw.get(e["id"]))
                    bad = tools.check_support_plan(plan, s, self.subs, rubric, self.outcomes)
                    if not bad:
                        e["plan"], e["status"] = plan, "ready"
                        on = ", ".join(st["outcome"] for st in plan["steps"])
                        s["history"].append({"who": "Coach", "what": f"Catch-up plan written: three steps on outcomes {on}."})
                        self.emit("CO", "INFO", f"Catch-up plan passes its checks: three steps on outcomes {on}.", e["id"])
                        continue
                    failed.append(e)
                    notes[e["id"]] = bad
                    if attempt == 1:
                        s["history"].append({"who": "Reviewer", "what": "Catch-up plan rejected: it " + "; ".join(bad) + "."})
                        self.emit("RV", "REJECT", "Catch-up plan rejected: it " + "; ".join(bad) + ". Sent back to the Coach.", e["id"])
                pending = failed
                if not pending:
                    break
            for e in pending:  # still failing after a retry: offer no plan rather than a wrong one
                e["status"], e["problems"] = "held", notes[e["id"]]
                self._sub(e["id"])["history"].append({"who": "Reviewer", "what": "Catch-up plan held back after failing its checks twice."})
                self.emit("RV", "ESCALATE", "Catch-up plan failed its checks twice. No plan is offered: the warning signs go to the teacher as they are.", e["id"])
            ready = sum(e["status"] == "ready" for e in self.support["learners"])
            if self.plan["deliver"]["lesson"]:  # written once the Reviewer has compared the two, in case a plan is sent back
                self.emit("CO", "INFO", f"{_n(ready, 'catch-up plan')} passed its own checks. The Reviewer will compare them with the lesson next.")
            else:
                self._publish_support()

    # ---- the next lesson (the Designer) -----------------------------------
    def _lesson(self):
        """Have the Designer draft a lesson on the class's weakest area, then check it the way marks are checked.

        Code checks the structure and sends a draft that fails back once. The Reviewer then tries every
        exercise without seeing which outcome it is labelled with, or its answer. An exercise the Reviewer
        cannot do, or reads as practising something else, goes back to the Designer once and is dropped if
        it fails again. A lesson that does not stand on what is left is held back, not written.
        """
        rubric, outcomes, minutes = self.rubric, self.outcomes, self.plan["lesson_minutes"]
        done = self._settled()
        self.lesson = {**tools.clean_lesson({}, minutes), "status": "drafting", "target": None, "problems": []}
        if not done:
            return self._hold_lesson(self.lesson, ["has no settled marks to aim at"])
        averages = self._criteria_avg(done)
        low = min(averages, key=lambda c: c["avg_pct"])
        weakest = {"id": low["id"], "name": low["name"], "pct": low["avg_pct"]}
        self.lesson["target"] = weakest
        flagged = (self.support or {}).get("learners", [])
        areas = [e["weakest"]["name"] if e["weakest"] else None for e in flagged]
        brief = {  # class-level figures only: the Designer is told nothing about any one learner
            "minutes": minutes, "weakest": weakest, "criteria_avg": averages, "marked": len(done), "flagged": len(flagged),
            "causes": [f"{_n(areas.count(a), 'flagged learner')} " + (f"weakest in {a}" if a else "handed in too little to mark")
                       for a in dict.fromkeys(areas)],
        }

        def draft(notes=None):
            lesson = tools.clean_lesson(agents.lesson(self.llm, rubric, outcomes, brief, self._log("DS"), notes), minutes)
            ids = [ex["id"] for ex in lesson["exercises"]]
            if len(set(ids)) < len(ids):  # a rewrite has to be matched to the exercise it replaces
                for n, ex in enumerate(lesson["exercises"], 1):
                    ex["id"] = f"X{n}"
            lesson.update(status="checking", target=weakest, problems=[])
            return (lesson, *tools.check_lesson(lesson, outcomes, weakest, minutes))

        with self._busy("DS", f"Drafting a {minutes}-minute lesson on {weakest['name'].lower()}"):
            self.emit("DS", "ACT", f"Drafting a {minutes}-minute lesson for the class's weakest area: {weakest['name']} ({weakest['pct']}%).")
            lesson, problems, per = draft()
            if problems:
                self.emit("RV", "REJECT", "Lesson draft rejected: it " + "; ".join(problems) + ". Sent back to the Designer.")
                lesson, problems, per = draft(problems + [f"exercise {k}: " + "; ".join(v) for k, v in per.items()])
        if problems:
            return self._hold_lesson(lesson, problems)
        exercises = lesson["exercises"]
        with self.lock:
            self.lesson = lesson
        self.emit("DS", "INFO", f"Draft passes its structure checks: “{lesson['title']}”, {_n(len(exercises), 'exercise')} "
                                f"on {'outcome' if len(lesson['outcomes']) == 1 else 'outcomes'} {', '.join(lesson['outcomes'])}.")
        if self.inject_fault:
            self._corrupt_one_exercise(lesson)

        ids = ", ".join(ex["id"] for ex in exercises)
        with self._busy("RV", f"Trying exercises {ids} blind"):
            self.emit("RV", "CHECK", f"Trying {ids} without seeing which outcome each is labelled with, or its answer.")
            tried = self._try_blind(exercises)
        failing = []
        for ex in exercises:
            ex["check"], blind = tried[ex["id"]]
            ex["problems"] = per.get(ex["id"], []) + blind
            if ex["problems"]:
                failing.append(ex)
                self.emit("RV", "REJECT", f"Exercise {ex['id']} sent back to the Designer: " + "; ".join(ex["problems"]) + ".")
            else:
                ex["status"] = "ok"
                self.emit("RV", "APPROVE", f"Exercise {ex['id']} holds up: done blind, and read as practising {ex['outcome']}, as labelled.")
        if failing:
            self._fix_exercises(lesson, failing)

        used = {ex["outcome"] for ex in exercises if ex["status"] != "dropped"}
        unused = [x for x in lesson["outcomes"] if x not in used]
        if unused and used:  # the lesson may only claim outcomes that a checked exercise practises
            lesson["outcomes"] = [x for x in lesson["outcomes"] if x in used]
            self.emit("RV", "GUARD", f"{', '.join(unused)} taken off the lesson's outcomes: no exercise that passed its checks practises {'it' if len(unused) == 1 else 'them'}.")
        problems, _ = tools.check_lesson(lesson, outcomes, weakest, minutes)
        if problems:
            return self._hold_lesson(lesson, problems)
        lesson["status"] = "ready"
        kept = sum(ex["status"] != "dropped" for ex in exercises)
        if self.plan["deliver"]["support"]:  # written once the Reviewer has compared the two, in case the support work is sent back
            self.emit("DS", "INFO", f"Lesson draft passed its checks ({_n(kept, 'exercise')}). The Reviewer will compare it with the catch-up plans next.")
        else:
            self._publish_lesson()

    def _hold_lesson(self, lesson, problems):
        with self.lock:
            lesson["status"], lesson["problems"] = "held", problems
            self.lesson = lesson
        self.emit("RV", "ESCALATE", "The lesson does not stand: it " + "; ".join(problems) + ". Held back, so no lesson plan was written.")

    def _try_blind(self, exercises):
        """The Reviewer tries exercises seeing only the task. Returns {exercise id: (what it made of it, problems)}."""
        tasks = [{"id": ex["id"], "task": ex["task"]} for ex in exercises]  # no label, no level, no answer
        raw = agents.try_exercises(self.llm, self.outcomes, tasks, self._log("RV"))
        missing = [t for t in tasks if t["id"] not in raw]
        if missing:
            self.emit("RV", "WAIT", f"The reply left out {', '.join(t['id'] for t in missing)}. Asking again for {'it' if len(missing) == 1 else 'those'}.")
            raw.update(agents.try_exercises(self.llm, self.outcomes, missing, self._log("RV")))
        return {ex["id"]: tools.blind_check(ex, raw.get(ex["id"]), self.outcomes) for ex in exercises}

    def _fix_exercises(self, lesson, failing):
        """One rework by the Designer, then the Reviewer tries the result blind again. What still fails is dropped."""
        ids = ", ".join(ex["id"] for ex in failing)
        with self._busy("DS", f"Reworking {ids} after the Reviewer's objections"):
            self.emit("DS", "FIX", f"Reworking {ids} with the Reviewer's objections.")
            cases = [{k: ex[k] for k in ("id", "level", "task", "answer", "outcome", "problems")} for ex in failing]
            raw = agents.fix_exercises(self.llm, self.outcomes, lesson["outcomes"], cases, self._log("DS"))
        reworked = []
        for ex in failing:
            if ex["id"] not in raw:
                self._drop(ex, ["the Designer returned no new version"])
                continue
            new = tools.clean_exercise(raw[ex["id"]], ex["id"])
            did = "rewritten" if new["task"] != ex["task"] else \
                f"relabelled from {ex['outcome']} to {new['outcome']}" if new["outcome"] != ex["outcome"] else "returned unchanged"
            ex.update(outcome=new["outcome"], task=new["task"], answer=new["answer"],
                      level=ex["level"] if ex["level"] in tools.EXERCISE_LEVELS else new["level"])
            self.emit("DS", "FIX", f"Exercise {ex['id']} {did}.")
            reworked.append(ex)
        if not reworked:
            return
        ids = ", ".join(ex["id"] for ex in reworked)
        with self._busy("RV", f"Trying the reworked {ids} blind"):
            self.emit("RV", "CHECK", f"Trying the reworked {ids} blind.")
            tried = self._try_blind(reworked)
        for ex in reworked:
            ex["check"], blind = tried[ex["id"]]
            still = tools.check_exercise(ex, lesson["outcomes"]) + blind
            if still:
                self._drop(ex, still)
            else:
                ex["status"] = "fixed"  # its problems stay on record: they are why it was sent back
                self.emit("RV", "APPROVE", f"Exercise {ex['id']} now holds up: read blind as practising {ex['outcome']}, as labelled.")

    def _drop(self, ex, problems):
        ex["status"], ex["problems"] = "dropped", problems
        self.emit("RV", "DROP", f"Exercise {ex['id']} still fails after one rework ({'; '.join(problems)}). Dropped from the lesson.")

    def _corrupt_one_exercise(self, lesson):
        """Test mode: quietly put the wrong outcome on one exercise, to prove that trying it blind catches the label."""
        exercises = lesson["exercises"]
        ex = exercises[min(1, len(exercises) - 1)]
        right = ex["outcome"]
        others = [x for x in lesson["outcomes"] if x != right] or [o["id"] for o in self.outcomes if o["id"] != right]
        if not others:
            return
        ex["outcome"] = others[0]
        self.emit("PL", "TEST", f"Fault injection is on: exercise {ex['id']} deliberately relabelled from {right} to {others[0]}. Nobody told the Reviewer.")

    # ---- do the Coach and the Designer agree? --------------------------------
    def _align(self):
        """After both have finished, check the catch-up plans against the lesson and send a mismatch back once.

        The lesson's support exercises must cover every weakness the Coach diagnosed. Every catch-up step must map
        to a lesson outcome, an exercise, or an outcome on the list. The colleague who owns a mismatch revises it
        once. What is still inconsistent is held, and the teacher is told, the same way a mark that still fails is.
        """
        if not (self.plan["deliver"]["support"] and self.plan["deliver"]["lesson"]) or not self.support or not self.lesson:
            return
        if self.lesson.get("status") != "ready":
            if not self.consistency:  # a lesson already held for its own checks is not compared; a later pass must not wipe that record
                self.consistency = {
                    "status": "skipped", "opened": [], "coverage": [], "steps": [], "problems": list(self.lesson.get("problems") or []),
                    "summary": "The lesson was not ready, so it was not compared with the catch-up plans.",
                }
            self._publish_support()
            return
        report = tools.consistency_issues(self.support["learners"], self.lesson, self.outcomes, self.rubric)
        if self.consistency and self.consistency.get("status") == "agreed" and not report["lesson"] and not report["plans"]:
            self.consistency = {**self.consistency, "coverage": report["coverage"], "steps": report["steps"], "problems": []}
            self.consistency["summary"] = self._consistency_summary()
            self._publish_support()
            return
        if self.consistency and self.consistency.get("status") == "held" and not report["lesson"] and not report["plans"]:
            self._publish_support()  # a plan already held stays held; a later pass must not quietly clear it
            if self.lesson.get("status") == "ready":
                self._publish_lesson()
            return
        opened = list((self.consistency or {}).get("opened") or [])
        with self._busy("RV", "Checking the catch-up plans against the lesson"):
            self.emit("RV", "CHECK", "Checking that the catch-up plans and the lesson agree: support work against the weaknesses "
                                      "the Coach diagnosed, and every step against the lesson, its exercises and the outcomes list.")
            self._set_consistency("checking", report, opened)
        if report["lesson"] and not self._lesson_revised:
            self.emit("RV", "REJECT", "Sent back to the Designer: the lesson " + "; ".join(report["lesson"]) + ".")
            opened.append({"agent": "DS", "text": "The lesson " + "; ".join(report["lesson"]) + "."})
            self._set_consistency("checking", report, opened)
            self._revise_lesson(report)
            self._lesson_revised = True
        pending = [e for e in self.support["learners"] if e["id"] in report["plans"] and e["id"] not in self._plans_revised]
        if pending:
            for entry in pending:
                problems = report["plans"][entry["id"]]
                self._sub(entry["id"])["history"].append({"who": "Reviewer", "what": "Catch-up plan sent back: " + "; ".join(problems) + "."})
                self.emit("RV", "REJECT", "Catch-up plan sent back to the Coach: " + "; ".join(problems) + ".", entry["id"])
                opened.append({"agent": "CO", "text": f"{entry['id']}: " + "; ".join(problems) + "."})
            self._set_consistency("checking", report, opened)
            self._revise_plans(pending, report)
            self._plans_revised.update(e["id"] for e in pending)
        report = tools.consistency_issues(self.support["learners"], self.lesson, self.outcomes, self.rubric)
        problems = list(report["lesson"])
        for sid, items in report["plans"].items():
            problems += [f"{sid}: {item}" for item in items]
        if report["lesson"] or report["plans"]:
            self._hold_inconsistent(report)
            self._set_consistency("held", report, opened, problems)
            self.emit("RV", "ESCALATE", "The catch-up plans and the lesson still disagree after one revision ("
                                        + "; ".join(problems) + "). Held for the teacher.")
        else:
            self.lesson["status"] = "ready"
            self._set_consistency("agreed", report, opened)
            self._emit_agreement(report)
            self.emit("RV", "APPROVE", "The catch-up plans and the lesson agree." if not opened else
                      "The catch-up plans and the lesson now agree, after one revision.")
        self._publish_support()
        self._publish_lesson()

    def _set_consistency(self, status, report, opened, problems=None):
        self.consistency = {
            "status": status, "opened": opened, "coverage": report["coverage"], "steps": report["steps"],
            "problems": report["lesson"] if problems is None else problems, "summary": "",
        }
        self.consistency["summary"] = self._consistency_summary()

    def _consistency_summary(self):
        """One paragraph for the teacher, from the check's final state."""
        state = self.consistency
        covered = [f"{c['name']} ({c['exercise']})" for c in state["coverage"] if c["exercise"]]
        gaps = [f"{c['name']} ({', '.join(c['learners'])})" for c in state["coverage"] if not c["exercise"]]
        counts = {}
        for step in state["steps"]:
            counts[step["where"]] = counts.get(step["where"], 0) + 1
        mapping = [f"{counts[key]} to {word}" for key, word in
                   (("lesson", "this lesson"), ("exercise", "an exercise"), ("outcomes", "the outcomes list")) if counts.get(key)]
        cover = ("Support exercises cover " + ", ".join(covered) + "." if covered
                 else "No weakness was diagnosed, so there was no support work to match.")
        mapped = ("Every catch-up step maps (" + ", ".join(mapping) + ")." if mapping else "There were no catch-up steps to map.")
        if state["status"] == "skipped":
            return state["summary"]
        if state["status"] == "held":
            bits = []
            if gaps:
                bits.append("no support exercise for " + " or ".join(gaps))
            unmapped = [f"{s['id']} step {s['n']}" for s in state["steps"] if s["where"] == "none"]
            if unmapped:
                bits.append("steps that map to nothing (" + ", ".join(unmapped) + ")")
            return "Still inconsistent after one revision, so it was held for the teacher: " + "; ".join(bits or ["the revision did not resolve it"]) + "."
        if state["status"] == "checking":
            return "The Reviewer is comparing the catch-up plans with the lesson."
        lead = ""
        if state["opened"]:
            who = " and ".join(name for name, agent in (("the Designer", "DS"), ("the Coach", "CO")) if any(item["agent"] == agent for item in state["opened"]))
            lead = "They did not agree at first. " + " ".join(item["text"] for item in state["opened"]) + f" Sent back to {who} once. "
        else:
            lead = "The catch-up plans and the lesson agree. "
        return lead + cover + " " + mapped

    def _emit_agreement(self, report):
        covered = [f"{c['name']} via {c['exercise']} ({c['outcome']})" for c in report["coverage"] if c["exercise"]]
        if covered:
            self.emit("RV", "CHECK", "Support exercises cover " + "; ".join(covered) + ".")
        counts = {}
        for step in report["steps"]:
            counts[step["where"]] = counts.get(step["where"], 0) + 1
        words = {"lesson": "this lesson", "exercise": "an exercise", "outcomes": "the outcomes list"}
        parts = [f"{counts[key]} to {words[key]}" for key in ("lesson", "exercise", "outcomes") if counts.get(key)]
        if parts:
            self.emit("RV", "CHECK", "Every catch-up step maps: " + ", ".join(parts) + ".")

    def _lesson_payload(self, lesson):
        return {
            "title": lesson["title"], "why": lesson["why"], "minutes": lesson["minutes"], "outcomes": list(lesson["outcomes"]),
            "phases": lesson["phases"], "exit_ticket": lesson["exit_ticket"], "target": lesson.get("target"),
            "exercises": [{"id": ex["id"], "outcome": ex["outcome"], "level": ex["level"], "task": ex["task"], "answer": ex["answer"]}
                          for ex in lesson["exercises"] if ex["status"] != "dropped"],
        }

    def _revise_lesson(self, report):
        """One revision by the Designer. A revision that does not itself pass the lesson checks is discarded."""
        previous = copy.deepcopy(self.lesson)
        missing = [{"id": c["id"], "name": c["name"], "learners": c["learners"]} for c in report["coverage"] if not c["exercise"]]
        with self._busy("DS", "Revising the lesson so its support work matches the Coach"):
            self.emit("DS", "FIX", "Revising the support work so it covers " + ", ".join(item["name"] for item in missing) + ".")
            raw = agents.align_lesson(self.llm, self.rubric, self.outcomes, self._lesson_payload(previous), missing, self._log("DS"))
        candidate = self._merge_lesson(previous, raw)
        fresh = [ex for ex in candidate["exercises"] if ex["status"] == "unchecked"]
        problems, per = tools.check_lesson(candidate, self.outcomes, candidate["target"], candidate["minutes"])
        broken = problems + [f"{eid}: " + "; ".join(items) for eid, items in per.items() if eid in {ex["id"] for ex in fresh}]
        if broken:
            self.emit("DS", "FIX", "The revision does not pass the lesson checks (" + "; ".join(broken) + "), so the previous draft stands.")
            return
        if fresh:
            ids = ", ".join(ex["id"] for ex in fresh)
            with self._busy("RV", f"Trying the revised exercises {ids} blind"):
                self.emit("RV", "CHECK", f"Trying the revised {ids} without seeing which outcome each is labelled with, or its answer.")
                tried = self._try_blind(fresh)
            failed = []
            for ex in fresh:
                ex["check"], blind = tried[ex["id"]]
                bad = tools.check_exercise(ex, candidate["outcomes"]) + blind
                if bad:
                    failed.append(f"{ex['id']}: " + "; ".join(bad))
                else:
                    ex["status"] = "ok"
            if failed:
                self.emit("RV", "REJECT", "The revised support work did not hold up (" + "; ".join(failed) + "). The previous lesson stands.")
                return
        with self.lock:
            self.lesson = candidate
        added = [ex["id"] for ex in candidate["exercises"] if ex["id"] not in {e["id"] for e in previous["exercises"]}]
        self.emit("DS", "FIX", ("Added " + ", ".join(added) + " so the support work covers the Coach's diagnoses.") if added
                  else "Returned a revised lesson for the Reviewer to check again.")

    def _merge_lesson(self, previous, raw):
        """The Designer's revision, with check results kept for every exercise that did not change."""
        merged = tools.clean_lesson(raw, previous["minutes"])
        if len({ex["id"] for ex in merged["exercises"]}) < len(merged["exercises"]):
            for n, ex in enumerate(merged["exercises"], 1):
                ex["id"] = f"X{n}"
        old = {ex["id"]: ex for ex in previous["exercises"]}
        exercises, seen = [], set()
        for ex in merged["exercises"]:
            prev = old.get(ex["id"])
            same = prev and prev["task"] == ex["task"] and prev["outcome"] == ex["outcome"] and prev["level"] == ex["level"]
            exercises.append(copy.deepcopy(prev) if same else ex)
            seen.add(ex["id"])
        for ex in previous["exercises"]:  # a dropped exercise stays on the record even if the revision omitted it
            if ex["status"] == "dropped" and ex["id"] not in seen:
                exercises.append(copy.deepcopy(ex))
        merged["exercises"] = exercises
        merged["target"] = previous.get("target")
        merged["status"] = "checking"
        return merged

    def _revise_plans(self, pending, report):
        kept = [ex for ex in self.lesson["exercises"] if ex["status"] != "dropped"]
        lesson_outcomes = list(self.lesson["outcomes"])
        exercise_outcomes = list({ex["outcome"] for ex in kept})

        def case(entry):
            plan = entry["plan"]
            return {"id": entry["id"], "weakest": (entry.get("weakest") or {}).get("id"),
                    "problems": report["plans"][entry["id"]],
                    "plan": {"why": plan["why"], "evidence": plan["evidence"], "strength": plan["strength"],
                             "steps": plan["steps"], "check": plan["check"]}}

        ids = ", ".join(e["id"] for e in pending)
        with self._busy("CO", f"Revising catch-up steps for {ids} so each one maps"):
            self.emit("CO", "FIX", f"Revising the catch-up steps for {ids} so each one maps to the lesson, an exercise, or an outcome on the list.")
            raw = agents.align_support(self.llm, self.rubric, self.outcomes, [case(e) for e in pending],
                                       lesson_outcomes, exercise_outcomes, self._log("CO"))
        for entry in pending:
            sub = self._sub(entry["id"])
            plan = tools.clean_support_plan(raw.get(entry["id"]))
            bad = tools.check_support_plan(plan, sub, self.subs, self.rubric, self.outcomes)
            if bad:
                self.emit("CO", "FIX", "The revised plan still fails its checks (" + "; ".join(bad) + "), so it is not used.", entry["id"])
                continue
            entry["plan"] = plan
            on = ", ".join(step["outcome"] for step in plan["steps"])
            sub["history"].append({"who": "Coach", "what": f"Catch-up steps revised so they map: {on}."})
            self.emit("CO", "FIX", f"Catch-up steps now name {on}.", entry["id"])

    def _hold_inconsistent(self, report):
        if report["lesson"]:
            with self.lock:
                self.lesson["status"] = "held"
                self.lesson["problems"] = list(report["lesson"])
        for sid, problems in report["plans"].items():
            entry = next(e for e in self.support["learners"] if e["id"] == sid)
            entry["status"], entry["problems"] = "held", list(problems)
            self._sub(sid)["history"].append({"who": "Reviewer", "what": "Catch-up plan held back: it still does not match the lesson or the outcomes list."})

    def _publish_support(self):
        if not self.support or (not self.support["learners"] and "support_plans.md" not in self.files):
            return
        tools.write_support_plans(self.out_dir, self.support["learners"], self.outcomes, **self._evidence())
        again = "support_plans.md" in self.files
        self._record_file("support_plans.md")
        ready = sum(e["status"] == "ready" for e in self.support["learners"])
        verb = "updated in" if again else "written to"
        self.emit("CO", "SEND", f"{_n(ready, 'catch-up plan')} {verb} {self.where}/support_plans.md.")

    def _publish_lesson(self):
        if not self.lesson or self.lesson.get("status") != "ready":
            self._unpublish("lesson_plan.md")
            return
        tools.write_lesson_plan(self.out_dir, self.lesson, self.outcomes)
        again = "lesson_plan.md" in self.files
        self._record_file("lesson_plan.md")
        exercises = self.lesson["exercises"]
        count = lambda status: sum(ex["status"] == status for ex in exercises)
        detail = "".join(f", {count(status)} {word}" for status, word in (("fixed", "reworked"), ("dropped", "dropped")) if count(status))
        verb = "updated in" if again else "written to"
        self.emit("DS", "SEND", f"Lesson plan {verb} {self.where}/lesson_plan.md: "
                                f"{_n(len(exercises) - count('dropped'), 'checked exercise')}{detail}.")

    def _unpublish(self, name):
        if name in self.files:
            self.files.remove(name)
        path = self.out_dir / name
        if path.is_file():
            path.unlink()

    def _send(self, s):
        """Save a learner's message to the outbox, and email it when SMTP is set up. True if it really left."""
        fb = s["feedback"]
        tools.write_email(self.out_dir, s, fb["subject"], fb["body"])
        try:
            return bool(tools.send_email(s, fb["subject"], fb["body"]))
        except Exception as e:  # a mail server problem must not lose the rest of the run
            self.emit("MS", "ERROR", f"Email could not be sent ({e}). The message is saved in the outbox.", s["id"])
            return False

    def _deliver(self, ready):
        rubric, want = self.rubric, self.plan["deliver"]
        with self._busy("MS", "Delivering the results"):
            sent = asked = emailed = 0
            for s in ready:
                if s["status"] != "agreed" or not s["feedback"]:
                    continue
                emailed += self._send(s)
                s["status"] = "delivered"
                s["history"].append({"who": "Messenger", "what": "Feedback delivered."})
                self.stats["delivered"] += 1
                sent += 1
            if want["feedback"]:
                for s in self.subs:
                    if s["status"] == "resubmit" and not s["feedback"]:
                        first = s["learner"].split()[0]
                        what = (f"what I received is incomplete ({_n(s['words'], 'word')})" if s["words"] else "I have not received it")
                        s["feedback"] = self._resubmit_message(s, first, what)
                        emailed += self._send(s)
                        s["history"].append({"who": "Messenger", "what": "Asked to resubmit."})
                        asked += 1
                what = " and ".join(_n(count, noun) for count, noun in ((sent, "feedback message"), (asked, "resubmission request")) if count)
                where = f"sent by email ({emailed})" if emailed else f"saved to {self.where}/outbox (email sending is not set up)"
                if what:
                    self.emit("MS", "SEND", f"{what} {where}.")
                else:
                    self.emit("MS", "INFO", "No feedback message was ready to deliver.")
            else:
                self.emit("MS", "INFO", "No feedback messages written, as the goal asked.")
            if want["csv"]:
                tools.write_marks_csv(self.out_dir, self.subs, rubric)
                self._record_file("marks.csv")
                self.emit("MS", "SEND", f"Mark sheet written to {self.where}/marks.csv.")
            if want["report"]:
                self._class_report()

    def _evidence(self):
        """How a quoted piece of evidence is introduced in the teacher's documents."""
        return {"evidence": "From the attempt log"} if self.assessment == "practical" else {}

    def _resubmit_message(self, s, first, what):
        rubric = self.rubric
        if self.assessment == "practical":
            return {"subject": "Please redo the PC assembly practical", "body": (
                f"Hi {first},\n\nI could not mark your PC assembly practical because there is no attempt from you in "
                f"the virtual lab's records. The task was: {rubric['task']}\n\nPlease book a session in the lab and "
                "complete the assembly so that it can be marked. If something is making it hard to finish, tell your teacher.")}
        return {"subject": "Please resubmit your essay", "body": (
            f"Hi {first},\n\nI could not mark your essay because {what}. "
            f"The task was: {rubric['task']}\n\nPlease send your full essay "
            "so that it can be marked. If something is making it hard to finish, tell your teacher.")}

    def _clean(self, raw, s):
        """A mark as a trusted structure, with every problem code can find: arithmetic, range and quoted evidence,
        and for a practical, any score above what the attempt log allows."""
        mark, problems = tools.clean_mark(raw, self.rubric, s["text"])
        if s.get("attempt"):
            problems += tools.check_practical(mark, self.rubric, s["attempt"])
        return mark, problems

    def _record_file(self, name):
        if name not in self.files:
            self.files.append(name)

    def _settled(self):
        """Essays whose mark is settled: the ones class figures are built from."""
        return [s for s in self.subs if s["final"] and s["status"] in ("agreed", "delivered")]

    def _criteria_avg(self, done):
        """The class average on each rubric criterion, as a percentage of its maximum."""
        return [{"id": c["id"], "name": c["name"],
                 "avg_pct": round(100 * sum(s["final"]["scores"][c["id"]]["score"] for s in done) / (len(done) * c["max"]))}
                for c in self.rubric["criteria"]]

    def _attention(self):
        """What the teacher should look at personally."""
        no_plan = {e["id"] for e in (self.support or {}).get("learners", []) if e["status"] == "held"}
        rows = []
        for s in self.subs:
            why = [FLAG_TEXT.get(f, f) for f in s["flags"] if not (f == "too_short" and "missing" in s["flags"])]
            if s["id"] in no_plan:
                why.append("falling behind, and the catch-up plan failed its checks")
            if s["status"] == "resubmit":
                why.append("asked to resubmit" if s["feedback"] else "not marked")
            if s["status"] == "escalated":
                why.append("the handwritten script needs your check" if s.get("script_hold") else "waiting for your decision")
            if why:
                rows.append({"id": s["id"], "learner": s["learner"], "why": "; ".join(why)})
        for rec in (self.intake or {}).get("scripts", []):
            if rec["status"] == "held" and not rec["learner"]:
                rows.append({"id": rec["id"], "learner": f"Unknown learner (name read as “{rec['name'] or 'nothing'}”)",
                             "why": "handwritten script held: " + "; ".join(rec["problems"])})
        return rows

    def _class_report(self):
        rubric = self.rubric
        done = self._settled()
        if not done:
            return
        summary = {
            "max": rubric["total"],
            "average": round(sum(s["final"]["total"] for s in done) / len(done), 1),
            "criteria_avg": self._criteria_avg(done),
            "rows": [{"id": s["id"], "total": s["final"]["total"],
                      "reasons": {c["id"]: s["final"]["scores"][c["id"]]["reason"] for c in rubric["criteria"]}} for s in done],
        }
        raw = agents.report(self.llm, rubric, summary, self._log("MS"))
        as_list = lambda v: [str(x) for x in v] if isinstance(v, list) else []
        self.report = {
            "marked": len(done), "average": summary["average"], "max": rubric["total"], "criteria_avg": summary["criteria_avg"],
            "summary": str(raw.get("summary") or ""), "strengths": as_list(raw.get("strengths")),
            "gaps": as_list(raw.get("gaps")), "next_lesson": as_list(raw.get("next_lesson")),
            "attention": self._attention(),
            "consistency": (self.consistency or {}).get("summary") or "",
            "consistency_status": (self.consistency or {}).get("status") or "",
        }
        r = self.report
        lines = [f"# Class report\n\n{r['summary']}\n\nAverage: {r['average']}/{r['max']} across {_n(len(done), self.noun)}\n"]
        lines += [f"- {c['name']}: {c['avg_pct']}%" for c in r["criteria_avg"]]
        for title, key in (("Strengths", "strengths"), ("Gaps", "gaps"), ("Teach next", "next_lesson")):
            lines.append(f"\n## {title}\n" + "\n".join(f"- {x}" for x in r[key]))
        if r["consistency"]:
            lines.append("\n## Catch-up and the lesson\n\n" + r["consistency"])
        if self.intake:
            lines.append("\n## Handwritten scripts\n\n" + self.intake["summary"]
                         + " What the Clerk read on every page is in scripts/clerk_report.md.")
        lines.append("\n## Needs your attention\n" + "\n".join(f"- {a['id']} {a['learner']}: {a['why']}" for a in r["attention"]))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "class_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._record_file("class_report.md")
        self.emit("MS", "SEND", f"Class report written to {self.where}/class_report.md.")

    # ---- the one place a person steps in --------------------------------
    def resolve(self, sid, choice):
        """Teacher settles an escalated essay by choosing the Marker's or the Reviewer's mark."""
        s = self._sub(sid)
        with self.lock:
            if not s or s["status"] != "escalated" or choice not in ("marker", "reviewer") or not s[choice]:
                return False
            s["final"], s["status"], s["issue"] = s[choice], "agreed", None
            self.stats["human_interventions"] += 1
            self.stats["escalated"] -= 1
            self.stats["marked"] += 1
            late = self._closing  # before this point the run itself still writes and delivers the feedback
        s["history"].append({"who": "Teacher", "what": f"Chose the {choice.title()}'s mark: {s['final']['total']}/{self.rubric['total']}."})
        self.emit("PL", "HUMAN", f"Teacher chose the {choice.title()}'s mark ({s['final']['total']}).", sid)
        if late:
            threading.Thread(target=self._finish_late, args=(s,), daemon=True).start()
        return True

    def _finish_late(self, s):
        """Finish an essay the teacher settled after the run had moved on: feedback, the warning signs, delivery."""
        with self.work:  # waits for the run, or an earlier decision, to finish first
            if s["status"] != "agreed":
                return
            try:
                self._finish(s)
            except Exception as e:
                traceback.print_exc()
                self.emit("MS", "ERROR", f"Could not finish this {self.noun}: {e}", s["id"])
            self._write_corrections()

    def _finish(self, s):
        if self.plan["deliver"]["feedback"]:
            s["feedback"] = None
            self._write_feedback([s])
        if self.plan["deliver"]["support"]:
            self._support([s])  # this learner could not be checked until the mark was settled
            if self.plan["deliver"]["lesson"]:
                self._align()  # the new plan has to agree with the lesson too, within the same one-revision limit
        self._deliver([s])

    # ---- photographed scripts (the Clerk) -----------------------------------
    def _intake(self):
        """Photos came with the goal. The Planner decides whether they need reading; if so, the Clerk reads them first."""
        with self._busy("PL", "Deciding whether the photographed scripts need reading"):
            raw = agents.intake(self.llm, self.goal, len(self.pages), self._log("PL"))
        reason = str(raw.get("reason") or "").strip()
        if raw.get("ingest") is not True:
            self.agent_state[CLERK] = "off"
            self.emit("PL", "DECIDE", "The photos will not be read. " + (reason or "The goal did not call for them.")
                      + " The typed essays on file are marked as they are.")
            return
        self.emit("PL", "DECIDE", "The Clerk reads the photographed scripts before any marking. " + reason)
        self._ingest()

    def _ingest(self):
        """Transcribe every page, check every reading in code, read a failing page once more, then hold what still fails.

        Accepted scripts become their learners' submissions and are marked exactly like typed essays. A script that
        still fails its checks after one re-read is not marked: it waits for the teacher, who can accept the
        transcript or set it aside. Nothing is ever marked from a reading the checks reject.
        """
        pages = self.pages
        info = {p["id"]: p for p in pages}
        folder = self.out_dir / "scripts"
        ingest.copy_pages(pages, folder / "pages")
        ingest.build_pdf([(p["data"], p["mime"]) for p in pages], folder / "all_pages.pdf", "All photographed pages")
        self._record_file("scripts/all_pages.pdf")
        with self.lock:
            self.intake = {
                "batch": self.batch, "status": "reading", "summary": "", "scripts": [],
                "pages": [{"id": p["id"], "original": p["original"], "read": None, "first": None, "reads": 0,
                           "first_problems": [], "problems": [], "script": None, "guard": None} for p in pages],
            }
        entry = {e["id"]: e for e in self.intake["pages"]}

        with self._busy(CLERK, f"Reading {_n(len(pages), 'photographed page')}"):
            self.emit(CLERK, "ACT", f"Transcribing {_n(len(pages), 'photographed page')} word for word, keeping the learners' own spelling.")
            for p in pages:
                read = self._read(p)
                entry[p["id"]].update(read=read, reads=1)
                self.emit(CLERK, "INFO", self._describe(p["id"], read))
        if self.inject_ocr_fault:
            self._corrupt_one_read()

        self.intake["status"] = "checking"
        again = self._failing_pages(self._sort_scripts())
        if again:
            for pid, (problems, hints) in again.items():
                close = f" Close names on the class list: {', '.join(hints)}." if hints else ""
                self.emit(CLERK, "REJECT", f"{pid} fails its checks: {'; '.join(problems)}.{close} Reading it again, more closely.")
            with self._busy(CLERK, f"Re-reading {', '.join(again)}"):
                for pid, (problems, hints) in again.items():
                    e = entry[pid]
                    notes = problems + ([f"names on the class list close to the name you read: {', '.join(hints)}. If the page "
                                         "shows one of them, give it exactly; if it does not, copy what is written"] if hints else [])
                    before, after = e["read"], self._read(info[pid], notes)
                    e.update(first=before, first_problems=list(problems), read=after, reads=2)
                    if before["name"] and after["name"] and \
                            tools.edit_distance(tools._norm(before["name"]), tools._norm(after["name"])) > 2:
                        # Not a closer look but a different answer: keep the first name, so the page cannot
                        # land on another learner's work, and let the teacher decide.
                        e["guard"] = (f"the second reading changed the name from “{before['name']}” to “{after['name']}”, "
                                      "too big a change to be a correction")
                        after = {**after, "name": before["name"]}
                        e["read"] = after
                    self.emit(CLERK, "FIX", self._describe_fix(pid, before, after))

        scripts = self._sort_scripts()
        final = {pid: tools.check_read(e["read"]) + ([e["guard"]] if e["guard"] else []) for pid, e in entry.items()}
        records = []
        for n, (script, learner, problems) in enumerate(scripts, 1):
            pids = script["pages"]
            text = tools.script_text([entry[q]["read"]["text"] for q in pids])
            issues = problems + [f"{q}: {item}" for q in pids for item in final[q]]
            rec = {
                "id": f"S{n}", "name": script["name"], "pages": pids, "text": text, "words": len(text.split()),
                "learner": learner["id"] if learner else None, "learner_name": learner["learner"] if learner else None,
                "status": "held" if issues else "accepted", "problems": issues, "decided": None, "file": None,
                "reread": any(entry[q]["reads"] > 1 for q in pids), "reordered": script["reordered"],
                "suggest": [] if learner else tools.close_learners(script["name"], self.subs),
            }
            for q in pids:
                entry[q].update(script=rec["id"], problems=final[q])
            self._file_script(rec, info)
            records.append(rec)
        with self.lock:
            self.intake["scripts"] = records
        for rec in records:
            if rec["reordered"]:
                self.emit(CLERK, "INFO", f"Script {rec['id']}'s pages were photographed out of order; put back in page order ({', '.join(rec['pages'])}).")
            if rec["learner"]:
                self._attach(rec)
            else:
                self.emit(CLERK, "ESCALATE", f"Script {rec['id']} held for the teacher: {'; '.join(rec['problems'])}. "
                                             "It belongs to nobody on the class list until the teacher says whose it is.")
        held = sum(r["status"] == "held" for r in records)
        twice = sum(e["reads"] > 1 for e in entry.values())
        with self.lock:
            self.intake["status"] = "done"
            self.intake["summary"] = (
                f"{_n(len(pages), 'photographed page')} read as {_n(len(records), 'handwritten script')}: "
                f"{len(records) - held} accepted, {held} held for the teacher"
                + (f", {_n(twice, 'page')} read a second time after failing a check." if twice else ".")
            )
        self._write_clerk_report()

    def _read(self, page, notes=None):
        """One reading of one page. A model that cannot answer gives an empty reading, which the checks then reject."""
        try:
            raw = agents.read_page(self.llm, page, self._log(CLERK), notes)
        except LLMError as e:
            raw = {"problem": f"the model could not read the photo: {e}"}
        return tools.clean_read(raw)

    def _sort_scripts(self):
        """Group the pages into scripts and check each script. Returns [(script, learner or None, problems)]."""
        pages = [{"id": e["id"], "read": e["read"]} for e in self.intake["pages"]]
        reads = {p["id"]: p["read"] for p in pages}
        out = []
        for script in tools.group_pages(pages):
            learner, problems = tools.check_script(script, reads, self.subs)
            out.append((script, learner, problems))
        owners = {}
        for script, learner, problems in out:
            if learner:
                owners.setdefault(learner["id"], []).append(problems)
        for lid, lists in owners.items():
            if len(lists) > 1:
                for problems in lists:
                    problems.append(f"{len(lists)} scripts carry the name {self._sub(lid)['learner']}")
        return out

    def _failing_pages(self, scripts):
        """Which pages to read again: {page id: (problems found, close names on the class list)}.

        A page that fails its own checks is read again. So is a script that fails as a whole: the pages carrying a
        name when only the name is wrong, otherwise every page of it, since the page numbers may have been misread.
        """
        again = {}
        for e in self.intake["pages"]:
            problems = tools.check_read(e["read"])
            if problems:
                again[e["id"]] = (problems, [])
        for script, learner, problems in scripts:
            if not problems:
                continue
            others = problems[1:] if not learner else problems  # check_script puts a name problem first
            pids = script["pages"] if others else ([q for q in script["pages"] if self._entry(q)["read"]["name"]] or script["pages"])
            hints = [c["learner"] for c in tools.close_learners(script["name"], self.subs)] if not learner else []
            for q in pids:
                found, close = again.setdefault(q, ([], []))
                found += [item for item in problems if item not in found]
                close += [name for name in hints if name not in close]
        return again

    def _entry(self, pid):
        return next(e for e in self.intake["pages"] if e["id"] == pid)

    def _describe(self, pid, read):
        where = f"page {read['page']}" + (f" of {read['of']}" if read["of"] else "") if read["page"] else "no page number"
        return (f"{pid}: {('“' + read['name'] + '”') if read['name'] else 'no name'}, {where}; "
                f"{tools.written_lines(read['text'])} lines, {read['words']} words, {round(100 * read['confidence'])}% sure.")

    def _describe_fix(self, pid, before, after):
        changes = []
        if after["name"] != before["name"]:
            changes.append(f"name now “{after['name'] or 'none'}” (first read as “{before['name'] or 'none'}”)")
        got_before, got_after = tools.written_lines(before["text"]), tools.written_lines(after["text"])
        if got_after != got_before:
            changes.append(f"{got_after} lines transcribed (first time {got_before})")
        if (after["page"], after["of"]) != (before["page"], before["of"]):
            changes.append(f"page {after['page'] or '?'} of {after['of'] or '?'} (first time {before['page'] or '?'} of {before['of'] or '?'})")
        if after["confidence"] != before["confidence"]:
            changes.append(f"{round(100 * after['confidence'])}% sure (first time {round(100 * before['confidence'])}%)")
        return f"{pid} read again: " + ("; ".join(changes) if changes else "the same reading as the first time") + "."

    def _corrupt_one_read(self):
        """Test mode: quietly delete the bottom half of one page's transcript, to prove the Clerk's checks catch it unprompted.

        The page chosen is one that would otherwise pass, so the catch and the fix are the fault's alone.
        """
        clean = {q for script, _, problems in self._sort_scripts() if not problems for q in script["pages"]}
        long_enough = [e for e in self.intake["pages"] if tools.written_lines(e["read"]["text"]) >= 6]
        e = next((e for e in long_enough if e["id"] in clean and not tools.check_read(e["read"])), None) or \
            next(iter(long_enough), None)
        if not e:
            return
        lines = e["read"]["text"].split("\n")
        written = [i for i, line in enumerate(lines) if line.strip()]
        cut = written[len(written) // 2]
        e["read"] = tools.clean_read({**e["read"], "text": "\n".join(lines[:cut])})
        self.emit("PL", "TEST", f"Fault injection is on: the bottom {len(written) - len(written) // 2} lines of {e['id']}'s "
                                "transcript were deleted after the Clerk read it. Nobody told the Clerk.")

    def _file_script(self, rec, info):
        """The script as its own PDF, in page order, and its transcript as text, in output/<run>/scripts."""
        who = f"{rec['learner']}_{rec['learner_name']}" if rec["learner"] else f"{rec['id']}_unknown"
        stem = re.sub(r"[^\w.-]+", "_", who)
        folder = self.out_dir / "scripts"
        ingest.build_pdf([(info[q]["data"], info[q]["mime"]) for q in rec["pages"]], folder / f"{stem}.pdf",
                         f"{rec['learner_name'] or 'Unknown learner'}, handwritten script")
        rec["file"] = f"scripts/{stem}.pdf"
        self._record_file(rec["file"])
        head = [f"Script {rec['id']}: " + (f"{rec['learner']} {rec['learner_name']}" if rec["learner"] else f"name read as “{rec['name']}”"),
                f"Pages: {', '.join(rec['pages'])}. Words: {rec['words']}. Status: {rec['status']}."]
        if rec["problems"]:
            head.append("Held because: " + "; ".join(rec["problems"]) + ".")
        (folder / "transcripts").mkdir(parents=True, exist_ok=True)
        (folder / "transcripts" / f"{stem}.txt").write_text("\n".join(head) + "\n\n" + rec["text"] + "\n", encoding="utf-8")

    def _write_clerk_report(self):
        tools.write_clerk_report(self.out_dir, self.intake)
        self._record_file("scripts/clerk_report.md")

    def _attach(self, rec):
        """An accepted script becomes its learner's submission. A held one puts the learner in front of the teacher."""
        s = self._sub(rec["learner"])
        typed = s["words"] > 0
        s.update(text=rec["text"], words=rec["words"], flags=[], source="script", script=rec["id"])
        pages = _n(len(rec["pages"]), "page")
        if rec["status"] == "accepted":
            s["history"].append({"who": "Clerk", "what": f"Handwritten script {rec['id']} transcribed: {pages}, {rec['words']} words."
                                 + (" It replaces the typed file for this run." if typed else "")})
            self.emit(CLERK, "APPROVE", f"Script {rec['id']} accepted: {pages} in order, {rec['words']} words, every check passed."
                      + (" It replaces the typed file for this run." if typed else ""), s["id"])
            return
        problems = "; ".join(rec["problems"])
        s.update(status="escalated", script_hold=True,
                 issue=f"The handwritten script needs your check: {problems}. Nothing has been marked from it.")
        self.stats["escalated"] += 1
        s["history"].append({"who": "Clerk", "what": f"Handwritten script {rec['id']} held for the teacher: {problems}."})
        self.emit(CLERK, "ESCALATE", f"Script {rec['id']} held for the teacher: {problems}. Nothing will be marked from it until the teacher decides.", s["id"])

    def resolve_script(self, script_id, choice, learner_id=None):
        """Teacher settles a script the Clerk held: accept the transcript, or set it aside.

        A held script whose learner is known can only be accepted for that learner. One whose name is not on the
        class list can be accepted for a learner who has nothing marked yet. Returns False if the request does not fit.
        """
        with self.lock:
            rec = next((r for r in (self.intake or {}).get("scripts", []) if r["id"] == script_id), None)
            if not rec or rec["status"] != "held" or choice not in ("accept", "set_aside"):
                return False
            target = self._sub(rec["learner"] or str(learner_id or ""))
            if choice == "accept":
                if not target or not rec["words"] or (rec["learner"] and learner_id and learner_id != rec["learner"]):
                    return False  # nobody to give it to, nothing that could be marked, or someone else's script
                own = target.get("script") == rec["id"] and target["status"] == "escalated"
                free = not rec["learner"] and target["status"] == "resubmit" and not target["final"] and not target.get("script")
                if not (own or free):
                    return False
                was = target["status"]
                target.update(text=rec["text"], words=rec["words"], flags=[], source="script", script=rec["id"],
                              script_hold=False, issue=None, status="received", feedback=None)
                tools.triage([target], self.rubric)
                self.stats["escalated" if was == "escalated" else "resubmit"] -= 1
                rec.update(status="accepted", decided="teacher", learner=target["id"], learner_name=target["learner"])
                what = f"Accepted the transcript of handwritten script {rec['id']} as it stands, so it can be marked."
            else:
                rec.update(status="set_aside", decided="teacher")
                if target and target.get("script") == rec["id"] and target["status"] == "escalated":
                    target.update(status="resubmit", script_hold=False, issue=None)
                    self.stats["escalated"] -= 1
                    self.stats["resubmit"] += 1
                else:
                    target = None
                what = f"Set handwritten script {rec['id']} aside: nothing is marked from it."
            self.stats["human_interventions"] += 1
        if target:
            target["history"].append({"who": "Teacher", "what": what})
        self.emit("PL", "HUMAN", f"Teacher: {what[0].lower()}{what[1:]}", target["id"] if target else None)
        self._write_clerk_report()
        threading.Thread(target=self._after_script_decision, args=(target, choice), daemon=True).start()
        return True

    def _after_script_decision(self, s, choice):
        """Mark a script the teacher released, then finish it like any essay; or ask for a set-aside one again."""
        with self.work:  # waits for the run, or an earlier decision, to finish first
            if s is None or self.plan is None:
                return
            try:
                if choice == "accept" and s["status"] == "received":
                    self._mark_batch(0, [s], label="Released by the teacher")
                    if s["status"] == "agreed":
                        self._finish(s)
                    else:
                        self._deliver([])  # the mark sheet and the report show it waiting for the teacher
                elif choice == "set_aside" and s["status"] == "resubmit":
                    if self.plan["deliver"]["support"]:
                        self._support([s])
                        if self.plan["deliver"]["lesson"]:
                            self._align()
                    self._deliver([])
            except Exception as e:
                traceback.print_exc()
                self.emit("MS", "ERROR", f"Could not finish this script: {e}", s["id"])
            self._write_corrections()
