"""Deterministic tools the agents rely on: loading work, checking marks, delivering results.

Anything that can be checked with plain code is checked here, never by asking a model.
"""
import csv
import json
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

INJECTION = re.compile(
    r"ignore (the|all|any|your)[^.]{0,40}(rubric|instructions)|note to the (ai|marker)|"
    r"award (this essay )?full marks|as an ai|system prompt", re.I)


def load_env(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# Question-paper tests in other subjects, marked question by question against a memo: key -> subject name.
# Each is data/<key>_rubric.json, data/<key>_memo.md and an answer script per learner in data/tests/<key>/<id>.txt.
TESTS = {"maths": "Mathematics", "science": "Physical Sciences", "history": "History"}
RUBRIC_FILES = {"essay": "rubric.json", "practical": "practical_rubric.json", **{k: f"{k}_rubric.json" for k in TESTS}}
MEMO_FILES = {"essay": "memo.md", "practical": "practical_memo.md", **{k: f"{k}_memo.md" for k in TESTS}}


def is_test(assessment):
    return assessment in TESTS


def available_tests(data_dir):
    """The subject tests whose rubric is on disk: [{key, label, title}]."""
    out = []
    for key, label in TESTS.items():
        path = Path(data_dir) / RUBRIC_FILES[key]
        if path.exists():
            title = json.loads(path.read_text(encoding="utf-8")).get("title", f"{label} test")
            out.append({"key": key, "label": label, "title": title})
    return out
STOPWORDS = set("""a about after all also an and any are as at be because been but by can do does done for from good harm
has have how in into is it its more most much no not of on or our so than that the their them then there these they this
those to was we were what when which who will with without you your young south african africans discuss""".split())


def memo_terms(text):
    """The words that show an answer is on the topic: the memo's 'Key terms' line, if it has one."""
    match = re.search(r"^#+\s*key terms\s*$\n+(.+)", text or "", re.I | re.M)
    if not match:
        return []
    return [t.strip().lower() for t in re.split(r"[,;]", match.group(1)) if t.strip()]


# Words in a Grade 12 task line that say what kind of paper it is, not what it is about.
STOPWORDS = set(STOPWORDS) | {"grade", "theory", "written", "response", "paper"}


def topic_terms(rubric):
    """What counts as on topic: the memo's key terms, else the content words of the task that was set."""
    terms = (rubric.get("memo") or {}).get("terms") or []
    if terms:
        return terms
    words = re.findall(r"[A-Za-z]{4,}", rubric.get("task", ""))
    return sorted({w.lower() for w in words if w.lower() not in STOPWORDS and not w.lower().startswith(("essay", "word", "topic", "write"))})


def load_memo(data_dir, assessment="essay"):
    """The teacher's marking memo for an assessment, or None. It sits beside the rubric as plain text or Markdown."""
    path = Path(data_dir) / MEMO_FILES[assessment]
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8-sig").strip()
    return {"file": path.name, "text": text, "terms": memo_terms(text)} if text else None


def load_rubric(data_dir, assessment="essay"):
    """The rubric for an assessment (the essay rubric, or the PC assembly practical's), with its marking memo if there is one."""
    rubric = json.loads((Path(data_dir) / RUBRIC_FILES[assessment]).read_text(encoding="utf-8"))
    rubric.setdefault("kind", "test" if is_test(assessment) else assessment)
    rubric.setdefault("work", "answer script" if rubric["kind"] == "test" else "essay")
    rubric["assessment"] = assessment
    for c in rubric["criteria"]:
        if c.get("parts"):
            c.setdefault("max", sum(_int(p.get("marks")) for p in c["parts"]))
        if not c.get("bands"):
            c["bands"] = question_bands(c)
    rubric["total"] = sum(c["max"] for c in rubric["criteria"])
    rubric["memo"] = load_memo(data_dir, assessment)
    return rubric


def question_bands(c):
    """Bands for a test question that has none written: from every part right down to nothing right."""
    top = c["max"]
    a, b = -(-top * 6 // 10), -(-top * 3 // 10)  # 60% and 30%, rounded up
    labels = "Parts " + ", ".join(p["label"] for p in c.get("parts") or []) if c.get("parts") else "The question"
    rows = [((top, top), f"{labels}: every part correct, with the working or reasons the memo asks for."),
            ((a, top - 1), "Most parts correct; a slip, a missing step or a missing point in one or two parts."),
            ((b, a - 1), "Some parts correct, or the right method with wrong final answers."),
            ((1, b - 1), "Little correct: a step of method or a single point at most."),
            ((0, 0), "No correct answer, or not attempted.")]
    return [{"range": [lo, hi], "text": text} for (lo, hi), text in rows if lo <= hi]


def _int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _percent(value):
    """A percentage typed into the class list ("62", "62%", "62.5"), or None if there is none."""
    try:
        number = float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def load_outcomes(data_dir, rubric):
    """Learning outcomes that lessons and catch-up plans are checked against: [{id, text, criteria}].

    Read from outcomes.json, where each outcome lists the rubric criteria it serves. Without that
    file each rubric criterion stands in as an outcome, so the checks still have something to hold
    the work against.
    """
    path = Path(data_dir) / "outcomes.json"
    rows = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = data.get("outcomes", []) if isinstance(data, dict) else data
    known = {c["id"] for c in rubric["criteria"]}
    kind = rubric.get("assessment") or rubric.get("kind", "essay")
    outcomes = [
        {"id": str(o["id"]).strip(), "text": str(o["text"]).strip(),
         "criteria": [str(c) for c in o.get("criteria") or [] if str(c) in known]}
        for o in rows if isinstance(o, dict) and o.get("id") and o.get("text")
        and o.get("assessment", "essay") == kind  # the essay's outcomes for essays, the practical's for the practical, and so on
    ]
    if not outcomes:
        outcomes = [{"id": c["id"], "text": f"{c['name']}: {max(c['bands'], key=lambda b: b['range'][1])['text']}",
                     "criteria": [c["id"]]} for c in rubric["criteria"]]
    return outcomes


def load_submissions(data_dir):
    """Read class.csv (id, name, email and optionally previous, the last essay mark as a percentage) and the essay files."""
    data_dir = Path(data_dir)
    subs = []
    with open(data_dir / "class.csv", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            sid = (row.get("id") or "").strip()
            if not sid:
                continue  # blank line in the class list
            path = data_dir / "essays" / f"{sid}.txt"
            text = path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""
            subs.append(new_submission(sid, (row.get("name") or "").strip() or sid, (row.get("email") or "").strip(),
                                       text, _percent(row.get("previous"))))
    return subs


def new_submission(sid, learner, email="", text="", previous=None):
    """One learner's entry for a run, with nothing marked yet."""
    return {
        "id": sid, "learner": learner, "email": email, "previous": previous,
        "text": text, "words": len(text.split()), "flags": [], "status": "received",
        # rejected: a Marker's mark the Reviewer sent back.  issue: why the essay is waiting for the teacher.
        "marker": None, "reviewer": None, "rejected": None, "final": None, "issue": None,
        "feedback": None, "history": [],
        # source: "typed", or "script" once the Clerk has transcribed a handwritten one (script: its id).
        # script_hold: the Clerk held that script for the teacher, so nothing is marked from it yet.
        # added: the teacher added this learner during the run, from a script whose name was not on the class list.
        "source": "typed" if text else None, "script": None, "script_hold": False, "added": False,
    }


def next_learner_id(subs):
    """An id for a learner added during a run, in the class list's own style: E12 is followed by E13."""
    taken = {s["id"] for s in subs}
    found = [re.fullmatch(r"([A-Za-z]*)(\d+)", s["id"]) for s in subs]
    found = [m for m in found if m]
    prefix = found[0].group(1) if found else "N"
    width = max((len(m.group(2)) for m in found), default=2)
    n = max((int(m.group(2)) for m in found if m.group(1) == prefix), default=0) + 1
    while f"{prefix}{n:0{width}d}" in taken:
        n += 1
    return f"{prefix}{n:0{width}d}"


def load_answers(data_dir, subs, assessment):
    """Give each learner their answer script for a subject test as the work to mark: data/tests/<subject>/<id>.txt.

    A learner with no script has nothing to mark, like a learner who handed in no essay. The previous marks in
    class.csv are for the essays, so there is no previous mark for this test to compare with.
    """
    folder = Path(data_dir) / "tests" / assessment
    for s in subs:
        path = folder / f"{s['id']}.txt"
        text = path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""
        s.update(text=text, words=len(text.split()), previous=None, source="typed" if text else None)
    return subs


def triage(subs, rubric):
    """Flag submissions that are missing, too short, or that try to instruct the marker."""
    for s in subs:
        if s["words"] == 0:
            s["flags"] += ["missing", "too_short"]
        elif s["words"] < rubric.get("min_words", 50):
            s["flags"].append("too_short")
        if INJECTION.search(s["text"]):
            s["flags"].append("instruction_to_marker")


def materials(subs, rubric, pages=None, batch=None):
    """Everything the team will work from, for the teacher to read before anything is planned:
    the memo, the rubric, and every learner's script (typed essay or attempt log) with what the checks noticed."""
    return {
        "rubric": rubric, "memo": rubric.get("memo"), "work": rubric.get("work", "essay"),
        "learners": [{"id": s["id"], "learner": s["learner"], "words": s["words"], "flags": list(s["flags"]),
                      "text": s["text"], "source": s.get("source")} for s in subs],
        "pages": [{"id": p["id"], "original": p.get("original") or p["id"]} for p in pages or []],
        "batch": batch,
    }


def _norm(t):
    """Lower-case words separated by single spaces: apostrophes dropped, other punctuation turned into spaces."""
    t = re.sub(r"['’‘`]", "", str(t).lower())
    return re.sub(r"[\W_]+", " ", t).strip()


def quote_in_text(quote, text):
    """True if the quote really appears in the essay. An ellipsis may join separate fragments.

    Case, spacing and punctuation are ignored, so a marker who tidies a comma is not accused of
    inventing evidence. The words themselves must match.
    """
    text = _norm(text)
    parts = [_norm(p) for p in re.split(r"\.\.\.|…", str(quote or ""))]
    parts = [p for p in parts if p]
    return bool(parts) and all(len(p) >= 8 and p in text for p in parts)


def clean_mark(raw, rubric, text):
    """Turn a model's mark into a trusted structure. Returns (mark, problems).

    The total is always added up here, so a model's arithmetic is never trusted.
    """
    problems, scores = [], {}
    raw_scores = raw.get("scores") if isinstance(raw, dict) else None
    if not isinstance(raw_scores, dict):
        raw_scores = {}
    for c in rubric["criteria"]:
        item = raw_scores.get(c["id"])
        if not isinstance(item, dict):
            problems.append(f"{c['name']}: no mark was given.")
            item = {}
        try:
            score = int(round(float(item.get("score"))))
        except (TypeError, ValueError, OverflowError):
            score = 0
            if item:
                problems.append(f"{c['name']}: the mark is not a number.")
        if not 0 <= score <= c["max"]:
            problems.append(f"{c['name']}: {score} is outside 0-{c['max']}.")
            score = max(0, min(c["max"], score))
        evidence = str(item.get("evidence") or "").strip()
        if item and not quote_in_text(evidence, text):
            where = {"practical": "the attempt log", "test": "the answer script"}.get(rubric.get("kind"), "the essay")
            problems.append(f"{c['name']}: the quoted evidence does not appear in {where}.")
        scores[c["id"]] = {"score": score, "evidence": evidence, "reason": str(item.get("reason") or "").strip()}
    mark = {"scores": scores, "total": sum(v["score"] for v in scores.values())}
    return mark, problems


def disagreements(rubric, a, b):
    """Criteria where two markers differ by more than the moderation tolerance."""
    out = []
    for c in rubric["criteria"]:
        tol = max(1, round(c["max"] * 0.15))
        x, y = a["scores"][c["id"]]["score"], b["scores"][c["id"]]["score"]
        if abs(x - y) > tol:
            out.append({"criterion": c["id"], "name": c["name"], "marker": x, "reviewer": y, "tolerance": tol})
    total_tol = max(2, round(rubric["total"] * 0.1))
    if not out and abs(a["total"] - b["total"]) > total_tol:
        out.append({"criterion": "total", "name": "Total", "marker": a["total"], "reviewer": b["total"], "tolerance": total_tol})
    return out


def check_feedback(msg, sub, all_subs, rubric):
    """Problems with a feedback message, checked in code before anything is sent."""
    problems = []
    body = str(msg.get("body") or "") if isinstance(msg, dict) else ""
    first = sub["learner"].split()[0]
    if not re.search(rf"\b{re.escape(first)}\b", body, re.I):
        problems.append(f"does not address {first} by name")
    total, out_of = sub["final"]["total"], rubric["total"]
    # The exact mark, so that 4/50 is not satisfied by a message that says 34/50.
    if not re.search(rf"(?<![\d.]){total}\s*/\s*{out_of}(?!\d)", body):
        problems.append(f"does not state the final mark {total}/{out_of}")
    n = len(body.split())
    if not 50 <= n <= 260:
        problems.append(f"is {n} words long (expected 50-260)")
    for other in all_subs:
        name = other["learner"].split()[0]
        if other["id"] != sub["id"] and name != first and re.search(rf"\b{re.escape(name)}\b", body):
            problems.append(f"mentions another learner ({name})")
    return problems


def write_email(out_dir, sub, subject, body):
    out = Path(out_dir) / "outbox"
    out.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]+", "_", f"{sub['id']}_{sub['learner']}")  # safe as a file name on any system
    path = out / f"{name}.txt"
    path.write_text(f"To: {sub['learner']} <{sub['email']}>\nSubject: {subject}\n\n{body}\n", encoding="utf-8")
    return path


def send_email(sub, subject, body):
    """Send by SMTP when it is configured. Returns True if the message really left."""
    host = os.getenv("SMTP_HOST")
    if not host or os.getenv("SEND_REAL_EMAIL") != "1" or not sub.get("email"):
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    msg["To"] = sub["email"]
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS", ""))
        s.send_message(msg)
    return True


def write_marks_csv(out_dir, subs, rubric):
    path = Path(out_dir) / "marks.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "learner", "status"] + [c["name"] for c in rubric["criteria"]] + ["total", "out_of", "notes"])
        for s in subs:
            fin = s["final"]
            w.writerow(
                [s["id"], s["learner"], s["status"]]
                + [fin["scores"][c["id"]]["score"] if fin else "" for c in rubric["criteria"]]
                + [fin["total"] if fin else "", rubric["total"], "; ".join(s["flags"])]
            )
    return path


# ---- learners falling behind ----------------------------------------------------------------

SUPPORT_RULES = {"below_pct": 50, "drop_points": 15, "criterion_below_pct": 40}


def weakest_criterion(mark, rubric):
    """The criterion on which a mark is lowest as a share of its maximum."""
    c = min(rubric["criteria"], key=lambda c: mark["scores"][c["id"]]["score"] / c["max"])
    return {"id": c["id"], "name": c["name"], "pct": round(100 * mark["scores"][c["id"]]["score"] / c["max"])}


def support_rules(rubric):
    """The thresholds in force: the defaults, with anything set under "support" in rubric.json on top."""
    return {**SUPPORT_RULES, **(rubric.get("support") or {})}


def support_signs(sub, rubric):
    """Warning signs that a learner is falling behind, worked out from the marks by fixed rules.

    Returns [{kind, text}]: an empty list means no concern. Thresholds can be set under "support"
    in rubric.json. An essay still waiting for the teacher has no final mark, so it raises nothing yet.
    """
    rules = support_rules(rubric)
    final = sub["final"]
    if not final:
        if sub["status"] != "resubmit":
            return []
        return [{"kind": "missing", "text": "Too little handed in to mark" if sub["words"] else "Nothing handed in"}]
    signs = []
    now = 100 * final["total"] / rubric["total"]
    if now < rules["below_pct"]:
        signs.append({"kind": "below", "text": f"{round(now)}% is below {rules['below_pct']}%"})
    previous = sub.get("previous")
    if previous is not None and previous - now >= rules["drop_points"]:
        signs.append({"kind": "dropped", "text": f"Down {round(previous - now)} points from {round(previous)}%"})
    for c in rubric["criteria"]:
        share = 100 * final["scores"][c["id"]]["score"] / c["max"]
        if share < rules["criterion_below_pct"]:
            signs.append({"kind": "weak_area", "text": f"{c['name']} at {round(share)}%", "criterion": c["id"]})
    return signs


def clean_support_plan(raw):
    """A Coach's reply as a predictable structure, whatever the model left out or mistyped."""
    raw = raw if isinstance(raw, dict) else {}
    steps = [
        {"outcome": str(st.get("outcome") or "").strip(), "activity": str(st.get("activity") or "").strip(), "minutes": _int(st.get("minutes"))}
        for st in (raw.get("steps") if isinstance(raw.get("steps"), list) else []) if isinstance(st, dict)
    ]
    return {"why": str(raw.get("why") or "").strip(), "evidence": str(raw.get("evidence") or "").strip(),
            "strength": str(raw.get("strength") or "").strip(), "steps": steps, "check": str(raw.get("check") or "").strip()}


def check_support_plan(plan, sub, all_subs, rubric, outcomes):
    """Problems with a catch-up plan, checked in code before a teacher is shown it."""
    by_id = {o["id"]: o for o in outcomes}
    problems = []
    if len(plan["why"].split()) < 6:
        problems.append("does not explain why the learner is behind")
    steps = plan["steps"]
    if len(steps) != 3:
        problems.append(f"has {len(steps)} steps (expected 3)")
    for n, st in enumerate(steps, 1):
        if st["outcome"] not in by_id:
            problems.append(f"step {n} names an outcome that is not on the list ({st['outcome'] or 'none'})")
        if len(st["activity"].split()) < 6:
            problems.append(f"step {n} does not say what to do")
        if not 5 <= st["minutes"] <= 45:
            problems.append(f"step {n} takes {st['minutes']} minutes (expected 5 to 45)")
    if sub["final"]:
        weakest = weakest_criterion(sub["final"], rubric)
        if not any(weakest["id"] in by_id.get(st["outcome"], {}).get("criteria", []) for st in steps):
            problems.append(f"has no step for the learner's weakest area ({weakest['name']})")
        if not quote_in_text(plan["evidence"], sub["text"]):
            problems.append("quotes evidence that does not appear in the learner's essay")
    text = " ".join([plan["why"], plan["strength"], plan["check"]] + [st["activity"] for st in steps])
    first = sub["learner"].split()[0]
    for other in all_subs:
        name = other["learner"].split()[0]
        if other["id"] != sub["id"] and name != first and re.search(rf"\b{re.escape(name)}\b", text):
            problems.append(f"mentions another learner ({name})")
    return problems


def write_support_plans(out_dir, entries, outcomes, evidence="In the learner's words"):
    """The catch-up plans, as one document for the teacher. A plan that failed its checks is named, not included."""
    by_id = {o["id"]: o["text"] for o in outcomes}
    lines = ["# Learners who need support\n", "Spotted from the marks by fixed rules. Each plan was checked before it was written here.\n"]
    for e in entries:
        lines.append(f"\n## {e['id']} {e['learner']}\n")
        lines.append("Warning signs: " + "; ".join(s["text"] for s in e["signs"]) + "\n")
        if e["status"] != "ready":
            lines.append("No plan is offered: the draft failed its checks (" + "; ".join(e["problems"]) + "). This one needs you.\n")
            continue
        p = e["plan"]
        lines.append(f"Why: {p['why']}\n")
        if p["evidence"]:
            lines.append(f"{evidence}: \"{p['evidence']}\"\n")
        if p["strength"]:
            lines.append(f"Build on: {p['strength']}\n")
        lines.append("This week:")
        lines += [f"{n}. {st['activity']} ({st['minutes']} min. Outcome {st['outcome']}: {by_id.get(st['outcome'], '')})"
                  for n, st in enumerate(p["steps"], 1)]
        lines.append(f"\nCheck in a week: {p['check']}\n")
    path = Path(out_dir) / "support_plans.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---- the next lesson ----------------------------------------------------------------------

EXERCISE_LEVELS = ("support", "core", "extension")
NOTHING_WRONG = re.compile(r"^(none|no|nil|n/?a|ok|fine|no problems?|nothing)?[.\s-]*$", re.I)


def clean_exercise(raw, default_id):
    raw = raw if isinstance(raw, dict) else {}
    return {"id": str(raw.get("id") or default_id).strip(), "outcome": str(raw.get("outcome") or "").strip(),
            "level": str(raw.get("level") or "").strip().lower(), "task": str(raw.get("task") or "").strip(),
            "answer": str(raw.get("answer") or "").strip(),
            # status: unchecked, then ok, fixed (failed a check, was rewritten, then passed) or dropped.
            # check: what the Reviewer made of it when shown only the task.
            "status": "unchecked", "check": None, "problems": []}


def clean_lesson(raw, minutes):
    """A Designer's reply as a predictable structure. The lesson length is the teacher's, not the model's."""
    raw = raw if isinstance(raw, dict) else {}
    rows = lambda key: [x for x in (raw.get(key) if isinstance(raw.get(key), list) else []) if isinstance(x, dict)]
    return {
        "title": str(raw.get("title") or "Next lesson").strip(), "minutes": minutes, "why": str(raw.get("why") or "").strip(),
        "outcomes": [str(x).strip() for x in (raw.get("outcomes") if isinstance(raw.get("outcomes"), list) else [])],
        "phases": [{"name": str(p.get("name") or "").strip(), "minutes": _int(p.get("minutes")),
                    "teacher": str(p.get("teacher") or "").strip(), "learners": str(p.get("learners") or "").strip()} for p in rows("phases")],
        "exercises": [clean_exercise(e, f"X{n}") for n, e in enumerate(rows("exercises"), 1)],
        "exit_ticket": str(raw.get("exit_ticket") or "").strip(),
    }


def check_exercise(ex, lesson_outcomes):
    """Problems with one exercise that plain code can see."""
    problems = []
    if ex["outcome"] not in lesson_outcomes:
        problems.append(f"it is labelled {ex['outcome'] or 'with no outcome'}, which is not one of the lesson's outcomes")
    if ex["level"] not in EXERCISE_LEVELS:
        problems.append("it has no level (support, core or extension)")
    if len(ex["task"].split()) < 8:
        problems.append("it does not give the learner enough to work on")
    if not ex["answer"]:
        problems.append("it has no model answer")
    return problems


def check_lesson(lesson, outcomes, weakest, minutes):
    """Problems with a lesson that plain code can find. Returns (problems with the lesson, {exercise id: problems}).

    Dropped exercises are ignored, so this also says whether a lesson still stands after losing some.
    """
    by_id = {o["id"]: o for o in outcomes}
    problems = []
    unknown = [x for x in lesson["outcomes"] if x not in by_id]
    if unknown:
        problems.append(f"names outcomes that are not on the list ({', '.join(unknown)})")
    chosen = [x for x in lesson["outcomes"] if x in by_id]
    if not 1 <= len(chosen) <= 3:
        problems.append(f"targets {len(chosen)} outcomes (expected 1 to 3)")
    elif not any(weakest["id"] in by_id[x]["criteria"] for x in chosen):
        problems.append(f"does not target the class's weakest area ({weakest['name']})")
    total = sum(p["minutes"] for p in lesson["phases"])
    if len(lesson["phases"]) < 3:
        problems.append("has fewer than three phases")
    if total != minutes:
        problems.append(f"has phases that add up to {total} minutes, not {minutes}")
    exercises = [ex for ex in lesson["exercises"] if ex["status"] != "dropped"]
    if not 3 <= len(exercises) <= 8:
        problems.append(f"has {len(exercises)} usable exercises (expected 3 to 8)")
    per, seen = {}, set()
    for ex in exercises:
        bad = check_exercise(ex, chosen) + (["it shares its id with another exercise"] if ex["id"] in seen else [])
        seen.add(ex["id"])
        if bad:
            per[ex["id"]] = bad
    for x in chosen:
        if not any(ex["outcome"] == x for ex in exercises):
            problems.append(f"has no exercise for outcome {x}")
    levels = {ex["level"] for ex in exercises}
    for level, who in (("support", "for learners who are behind"), ("core", "for the whole class")):
        if level not in levels:
            problems.append(f"has no {level} exercise {who}")
    return problems, per


def blind_check(ex, attempt, outcomes):
    """Hold an exercise's label against what a reviewer made of it when shown only the task.

    Returns (the reviewer's attempt, tidied; problems). An exercise passes when the reviewer could do
    it and, without being told, named the same outcome the designer claimed.
    """
    ids = {o["id"] for o in outcomes}
    seen = isinstance(attempt, dict)
    attempt = attempt if seen else {}
    guess = str(attempt.get("outcome") or "").strip()
    trouble = str(attempt.get("problem") or "").strip()
    check = {"outcome": guess, "answer": str(attempt.get("answer") or "").strip(),
             "problem": "" if NOTHING_WRONG.match(trouble) else trouble}
    problems = []
    if not seen:
        problems.append("the Reviewer returned no attempt at it")
    elif guess not in ids:
        problems.append(f"the Reviewer could not match it to an outcome on the list ({guess or 'none given'})")
    elif guess != ex["outcome"]:
        problems.append(f"it is labelled {ex['outcome']}, but the Reviewer, who was not shown the label, judged that it practises {guess}")
    if check["problem"]:
        problems.append(f"the Reviewer could not do it as written: {check['problem']}")
    return check, problems


def _and(items):
    """'E02', 'E02 and E10', or 'E02, E04 and E10'."""
    items = list(items)
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def consistency_issues(learners, lesson, outcomes, rubric):
    """Where the Coach's catch-up plans and the Designer's lesson disagree.

    Two checks, both in code. The lesson's support exercises (the work for learners who are behind) must
    cover every weakness the marks diagnosed. Every step of a ready plan must name a lesson outcome, an
    exercise's outcome, or an outcome on the list. Returns lesson problems (for the Designer), plan problems
    keyed by learner (for the Coach), the coverage of each diagnosed weakness, and where each step maps.
    """
    by_id = {o["id"]: o for o in outcomes}
    names = {c["id"]: c["name"] for c in rubric["criteria"]}
    kept = [ex for ex in (lesson.get("exercises") or []) if ex.get("status") != "dropped"]
    lesson_outcomes = [x for x in (lesson.get("outcomes") or []) if x in by_id]
    exercise_outcomes = {ex.get("outcome") for ex in kept}
    covered_by = {}
    for ex in kept:
        if ex.get("level") != "support":
            continue
        for criterion in by_id.get(ex.get("outcome"), {}).get("criteria", []):
            covered_by.setdefault(criterion, ex)

    diagnosed = {}
    for entry in learners or []:
        found = []
        weakest = entry.get("weakest") or {}
        if weakest.get("id"):
            found.append(weakest["id"])
        for sign in entry.get("signs") or []:
            if sign.get("kind") == "weak_area" and sign.get("criterion"):
                found.append(sign["criterion"])
        for criterion in dict.fromkeys(found):
            diagnosed.setdefault(criterion, []).append(entry["id"])

    coverage, lesson_problems = [], []
    for criterion, who in diagnosed.items():
        exercise = covered_by.get(criterion)
        coverage.append({
            "id": criterion, "name": names.get(criterion, criterion), "learners": who,
            "exercise": exercise["id"] if exercise else None, "outcome": exercise["outcome"] if exercise else None,
        })
        if not exercise:
            lesson_problems.append(
                "has no support exercise for " + names.get(criterion, criterion)
                + ", which the Coach diagnosed for " + _and(who))

    steps, plan_problems = [], {}
    for entry in learners or []:
        plan = entry.get("plan")
        if entry.get("status") != "ready" or not plan:
            continue
        for n, step in enumerate(plan.get("steps") or [], 1):
            outcome = step.get("outcome") or ""
            if outcome in lesson_outcomes:
                where = "lesson"
            elif outcome in exercise_outcomes:
                where = "exercise"
            elif outcome in by_id:
                where = "outcomes"
            else:
                where = "none"
            steps.append({"id": entry["id"], "n": n, "outcome": outcome, "where": where})
            if where == "none":
                plan_problems.setdefault(entry["id"], []).append(
                    f"step {n} names {outcome or 'no outcome'}, which is not a lesson outcome, not an exercise, and not on the outcomes list")
    return {"lesson": lesson_problems, "plans": plan_problems, "coverage": coverage, "steps": steps}


def write_lesson_plan(out_dir, lesson, outcomes):
    by_id = {o["id"]: o["text"] for o in outcomes}
    lines = [f"# {lesson['title']}\n",
             f"{lesson['minutes']} minutes. Targets the class's weakest area: {lesson['target']['name']} ({lesson['target']['pct']}%).\n"]
    if lesson["why"]:
        lines.append(f"{lesson['why']}\n")
    lines.append("## Learning outcomes\n")
    lines += [f"- {x}: {by_id.get(x, '')}" for x in lesson["outcomes"]]
    lines.append("\n## Lesson\n")
    lines += [f"- **{p['name']}** ({p['minutes']} min). Teacher: {p['teacher']} Learners: {p['learners']}" for p in lesson["phases"]]
    lines.append("\n## Exercises\n")
    kept = [ex for ex in lesson["exercises"] if ex["status"] != "dropped"]
    lines += [f"**{ex['id']}** ({ex['level']}, outcome {ex['outcome']})\n\n{ex['task']}\n" for ex in kept]
    if lesson["exit_ticket"]:
        lines.append(f"## Exit ticket\n\n{lesson['exit_ticket']}\n")
    lines.append("## Model answers\n")
    lines += [f"- **{ex['id']}**: {ex['answer']}" for ex in kept]
    path = Path(out_dir) / "lesson_plan.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---- the PC assembly practical ------------------------------------------------------------------

def _clock(seconds):
    return f"{seconds // 60}:{seconds % 60:02d}"


def clean_attempt(raw, parts):
    """An attempt file as a predictable structure. Unknown parts are kept as written, so the log shows them."""
    raw = raw if isinstance(raw, dict) else {}
    tried = [str(p).strip() for p in raw.get("order_tried") or [] if str(p).strip()] if isinstance(raw.get("order_tried"), list) else []
    wrong = [{"part": str(w.get("part") or "").strip(), "expected": str(w.get("expected") or "").strip(), "t": max(0, _int(w.get("t")))}
             for w in (raw.get("wrong_placements") if isinstance(raw.get("wrong_placements"), list) else []) if isinstance(w, dict)]
    return {"learner_id": str(raw.get("learner_id") or "").strip(), "order_tried": tried, "wrong_placements": wrong,
            "mistakes": max(0, _int(raw.get("mistakes"))), "hints": max(0, _int(raw.get("hints"))),
            "completed": raw.get("completed") is True, "duration_seconds": max(0, _int(raw.get("duration_seconds")))}


def attempt_steps(attempt, parts):
    """Replay an attempt against the correct order: [(step, part, expected or None if right, seconds or None)]."""
    times = [dict(w) for w in attempt["wrong_placements"]]
    steps, done = [], 0
    for n, part in enumerate(attempt["order_tried"], 1):
        expected = parts[done] if done < len(parts) else None
        if expected and part.lower() == expected.lower():
            steps.append((n, expected, None, None))
            done += 1
            continue
        hit = next((w for w in times if w["part"].lower() == part.lower()), None)
        if hit:
            times.remove(hit)
        steps.append((n, part, expected or "the end of the build", hit["t"] if hit else None))
    return steps


def attempt_facts(attempt, parts):
    """What the log shows, counted in code: the facts the mark ceilings are built from."""
    steps = attempt_steps(attempt, parts)
    installed = sum(1 for s in steps if s[2] is None)
    wrong = sum(1 for s in steps if s[2] is not None)
    return {"installed": installed, "parts": len(parts), "wrong": max(wrong, len(attempt["wrong_placements"])),
            "mistakes": max(attempt["mistakes"], wrong), "slot_misses": max(0, attempt["mistakes"] - wrong), "hints": attempt["hints"],
            "completed": attempt["completed"] and installed == len(parts), "seconds": attempt["duration_seconds"]}


def render_attempt(attempt, rubric):
    """An attempt as the plain-text log the Marker and Reviewer read, and quote evidence from word for word."""
    parts = rubric["parts"]
    facts = attempt_facts(attempt, parts)
    target = rubric["limits"]["target_seconds"]
    lines = [
        "PC assembly practical: attempt log",
        f"Finished: {'yes' if facts['completed'] else 'no'}. Installed: {facts['installed']} of {facts['parts']} parts.",
        f"Mistakes: {facts['mistakes']} ({facts['wrong']} part{'' if facts['wrong'] == 1 else 's'} tried out of order, "
        f"{facts['slot_misses']} dropped outside {'its' if facts['slot_misses'] == 1 else 'their'} slot). Hints used: {facts['hints']}.",
        f"Time taken: {facts['seconds']} seconds ({_clock(facts['seconds'])}), against a target of {target} seconds.",
        "Correct order: " + ", ".join(parts) + ".",
        "",
        "Step by step:",
    ]
    for n, part, expected, t in attempt_steps(attempt, parts):
        if expected is None:
            lines.append(f"{n}. Right: installed the {part}.")
        else:
            at = f" at {_clock(t)}" if t is not None else ""
            lines.append(f"{n}. Wrong: placed the {part} before the {expected}{at}. It was taken out again.")
    missing = parts[facts["installed"]:]
    if missing:
        lines.append("Not installed when the learner stopped: " + ", ".join(missing) + ".")
    return "\n".join(lines)


def _read_attempts(folder, parts):
    found = {}
    for path in sorted(Path(folder).glob("*.json")) if folder and Path(folder).is_dir() else []:
        try:
            attempt = clean_attempt(json.loads(path.read_text(encoding="utf-8-sig")), parts)
        except (ValueError, UnicodeDecodeError):
            continue
        found[attempt["learner_id"] or path.stem] = attempt
    return found


def load_attempts(data_dir, subs, rubric, live_dir=None):
    """Give each learner their PC assembly attempt as the work to mark: data/attempts/<learner id>.json, or the
    attempt recorded live in the dashboard's virtual lab (live_dir), which takes its place.

    A learner with no attempt has nothing to mark, exactly like a learner who handed in no essay. The essay
    marks in class.csv say nothing about this practical, so there is no previous mark to compare with.
    """
    found = _read_attempts(Path(data_dir) / "attempts", rubric["parts"])
    live = _read_attempts(live_dir, rubric["parts"])
    for s in subs:
        attempt = live.get(s["id"]) or found.get(s["id"])
        text = render_attempt(attempt, rubric) if attempt else ""
        source = None if not attempt else "live" if s["id"] in live else "practical"
        s.update(text=text, words=len(text.split()), previous=None, source=source,
                 attempt=attempt_facts(attempt, rubric["parts"]) if attempt else None)
    return subs


def check_attempt(raw, subs, rubric):
    """Problems with an attempt sent from the virtual lab, found in code before it is kept. Returns (attempt, problems).

    The record must replay: the out-of-order tries it lists must be the ones its order of placements shows,
    its mistakes must cover them, and it can only claim to be finished if all six parts went in.
    """
    parts = rubric["parts"]
    problems = []
    if not isinstance(raw, dict):
        return None, ["the attempt is not a JSON object"]
    attempt = clean_attempt(raw, parts)
    if attempt["learner_id"] not in {s["id"] for s in subs}:
        problems.append(f"learner {attempt['learner_id'] or '(none)'} is not on the class list")
    unknown = sorted({p for p in attempt["order_tried"] if p.lower() not in {q.lower() for q in parts}})
    if unknown:
        problems.append("it names parts that are not in the practical: " + ", ".join(unknown))
    replayed = [(part, expected) for _, part, expected, _ in attempt_steps(attempt, parts) if expected is not None]
    listed = [(w["part"], w["expected"]) for w in attempt["wrong_placements"]]
    if [(p.lower(), e.lower()) for p, e in replayed] != [(p.lower(), e.lower()) for p, e in listed]:
        problems.append(f"its wrong placements ({len(listed)}) do not match the order of placements, which shows {len(replayed)}")
    if attempt["mistakes"] < len(listed):
        problems.append(f"it counts {attempt['mistakes']} mistakes but lists {len(listed)} wrong placements")
    facts = attempt_facts(attempt, parts)
    if raw.get("completed") is True and facts["installed"] < len(parts):
        problems.append(f"it says it was finished, but only {facts['installed']} of {len(parts)} parts went in")
    if not 0 < attempt["duration_seconds"] <= 4 * 3600:
        problems.append("its time taken is missing or impossible")
    return attempt, problems


def practical_ceilings(rubric, facts):
    """The most each criterion can earn on what the log shows: {criterion id: (ceiling, why)}."""
    limits, out = rubric.get("limits") or {}, {}
    by = {c["id"]: c for c in rubric["criteria"]}
    if "order" in by:
        c = by["order"]
        cut = limits.get("order_penalty", 3) * facts["wrong"]
        out["order"] = (max(0, c["max"] - cut), f"{facts['wrong']} wrong placement{'' if facts['wrong'] == 1 else 's'} in the log")
    if "correctness" in by and not facts["completed"]:
        c = by["correctness"]
        out["correctness"] = (round(c["max"] * facts["installed"] / facts["parts"]),
                              f"only {facts['installed']} of {facts['parts']} parts were installed")
    if "efficiency" in by:
        c = by["efficiency"]
        ceiling, why = c["max"] - limits.get("hint_penalty", 2) * facts["hints"], [f"{facts['hints']} hint{'' if facts['hints'] == 1 else 's'} used"]
        slow = limits.get("target_seconds", 240) * limits.get("slow_factor", 2)
        if facts["seconds"] > slow:
            ceiling = min(ceiling, round(c["max"] * limits.get("slow_cap_pct", 50) / 100))
            why.append(f"{facts['seconds']} seconds is more than twice the target")
        out["efficiency"] = (max(0, ceiling), " and ".join(why))
    return out


def check_practical(mark, rubric, facts):
    """Problems with a practical mark that the attempt log rules out, found in code."""
    problems = []
    for c in rubric["criteria"]:
        ceiling = practical_ceilings(rubric, facts).get(c["id"])
        score = mark["scores"][c["id"]]["score"]
        if ceiling and score > ceiling[0]:
            problems.append(f"{c['name']}: {score} is more than the attempt log allows (at most {ceiling[0]}, since {ceiling[1]}).")
    return problems


# ---- handwritten scripts (the Clerk) ------------------------------------------------------------

READ_RULES = {"min_confidence": 0.75, "max_unreadable": 0.05, "line_slack": 0.15}
UNREADABLE = "[?]"


def _page_number(value):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() and 0 < number < 1000 else None


def written_lines(text):
    """Lines that carry writing: blank lines between paragraphs do not count."""
    return sum(1 for line in str(text).splitlines() if line.strip())


def clean_read(raw):
    """A Clerk's reading of one page as a predictable structure, whatever the model left out or mistyped."""
    raw = raw if isinstance(raw, dict) else {}
    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence != confidence:  # NaN
        confidence = 0.0
    if 1 < confidence <= 100:  # given as a percentage
        confidence /= 100
    text = "\n".join(line.rstrip() for line in str(raw.get("text") or "").replace("\r\n", "\n").split("\n")).strip()
    problem = str(raw.get("problem") or "").strip()
    words = text.split()
    return {
        "name": " ".join(str(raw.get("name") or "").split()),
        "page": _page_number(raw.get("page")), "of": _page_number(raw.get("of")),
        "lines": max(0, _int(raw.get("lines"))), "text": text,
        "confidence": round(max(0.0, min(1.0, confidence)), 2),
        "problem": "" if NOTHING_WRONG.match(problem) else problem,
        "words": len(words), "unreadable": sum(UNREADABLE in w for w in words),
    }


def check_read(read):
    """Problems with one page's transcript that plain code can see. An empty list means the read stands."""
    problems = []
    if read["problem"]:
        said = read["problem"].rstrip(".")
        problems.append(f"the Clerk reported a problem reading it ({said[:1].lower()}{said[1:]})")
    if not read["text"]:
        return problems + ["no text was read from the page"]
    if read["confidence"] < READ_RULES["min_confidence"]:
        problems.append(f"the Clerk is only {round(100 * read['confidence'])}% sure of the transcript "
                        f"({round(100 * READ_RULES['min_confidence'])}% is needed)")
    if read["words"] and read["unreadable"] / read["words"] > READ_RULES["max_unreadable"]:
        problems.append(f"{read['unreadable']} of its {read['words']} words could not be read")
    seen, got = read["lines"], written_lines(read["text"])
    if seen and abs(got - seen) > max(2, round(seen * READ_RULES["line_slack"])):
        problems.append(f"the transcript has {got} lines but the page has {seen} lines of writing, so "
                        + ("some lines may have been skipped" if got < seen else "lines may have been repeated or made up"))
    return problems


def edit_distance(a, b):
    """Letters to add, remove or change to turn one string into the other."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def match_learner(name, subs):
    """The one learner on the class list with exactly this name (case and punctuation aside), or None."""
    key = _norm(name)
    hits = [s for s in subs if key and _norm(s["learner"]) == key]
    return hits[0] if len(hits) == 1 else None


def close_learners(name, subs, limit=3):
    """Learners whose names are close to one that is not on the class list: a likely misreading, or a nickname."""
    key = _norm(name)
    if not key:
        return []
    found = []
    for s in subs:
        other = _norm(s["learner"])
        d = edit_distance(key, other)
        if d <= max(2, len(other) // 4) or key.split()[-1] == other.split()[-1]:
            found.append((d, s))
    found.sort(key=lambda pair: pair[0])
    return [{"id": s["id"], "learner": s["learner"]} for _, s in found[:limit]]


def group_pages(pages):
    """Sort photographed pages into scripts. pages: [{id, read}] in the order they were photographed.

    A page carrying a name joins the script with that name, wherever it was photographed. A page with no name
    continues the script of the page before it, unless that script already has a page with its number. A page
    with nothing read on it at all stands alone, so it cannot spoil a good script. Pages are then put in
    page-number order. Returns [{key, name, pages: [page id], reordered}].
    """
    by = {p["id"]: p["read"] for p in pages}
    scripts, last = [], None
    for p in pages:
        read = p["read"]
        key = _norm(read["name"])
        if key:
            target = next((s for s in scripts if s["key"] == key), None)
        else:
            n = read["page"]
            continues = n is not None and all(by[q]["page"] != n for q in last["pages"]) if last else False
            fits = last is not None and (continues or (n is None and bool(read["text"])))
            target = last if fits else None
        if target is None:
            target = {"key": key, "name": read["name"], "pages": []}
            scripts.append(target)
        target["pages"].append(p["id"])
        last = target
    for s in scripts:
        order = sorted(s["pages"], key=lambda q: (by[q]["page"] is None, by[q]["page"] or 0))
        s["reordered"], s["pages"] = order != s["pages"], order
    return scripts


def check_script(script, reads, subs):
    """Whose script this is, and problems with it as a whole. reads: {page id: clean read}. Returns (learner, problems)."""
    problems = []
    name = script["name"]
    learner = match_learner(name, subs) if name else None
    if not name:
        problems.append("no learner's name can be read on any of its pages")
    elif not learner:
        problems.append(f"the name “{name}” is not on the class list")
    nums = [reads[q]["page"] for q in script["pages"]]
    ofs = sorted({reads[q]["of"] for q in script["pages"] if reads[q]["of"]})
    numbered = [n for n in nums if n]
    if len(ofs) > 1:
        problems.append("its pages disagree on how many pages there are (" + ", ".join(f"of {o}" for o in ofs) + ")")
    if numbered or ofs:
        total = max(ofs) if ofs else max(numbered)
        for n in range(1, total + 1):
            count = numbered.count(n)
            if not count:
                problems.append(f"page {n} of {total} is missing")
            elif count > 1:
                problems.append(f"page {n} appears {count} times")
        for n in sorted(set(numbered)):
            if n > total:
                problems.append(f"page {n} is numbered beyond the {total} pages it says there are")
        if len(numbered) < len(nums):
            missing = len(nums) - len(numbered)
            problems.append(f"{missing} of its pages {'carries' if missing == 1 else 'carry'} no page number")
    return learner, problems


def script_text(texts):
    """The essay as a marker reads it: each paragraph on one line, as in a typed essay, pages in order."""
    paragraphs = []
    for text in texts:
        for block in re.split(r"\n\s*\n", text):
            joined = " ".join(line.strip() for line in block.splitlines() if line.strip())
            if joined:
                paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def write_clerk_report(out_dir, intake):
    """What the Clerk read on every page, what the checks found, and what became of each script."""
    pages = {p["id"]: p for p in intake["pages"]}
    lines = ["# Handwritten scripts\n",
             f"{len(intake['pages'])} photographed pages read by the Clerk. Every page was checked in code: its "
             f"confidence (at least {round(100 * READ_RULES['min_confidence'])}%), unreadable words (at most "
             f"{round(100 * READ_RULES['max_unreadable'])}%), the lines transcribed against the lines on the page, the "
             "name against the class list, and the page numbers. A page that failed was read once more; a script "
             "that still failed was held for the teacher.\n"]
    if intake.get("summary"):
        lines.append(intake["summary"] + "\n")
    lines.append("## Scripts\n")
    for s in intake["scripts"]:
        who = f"{s['learner']} {s['learner_name']}" if s["learner"] else f"Unknown learner (name read as “{s['name'] or 'nothing'}”)"
        state = {"accepted": "Accepted", "held": "Held for the teacher", "set_aside": "Set aside by the teacher"}.get(s["status"], s["status"])
        lines.append(f"### {s['id']}: {who}\n")
        lines.append(f"{state}. {len(s['pages'])} page{'' if len(s['pages']) == 1 else 's'} ({', '.join(s['pages'])}), {s['words']} words."
                     + (" Decided by the teacher." if s.get("decided") else "") + "\n")
        if s["problems"]:
            lines.append("Why it was held: " + "; ".join(s["problems"]) + ".\n")
    lines.append("## Pages\n")
    lines.append("| Page | Photo | Read as | Lines | Words | Sure | Re-read | Outcome |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for pid in [p["id"] for p in intake["pages"]]:
        p = pages[pid]
        r = p["read"]
        label = (r["name"] or "no name") + (f", page {r['page']}" if r["page"] else "") + (f" of {r['of']}" if r["of"] else "")
        reread = ("yes: " + "; ".join(p["first_problems"])) if p["reads"] > 1 else "no"
        outcome = "; ".join(p["problems"]) if p["problems"] else "passed its checks"
        lines.append(f"| {pid} | {p['original']} | {label} | {written_lines(r['text'])}/{r['lines']} | {r['words']} | "
                     f"{round(100 * r['confidence'])}% | {reread} | {outcome} |")
    path = Path(out_dir) / "scripts" / "clerk_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
