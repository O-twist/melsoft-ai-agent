"""How we corrected ourselves: the run's self-corrections, built from its log.

Every time a check sent work back, the log says so (REJECT), and later says how it ended: fixed (FIX, then
APPROVE or a passing check), held for the teacher (ESCALATE), dropped (DROP) or decided by the teacher
(HUMAN). This module walks the log in order and ties those lines together into one story per piece of work:
what was wrong, who caught it, how it was caught, who fixed it, and how it ended. A planted fault (TEST) is
attached to the story it started, and a code guard (GUARD) is a story of its own: something code stopped.

Nothing here asks a model. It reads the log, plus the run's state where the log alone cannot say which pages
make up a handwritten script.
"""
import re

WHO = {"PL": "Planner", "CL": "Clerk", "MK": "Marker", "RV": "Reviewer", "MS": "Messenger", "CO": "Coach", "DS": "Designer"}

# How a problem was caught, from the words the checks use. Code checks first: they are the ones no model can talk past.
METHODS = [
    (r"more than the attempt log allows", "code check against the attempt log"),
    (r"quoted evidence does not appear", "code check that the quoted evidence is really there"),
    (r"no mark was given|is outside 0-|is not a number", "code check of the mark itself"),
    (r"the Reviewer gave", "blind second mark"),
    (r"judged that it practises|could not do it as written|could not match it to an outcome", "blind trial by the Reviewer"),
    (r"^Feedback draft rejected", "code check of the message"),
    (r"^Catch-up plan rejected", "code check of the plan"),
    (r"^Lesson draft rejected", "code check of the lesson's structure"),
    (r"^Sent back to the Designer: the lesson|^Catch-up plan sent back to the Coach|support work did not hold up",
     "cross-check of the catch-up plans against the lesson"),
    (r"fails its checks: .*lines of writing", "code check of the lines transcribed against the lines on the page"),
    (r"fails its checks: .*not on the class list", "code check of the name against the class list"),
    (r"fails its checks: .*(is missing|appears \d+ times|disagree on how many|page number)", "code check of the page numbers"),
    (r"fails its checks: .*(sure of the transcript|could not be read|no text was read|reported a problem)",
     "code check of how clearly the page was read"),
]


def _methods(msg):
    found = [label for pattern, label in METHODS if re.search(pattern, msg, re.S)]
    return found or ["a check in code"]


def _subject(e, page_script):
    """Which piece of work a log line is about, as (key, label, learner id or None). None if it is about none."""
    msg, agent, sid = e["msg"], e["agent"], e.get("sid")
    if agent == "CL":
        m = re.match(r"(p\d{2,3})\b", msg)
        if m:
            return f"page:{m.group(1)}", f"Page {m.group(1)} of the handwritten scripts", None
        m = re.match(r"Script (S\d+)\b", msg)
        if m:
            return f"script:{m.group(1)}", f"Handwritten script {m.group(1)}", sid
        return None
    if e["kind"] == "TEST" and "transcript" in msg:
        m = re.search(r"\b(p\d{2,3})'s transcript", msg)
        return (f"page:{m.group(1)}", f"Page {m.group(1)} of the handwritten scripts", None) if m else None
    if e["kind"] == "HUMAN" and "handwritten script" in msg:
        m = re.search(r"handwritten script (S\d+)", msg)
        return (f"script:{m.group(1)}", f"Handwritten script {m.group(1)}", sid) if m else None
    if re.search(r"catch-up plans and the lesson|^Sent back to the Designer: the lesson|support work|Coach's diagnoses|"
                 r"The revision does not pass|previous lesson stands", msg):
        return "align", "The catch-up plans and the lesson", None
    if re.search(r"^Catch-up plan|^Catch-up steps|catch-up steps|The revised plan", msg) and sid:
        return f"plan:{sid}", f"{sid}: catch-up plan", sid
    if re.search(r"^Feedback", msg) and sid:
        return f"feedback:{sid}", f"{sid}: feedback message", sid
    m = re.search(r"\b(?:[Ee]xercise|Reworking) (X\d+)\b", msg)
    if m and agent in ("RV", "DS", "PL"):
        return f"exercise:{m.group(1)}", f"Exercise {m.group(1)} in the lesson", None
    if re.search(r"^Lesson draft|^The lesson does not stand|^Draft passes its structure checks", msg):
        return "lesson", "The lesson draft", None
    if sid and agent in ("RV", "MK", "PL"):
        return f"mark:{sid}", f"{sid}: mark", sid
    return None


def _scripts_pages(intake):
    """{script id: [page ids]} and {page id: script id}, from the Clerk's work."""
    scripts = {s["id"]: list(s["pages"]) for s in (intake or {}).get("scripts", [])}
    return scripts, {p: sid for sid, pages in scripts.items() for p in pages}


def corrections(events, intake=None, support=None, subs=None):
    """The run's self-corrections as stories, oldest first, with a count of how each ended."""
    scripts, page_script = _scripts_pages(intake)
    stories, open_by_key, planted = [], {}, {}

    def close(story, outcome, e=None):
        if story["outcome"] == "open":
            story["outcome"] = outcome
            if e and e["kind"] == "FIX" and not story["fixed_by"]:
                story["fixed_by"] = WHO.get(e["agent"], e["agent"])

    for e in events:
        kind = e["kind"]
        if kind == "GUARD":
            stories.append({
                "key": f"guard:{len(stories)}", "subject": f"{e['sid']}: what the plan left out" if e.get("sid") else "The lesson's outcomes",
                "sid": e.get("sid"), "caught_by": WHO.get(e["agent"], e["agent"]), "how": ["a code guard"], "problem": e["msg"],
                "planted": None, "fixed_by": None, "outcome": "prevented", "steps": [_step(e)], "t": e["t"],
            })
            continue
        if kind not in ("TEST", "REJECT", "FIX", "APPROVE", "ESCALATE", "DROP", "HUMAN", "INFO"):
            continue
        found = _subject(e, page_script)
        if not found:
            continue
        key, label, sid = found
        if kind == "TEST":
            planted[key] = e
            continue
        # a script's verdict, or the teacher's decision on it, settles the stories of its pages
        keys = [f"page:{p}" for p in scripts.get(key.split(":", 1)[1], [])] if key.startswith("script:") else [key]
        if kind == "REJECT":
            story = open_by_key.get(key)
            if story and story["outcome"] == "open":
                story["steps"].append(_step(e))  # a second objection in the same story, such as the revision failing too
                story["how"] += [m for m in _methods(e["msg"]) if m not in story["how"]]
                continue
            fault = planted.pop(key, None)
            story = {"key": key, "subject": label, "sid": sid, "caught_by": WHO.get(e["agent"], e["agent"]),
                     "how": _methods(e["msg"]), "problem": e["msg"], "planted": fault["msg"] if fault else None,
                     "fixed_by": None, "outcome": "open", "steps": ([_step(fault)] if fault else []) + [_step(e)], "t": e["t"]}
            stories.append(story)
            open_by_key[key] = story
            continue
        for k in keys:
            story = open_by_key.get(k)
            if not story or (story["outcome"] != "open" and kind != "HUMAN"):
                continue
            if kind == "INFO" and not re.search(r"passes its checks|passes its structure checks", e["msg"]):
                continue
            if kind == "APPROVE" and k.startswith("exercise:") and "now holds up" not in e["msg"]:
                continue
            story["steps"].append(_step(e))
            if kind == "FIX":
                story["fixed_by"] = story["fixed_by"] or WHO.get(e["agent"], e["agent"])
            elif kind in ("APPROVE", "INFO"):
                close(story, "fixed")
            elif kind == "ESCALATE":
                close(story, "held")
            elif kind == "DROP":
                close(story, "dropped")
            elif kind == "HUMAN":
                story["outcome"] = "teacher"

    # Some fixes end quietly: a feedback message that passes on its second try is simply sent. Settle those from
    # the run's state, which says what was finally held.
    held_plans = {e["id"] for e in (support or {}).get("learners", []) if e.get("status") == "held"}
    by_sub = {s["id"]: s for s in subs or []}
    for story in stories:
        if story["outcome"] != "open":
            continue
        kind, _, ident = story["key"].partition(":")
        if kind == "feedback":
            issue = (by_sub.get(ident) or {}).get("issue") or ""
            story["outcome"] = "held" if "feedback message failed" in issue else "fixed"
        elif kind == "plan":
            story["outcome"] = "held" if ident in held_plans else "fixed"
        elif kind == "page":
            script = next((s for s in (intake or {}).get("scripts", []) if s["id"] == page_script.get(ident)), None)
            story["outcome"] = {"accepted": "fixed", "held": "held", "set_aside": "teacher"}.get((script or {}).get("status"), "open")
    for story in stories:
        story.pop("key")
    counts = {}
    for story in stories:
        counts[story["outcome"]] = counts.get(story["outcome"], 0) + 1
    return {"stories": stories, "counts": counts, "planted": sum(1 for s in stories if s["planted"])}


def _step(e):
    return {"t": e["t"], "agent": e["agent"], "kind": e["kind"], "msg": e["msg"]}


OUTCOME = {"fixed": "Fixed", "held": "Held for the teacher", "dropped": "Dropped", "teacher": "Decided by the teacher",
           "prevented": "Stopped by code", "open": "Still open"}


def to_markdown(story, where=""):
    """The stories as a document for the teacher."""
    stories, counts = story["stories"], story["counts"]
    lines = ["# How we corrected ourselves\n"]
    if not stories:
        lines.append("Every check passed first time in this run: nothing had to be sent back.\n")
    else:
        tally = ", ".join(f"{n} {OUTCOME[k].lower()}" for k, n in counts.items())
        lines.append(f"{len(stories)} time{'' if len(stories) == 1 else 's'} a check stopped work in this run: {tally}."
                     + (f" {story['planted']} of them began with a fault planted on purpose." if story["planted"] else "") + "\n")
    for n, s in enumerate(stories, 1):
        lines.append(f"## {n}. {s['subject']}: {OUTCOME[s['outcome']].lower()}\n")
        if s["planted"]:
            lines.append(f"Planted on purpose: {s['planted']}\n")
        lines.append(f"Caught by the {s['caught_by']}, by {' and '.join(s['how'])}."
                     + (f" Fixed by the {s['fixed_by']}." if s["fixed_by"] and s["outcome"] == "fixed" else "") + "\n")
        lines += [f"- {st['t']:>5.1f}s {WHO.get(st['agent'], st['agent'])}: {st['msg']}" for st in s["steps"]]
        lines.append("")
    return "\n".join(lines) + "\n"
