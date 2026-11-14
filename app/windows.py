"""Windows station for LabLess: four tasks, proof answers, and the Reviewer's check.

The simulator at win11.blueedge.me is shown in an iframe and sends nothing back, the same
screen CompuClass embeds. The learner types a proof answer for each task. This module is
the Reviewer's check: it compares the answer with what that simulator actually shows.
No model is called, so mock mode needs no API key.

The accepted answers are the readings on win11.blueedge.me (Win11 in React): the desktop
folder the task asks for, the Documents folder the learner renames, the Personalisation
heading, and the device name and model on Settings, System (Liber-V, NS14A8). That page
does not show a RAM figure, so the system-info proof asks for the name and model instead.
"""
import re

# ``need`` is a list of groups. A group matches when the answer contains one of its phrases.
# Every group must match for a full mark. One group is a partial. ``sample`` is the answer
# a correct learner types, used when Week 2 closes the gap.
TASKS = [
    {
        "id": "S1",
        "name": "Create a folder",
        "instruction": "In the simulator, open File Explorer, go to the Desktop, and create a folder named CAT Rescue.",
        "proof": "What name did you give the new folder?",
        "need": [["cat rescue"]],
        "sample": "CAT Rescue",
    },
    {
        "id": "S2",
        "name": "Rename a file",
        "instruction": "Open Documents, then the 2020 folder, and rename the folder whose name mentions a Windows release.",
        "proof": "What was that folder called before you renamed it?",
        "need": [["windows 11 release"]],
        "partial": [["windows 11"]],
        "sample": "Windows 11 Release",
    },
    {
        "id": "S3",
        "name": "Change the wallpaper",
        "instruction": "Open Settings, then Personalisation, and choose a different theme picture.",
        "proof": "What heading is written above the row of theme pictures?",
        "need": [["select a theme to apply"]],
        "partial": [["select a theme"]],
        "sample": "Select a theme to apply",
    },
    {
        "id": "S4",
        "name": "Find system info",
        "instruction": "Open Settings, then System. Read the device name and the model written under it.",
        "proof": "What device name and model does System show?",
        "need": [["liber v", "liberv"], ["ns14a8"]],
        "partial": [["liber v", "liberv"], ["ns14a8"]],
        "sample": "Liber-V NS14A8",
    },
]

_BY_ID = {task["id"]: task for task in TASKS}


def task_by_id(outcome_id):
    return _BY_ID.get(outcome_id)


def public_tasks():
    """What the checklist may show. The accepted answers stay on the server."""
    return [
        {"id": task["id"], "name": task["name"], "instruction": task["instruction"], "proof": task["proof"]}
        for task in TASKS
    ]


def normalise(text):
    text = str(text or "").lower().replace("-", " ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _hits(groups, answer):
    found = 0
    for group in groups:
        if any(normalise(phrase) in answer for phrase in group):
            found += 1
    return found


def review_answer(task, answer):
    """One proof. The Reviewer agrees, accepts it in part, or disagrees. Percents are 100, 50 or 0."""
    got = normalise(answer)[:200]
    if not got:
        return {
            "percent": 0, "verdict": "no proof",
            "note": f"The Reviewer could not check {task['id']}: no answer was given.",
        }
    if _hits(task["need"], got) == len(task["need"]):
        return {
            "percent": 100, "verdict": "agreed",
            "note": f"The Reviewer agreed on {task['id']}: the proof matches what the simulator shows.",
        }
    partial = task.get("partial") or []
    if partial and _hits(partial, got):
        return {
            "percent": 50, "verdict": "partly",
            "note": f"The Reviewer found part of the {task['id']} proof, not the full answer.",
        }
    return {
        "percent": 0, "verdict": "disagreed",
        "note": f"The Reviewer disagreed on {task['id']}. The proof does not match what the simulator shows.",
    }


def review(answers, learner_id):
    """Check every task for one learner. ``answers`` maps S1–S4 to the text the learner typed."""
    answers = answers if isinstance(answers, dict) else {}
    outcomes = {}
    for task in TASKS:
        result = review_answer(task, answers.get(task["id"], ""))
        outcomes[task["id"]] = {
            "percent": result["percent"],
            "verdict": result["verdict"],
            "answer": str(answers.get(task["id"]) or "").strip()[:200],
            "note": result["note"],
        }
    agreed = sum(1 for row in outcomes.values() if row["verdict"] == "agreed")
    return {
        "learner_id": learner_id,
        "outcomes": outcomes,
        "agreed": agreed,
        "checked": len(TASKS),
        "summary": f"The Reviewer checked {len(TASKS)} Windows proofs and agreed with {agreed}.",
    }


def outcome_percent(raw):
    """A stored outcome is either a number or ``{"percent": n, ...}``."""
    if isinstance(raw, dict):
        raw = raw.get("percent")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
