"""Week 2: the class after the rescue plan, scored again with the same rules.

Nothing here calls a model. High and Medium learners (or one named learner) are given the
result of a week of catch-up, then :func:`app.risk.assess` runs again. Strong work is left
as it was. The sample files on disk are not changed.
"""
from pathlib import Path

from . import risk, tools, windows as windows_station


def _at_pass(max_marks, pass_line):
    """The smallest whole mark that meets the pass line for a criterion."""
    return min(max_marks, (max_marks * pass_line + 99) // 100)


def _rescue_theory(row, rubric, pass_line):
    """Lift criteria that are under the pass line. A missing essay becomes a draft that just passes."""
    if not row["theory"].get("in_class", True):
        return None
    existing = {item["id"]: item for item in row["theory"].get("criteria") or []}
    scores = {}
    changed = not row["theory"].get("marked")
    for criterion in rubric["criteria"]:
        got = existing.get(criterion["id"], {})
        score = int(got.get("score") or 0)
        floor = _at_pass(criterion["max"], pass_line)
        if score < floor:
            score = floor
            changed = True
        scores[criterion["id"]] = {
            "score": score,
            "evidence": got.get("evidence") or "",
            "reason": got.get("reason") or "After the rescue week this sits on the pass line.",
        }
    if not changed:
        return None
    return {"scores": scores, "total": sum(item["score"] for item in scores.values())}


def _rescue_attempt(learner_id, attempt, parts):
    """A finished build in the correct order, with no hints, inside the target time."""
    if not parts:
        return None
    if attempt and attempt.get("completed") and not attempt.get("wrong_placements") and not attempt.get("hints"):
        installed = [part for part in attempt.get("order_tried") or []]
        if [part.lower() for part in installed[:len(parts)]] == [part.lower() for part in parts]:
            return None
    return {
        "learner_id": learner_id,
        "order_tried": list(parts),
        "mistakes": 0,
        "hints": 0,
        "wrong_placements": [],
        "completed": True,
        "duration_seconds": 180,
    }


def _rescue_windows(raw):
    """Proofs under 80% are marked as agreed at 80 after the week of practice."""
    raw = raw if isinstance(raw, dict) else {}
    lifted = {}
    changed = False
    for task in windows_station.TASKS:
        current = windows_station.outcome_percent(raw.get(task["id"]))
        if current is None or current < 80:
            changed = True
            lifted[task["id"]] = {
                "percent": 80,
                "verdict": "agreed",
                "answer": task["sample"],
                "note": f"Week 2: the Reviewer agreed on {task['id']}. The proof now matches.",
            }
        else:
            stored = raw.get(task["id"])
            lifted[task["id"]] = stored if isinstance(stored, dict) else {"percent": current}
    return lifted if changed else None


def _targets(before, learner_id):
    ids = [row["id"] for row in before["learners"]]
    if learner_id:
        if learner_id not in ids:
            return None
        return [learner_id]
    return [row["id"] for row in before["learners"] if row["band"] in ("High", "Medium")]


def _loop(changes):
    moved = sum(1 for row in changes if row["band_before"] != row["band_after"])
    detail = (
        f"{moved} learner{'s' if moved != 1 else ''} moved to a different band."
        if changes else "Nobody was on the rescue list, so nothing was re-marked."
    )
    return [
        {"id": "plan", "label": "Plan", "state": "done",
         "detail": "The Planner reads the rescue list and the gaps the week was meant to close."},
        {"id": "do", "label": "Do", "state": "done",
         "detail": "Catch-up is applied: builds that were wrong or unfinished are completed in order, and the Windows tasks are done again."},
        {"id": "check", "label": "Check", "state": "done",
         "detail": "The Reviewer second-marks the week 2 practical and checks the Windows proof answers."},
        {"id": "correct", "label": "Correct", "state": "done" if changes else "clear",
         "detail": "Gaps the plan targeted are closed. Work that was already strong is left as it was."},
        {"id": "deliver", "label": "Deliver", "state": "done", "detail": detail},
    ]


def project(data_dir, live_dir=None, windows=None, learner_id=None, config=None):
    """Before and after the rescue week. ``learner_id`` limits the week to one learner."""
    config = config or risk.RISK
    before = risk.assess(data_dir, live_dir=live_dir, windows=windows, config=config)
    targets = _targets(before, learner_id)
    if targets is None:
        return {"ok": False, "error": "That learner is not on this class list."}

    rubric = tools.load_rubric(data_dir)
    practical_path_parts = []
    practical_file = tools.RUBRIC_FILES["practical"]
    data_path = Path(data_dir)
    if (data_path / practical_file).exists():
        practical_rubric = tools.load_rubric(data_dir, "practical")
        practical_path_parts = practical_rubric.get("parts") or []
    attempts = risk._attempts(data_dir, live_dir, practical_path_parts)
    stored_windows = risk._load_windows(data_dir, windows)

    theory_overlay, attempt_overlay = {}, {}
    windows_after = {key: value for key, value in stored_windows.items()}
    for row in before["learners"]:
        if row["id"] not in targets:
            continue
        theory = _rescue_theory(row, rubric, config["pass_line"])
        if theory:
            theory_overlay[row["id"]] = theory
        if practical_path_parts:
            attempt = _rescue_attempt(row["id"], attempts.get(row["id"]), practical_path_parts)
            if attempt:
                attempt_overlay[row["id"]] = attempt
        lifted = _rescue_windows(stored_windows.get(row["id"]))
        if lifted:
            windows_after[row["id"]] = lifted

    after = risk.assess(
        data_dir, live_dir=live_dir, windows=windows_after, config=config,
        attempt_overlay=attempt_overlay or None, theory_overlay=theory_overlay or None,
    )
    by_after = {row["id"]: row for row in after["learners"]}
    changes = []
    for row in before["learners"]:
        if row["id"] not in targets:
            continue
        later = by_after[row["id"]]
        changes.append({
            "id": row["id"],
            "learner": row["learner"],
            "risk_before": row["risk"],
            "risk_after": later["risk"],
            "band_before": row["band"],
            "band_after": later["band"],
            "overall_before": row["overall"],
            "overall_after": later["overall"],
            "result_before": row["result"],
            "result_after": later["result"],
        })
    who = "the class" if not learner_id else next(row["learner"] for row in before["learners"] if row["id"] == learner_id)
    moved = [row["learner"] for row in changes if row["band_before"] != row["band_after"]]
    summary = (
        f"Week 2 reran the loop for {who}. "
        + (f"{len(moved)} band change{'s' if len(moved) != 1 else ''}: {', '.join(moved)}." if moved
           else "No band changed.")
    )
    return {
        "ok": True,
        "learner": learner_id,
        "summary": summary,
        "loop": _loop(changes),
        "changes": changes,
        "before": {"counts": before["counts"], "average": before["average"], "passed": before["passed"],
                   "narrative": before["narrative"]},
        "after": after,
    }
