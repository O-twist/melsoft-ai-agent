"""Planner risk scores for Colleague Zero: Matric Rescue.

One place holds the weights and thresholds (``RISK``). For each learner the score
combines theory marks from the Marker and the Reviewer with practical outcomes.
PC assembly outcomes are H1–H6. Windows outcomes S1–S4 use the same station
shape: pass them to :func:`assess` or drop ``windows.json`` in the class folder
and they join the practical side. Nothing here calls a model, so mock mode works
with no API key.

Risk runs from 0 to 100. A higher score needs attention sooner.
"""
import json
from collections import Counter
from pathlib import Path

from . import mock, tools

# Weights, pass line, bands and how far a weak outcome pushes the score.
# Change a rescue decision here, not in the dashboard.
RISK = {
    "pass_line": 50,
    "weights": {"theory": 0.55, "practical": 0.45},
    "bands": {"high": 45, "medium": 25},
    "skill": {"strong": 70, "meeting": 50},
    # Each percentage point an outcome sits below the pass line adds this much risk, up to the cap.
    "area_shortfall_weight": 0.1,
    "shortfall_cap": 24,
    "stations": {
        "pc": {
            "id": "pc",
            "label": "Hardware / PC assembly",
            "outcomes": ["H1", "H2", "H3", "H4", "H5", "H6"],
            "weight": 1,
        },
        "windows": {
            "id": "windows",
            "label": "Windows",
            "outcomes": ["S1", "S2", "S3", "S4"],
            "weight": 1,
        },
    },
}

# Catch-up a teacher can hand over. A lab step or a part of the 3D model is enough.
CATCH_UP = {
    "H1": "On the 3D model of the PC, name the motherboard, CPU, RAM, GPU, SSD and power supply, and write one line on what each does.",
    "H2": "In the virtual lab, say the build order aloud before you touch a part: motherboard, CPU, RAM, GPU, SSD, then the power supply.",
    "H3": "In the virtual lab, seat the CPU and then the RAM before any card. On the 3D motherboard, point to the CPU socket and the RAM slots first.",
    "H4": "Fit the GPU in the long slot and the SSD in its bay on the 3D model, then do those two steps again in the virtual lab.",
    "H5": "Connect the power supply last, and tick a five-point check on the 3D model before the PC would be switched on.",
    "H6": "Write the six parts in order on paper, then finish the build in the virtual lab within four minutes, without the Hint button.",
    "W1": "Spend ten minutes on a plan: list six ideas, cross out the two weakest, and number the rest in the order you will use them.",
    "W2": "Rewrite the thinnest paragraph as a topic sentence plus one specific example from life in South Africa.",
    "W4": "Label each paragraph introduction, point or conclusion, and write the part that is missing.",
    "W6": "Read the essay aloud and correct capital letters, spelling and subject-verb agreement before the next lesson.",
    "missing_essay": "Write the essay to at least 200 words on the set topic and hand it in so it can be marked.",
    "missing_practical": "Complete the PC assembly practical in the virtual lab so there is an attempt to mark.",
}

_THEORY_OUTCOME = {"content": "W2", "language": "W6", "structure": "W4"}
_PART = {
    "motherboard": "motherboard", "cpu": "CPU", "ram": "RAM", "gpu": "GPU",
    "ssd": "SSD", "psu": "power supply",
}


def _round(number):
    return int(number + 0.5) if number >= 0 else int(number - 0.5)


def _clamp(number):
    return max(0, min(100, _round(number)))


def _pct(score, maximum):
    return _round(100 * score / maximum) if maximum else 0


def skill_label(percent, config=None):
    """Strong, Meeting or Needs work, from the thresholds in ``RISK``."""
    config = config or RISK
    if percent >= config["skill"]["strong"]:
        return "Strong"
    if percent >= config["skill"]["meeting"]:
        return "Meeting"
    return "Needs work"


def band_for(score, config=None):
    """High, Medium or Low. A higher risk score is the more urgent band."""
    config = config or RISK
    if score >= config["bands"]["high"]:
        return "High"
    if score >= config["bands"]["medium"]:
        return "Medium"
    return "Low"


def part_name(part):
    return _PART.get(str(part).lower(), str(part))


def failure_phrases(wrongs):
    """Human phrases for parts tried out of turn. Repeated tries are counted."""
    counts = Counter(part.lower() for part, _, _ in wrongs)
    phrases = []
    for part, count in counts.most_common():
        expected = next(exp for name, exp, _ in wrongs if name.lower() == part)
        if count == 2:
            phrases.append(f"failed the {part_name(part)} install step twice")
        elif count > 2:
            phrases.append(f"failed the {part_name(part)} install step {count} times")
        else:
            phrases.append(f"placed the {part_name(part)} before the {part_name(expected)}")
    return phrases


def _mark(scores, rubric):
    total = sum(scores[c["id"]]["score"] for c in rubric["criteria"])
    return {"scores": scores, "total": total}


def _offline_marks(text, rubric, learner_id, kind):
    """The same marks the offline Marker and Reviewer would give, with no model call."""
    if kind == "practical":
        marker = _mark(mock._practical_score(text, rubric), rubric)
        reviewer = _mark(mock._practical_score(text, rubric), rubric)
    else:
        marker = _mark(mock._score(text, rubric, nudge=0), rubric)
        nudge = (sum(ord(ch) for ch in learner_id) % 3) - 1
        reviewer = _mark(mock._score(text, rubric, nudge=nudge), rubric)
    return marker, reviewer


def _overlay_marks(sub):
    """Settled marks from a live run, when the Marker has actually marked this learner."""
    if not isinstance(sub, dict):
        return None
    marker, reviewer, final = sub.get("marker"), sub.get("reviewer"), sub.get("final")
    if not marker and not final:
        return None
    marker = marker or final
    final = final or marker
    return marker, reviewer, final


def _criteria(mark, rubric):
    rows = []
    for criterion in rubric["criteria"]:
        got = mark["scores"].get(criterion["id"]) or {}
        score = int(got.get("score") or 0)
        rows.append({
            "id": criterion["id"],
            "name": criterion["name"],
            "score": score,
            "max": criterion["max"],
            "percent": _pct(score, criterion["max"]),
            "evidence": str(got.get("evidence") or "").strip(),
            "reason": str(got.get("reason") or "").strip(),
        })
    return rows


def _wrongs(attempt, parts):
    return [(part, expected, t) for _, part, expected, t in tools.attempt_steps(attempt, parts) if expected]


def _pc_outcomes(attempt, parts, limits):
    """H1–H6 as percentages a teacher can read off the attempt log."""
    blank = "No attempt on record."
    if not attempt:
        return [{"id": f"H{n}", "name": f"H{n}", "percent": 0, "detail": blank} for n in range(1, 7)]
    facts = tools.attempt_facts(attempt, parts)
    steps = tools.attempt_steps(attempt, parts)
    wrongs = _wrongs(attempt, parts)
    rights = [part for _, part, expected, _ in steps if expected is None]
    installed_names = {part.lower() for part in rights}
    wrong = len(wrongs)
    target = (limits or {}).get("target_seconds", 240)
    slow = target * (limits or {}).get("slow_factor", 2)

    h1 = _pct(facts["installed"], facts["parts"])
    h2 = 100
    if not rights or rights[0].lower() != parts[0].lower():
        h2 -= 40
    if not facts["completed"] or not rights or rights[-1].lower() != parts[-1].lower():
        h2 -= 30
    h2 = max(0, h2 - 15 * wrong)

    cpu = ram = False
    h3_hits = 0
    for _, part, expected, _ in steps:
        key = part.lower()
        if expected is None:
            cpu = cpu or key == "cpu"
            ram = ram or key == "ram"
            continue
        expansion_too_soon = key in {"gpu", "ssd", "psu"} and not (cpu and ram)
        if key in {"cpu", "ram"} or expansion_too_soon:
            h3_hits += 1
    h3 = max(0, 100 - 25 * h3_hits)

    h4_hits = sum(1 for part, _, _ in wrongs if part.lower() in {"gpu", "ssd"})
    h4 = max(0, 100 - 30 * h4_hits)
    if "gpu" not in installed_names or "ssd" not in installed_names:
        h4 = min(h4, 40)

    early_psu = any(part.lower() == "psu" for part, _, _ in wrongs)
    if "psu" in installed_names and not early_psu and facts["completed"]:
        h5 = 100
    elif "psu" in installed_names:
        h5 = 55
    else:
        h5 = 0

    h6 = 100 - 20 * facts["hints"]
    if facts["seconds"] > target:
        h6 -= 15
    if facts["seconds"] > slow:
        h6 -= 25
    if not facts["completed"]:
        h6 -= 40
    h6 = max(0, h6)

    phrases = failure_phrases(wrongs)
    detail = {
        "H1": f"{facts['installed']} of {facts['parts']} parts installed.",
        "H2": (f"{wrong} part{'s' if wrong != 1 else ''} tried out of turn." if wrong
               else "Motherboard first and power last."),
        "H3": ("; ".join(phrases) + "." if phrases else "CPU and RAM went in before the cards."),
        "H4": ("The GPU or the SSD was tried in the wrong place." if h4_hits
               else "Expansion cards and storage landed in the right places."),
        "H5": ("The power supply was tried before the build was ready." if early_psu or h5 == 0
               else "Power was connected last."),
        "H6": f"{facts['hints']} hint{'s' if facts['hints'] != 1 else ''}, {facts['seconds']} seconds"
              + ("" if facts["completed"] else ", and the build was not finished") + ".",
    }
    percents = {"H1": h1, "H2": h2, "H3": h3, "H4": h4, "H5": h5, "H6": h6}
    names = {
        "H1": "Name the parts", "H2": "Build order", "H3": "CPU and RAM",
        "H4": "Cards and storage", "H5": "Power last", "H6": "Independent build",
    }
    return [{"id": key, "name": names[key], "percent": percents[key], "detail": detail[key]} for key in percents]


def _windows_outcomes(raw, station):
    if not isinstance(raw, dict):
        return []
    rows = []
    for outcome_id in station["outcomes"]:
        if outcome_id not in raw:
            continue
        try:
            percent = float(raw[outcome_id])
        except (TypeError, ValueError):
            continue
        rows.append({
            "id": outcome_id, "name": outcome_id, "percent": _clamp(percent),
            "detail": "Recorded on the Windows station.",
        })
    return rows


def _load_windows(data_dir, windows):
    if windows is not None:
        return windows if isinstance(windows, dict) else {}
    path = Path(data_dir) / "windows.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get("learners"), dict):
        return data["learners"]
    return data if isinstance(data, dict) else {}


def _contains(quote, text):
    if not quote or not text:
        return False
    folded = " ".join(quote.split()).lower()
    return bool(folded) and folded in " ".join(text.split()).lower()


def _moderation(label, marker, reviewer, final, rubric):
    """One sentence. The caller joins the sides under a single 'Second-marked.'"""
    if not marker:
        return f"{label}: nothing to mark, so the Reviewer was not asked."
    out_of = rubric["total"]
    if not reviewer:
        return f"{label}: marked {marker['total']}/{out_of}, still waiting for the Reviewer."
    final = final or marker
    gap = reviewer["total"] - marker["total"]
    if final["total"] != marker["total"]:
        changed = abs(final["total"] - marker["total"])
        unit = "mark" if changed == 1 else "marks"
        return f"{label}: {changed} {unit} adjusted (Marker {marker['total']}/{out_of}, now {final['total']}/{out_of})."
    if gap == 0:
        return f"{label}: the Reviewer agreed ({marker['total']}/{out_of})."
    changed = abs(gap)
    unit = "mark" if changed == 1 else "marks"
    way = "higher" if gap > 0 else "lower"
    inside = "inside the 15% tolerance, so the Marker's mark stood" if not tools.disagreements(rubric, marker, reviewer) else "and the Marker's mark stood"
    return f"{label}: the Reviewer was {changed} {unit} {way}, {inside} ({marker['total']}/{out_of})."


def _area(row, group):
    return {
        "id": row["id"], "name": row["name"], "group": group,
        "percent": row["percent"], "label": row["label"],
        "score": row.get("score"), "max": row.get("max"),
        "detail": row.get("detail") or "",
    }


def _learner_report(sub, theory, practical, windows_rows, config):
    """One learner: risk, the score report, and the sentences that explain both."""
    pass_line = config["pass_line"]
    weights = config["weights"]
    theory_pct = theory["percent"] if theory["marked"] else 0
    stations = []
    if practical["in_class"]:
        stations.append((config["stations"]["pc"]["weight"], practical["percent"] if practical["marked"] else 0))
    if windows_rows:
        stations.append((config["stations"]["windows"]["weight"], _round(sum(r["percent"] for r in windows_rows) / len(windows_rows))))
    if stations:
        weight = sum(item[0] for item in stations)
        practical_pct = _round(sum(item[0] * item[1] for item in stations) / weight)
        practical_known = True
    else:
        practical_pct, practical_known = None, False

    parts = [(weights["theory"], theory_pct)]
    if practical_known:
        parts.append((weights["practical"], practical_pct))
    overall = _round(sum(w * p for w, p in parts) / sum(w for w, _ in parts))
    base = _round(sum(w * (100 - p) for w, p in parts) / sum(w for w, _ in parts))

    short_points = 0
    if theory["marked"]:
        short_points += sum(max(0, pass_line - row["percent"]) for row in theory["criteria"])
    else:
        short_points += pass_line
    if practical["in_class"]:
        short_points += sum(max(0, pass_line - row["percent"]) for row in practical["outcomes"])
    short_points += sum(max(0, pass_line - row["percent"]) for row in windows_rows)
    extra = min(config["shortfall_cap"], config["area_shortfall_weight"] * short_points)
    risk = _clamp(base + extra)
    band = band_for(risk, config)

    areas = []
    for row in (theory["criteria"] if theory["marked"] else [{
        "id": "theory", "name": "Theory essay", "percent": 0, "score": 0, "max": theory["max"], "detail": theory["why"],
    }]):
        row = {**row, "label": skill_label(row["percent"], config)}
        areas.append(_area(row, "theory"))
    if practical["in_class"]:
        hardware = {
            "id": "pc", "name": config["stations"]["pc"]["label"],
            "percent": practical["percent"] if practical["marked"] else 0,
            "score": practical.get("score"), "max": practical.get("max"),
            "detail": _hardware_detail(practical),
        }
        hardware["label"] = skill_label(hardware["percent"], config)
        areas.append(_area(hardware, "practical"))
    if windows_rows:
        percent = _round(sum(row["percent"] for row in windows_rows) / len(windows_rows))
        windows_area = {
            "id": "windows", "name": config["stations"]["windows"]["label"],
            "percent": percent, "label": skill_label(percent, config),
            "detail": ", ".join(f"{row['id']} {row['percent']}%" for row in windows_rows),
        }
        areas.append(_area(windows_area, "practical"))

    strengths, gaps = _evidence(sub, theory, practical, windows_rows, config)
    reason, reasons = _reasons(sub, theory, practical, windows_rows, pass_line, practical_pct)
    notes = []
    if theory["in_class"]:
        notes.append(_moderation("Theory", theory.get("marker"), theory.get("reviewer"), theory.get("final"), theory["rubric"]))
    if practical["in_class"]:
        notes.append(_moderation("Practical", practical.get("marker"), practical.get("reviewer"), practical.get("final"), practical["rubric"]))
    moderation = "Second-marked. " + " ".join(notes) if notes else "Nothing has been second-marked yet."

    return {
        "id": sub["id"], "learner": sub["learner"], "first_name": sub["learner"].split()[0],
        "risk": risk, "band": band, "reason": reason, "reasons": reasons,
        "overall": overall, "result": "Pass" if overall >= pass_line else "Not yet",
        "pass_line": pass_line, "areas": areas, "strengths": strengths, "gaps": gaps,
        "moderation": moderation,
        "theory": {k: v for k, v in theory.items() if k not in ("rubric", "marker", "reviewer", "final", "text")},
        "practical": {k: v for k, v in practical.items() if k not in ("rubric", "marker", "reviewer", "final", "text", "attempt", "wrongs")},
    }


def _hardware_detail(practical):
    if not practical["marked"]:
        return practical["why"]
    return " · ".join(f"{row['name']} {row['score']}/{row['max']}" for row in practical["criteria"])


def _evidence(sub, theory, practical, windows_rows, config):
    strengths, gaps = [], []
    text = theory.get("text") or ""
    if theory["marked"]:
        ordered = sorted(theory["criteria"], key=lambda row: (row["percent"], -row["max"]))
        best = ordered[-1]
        quote = best["evidence"] if _contains(best["evidence"], text) else ""
        if not quote:
            quote = mock._quote(text) if text else ""
            if not _contains(quote, text):
                quote = ""
        if best["percent"] >= config["skill"]["meeting"]:
            strengths.append({
                "name": best["name"], "percent": best["percent"], "label": skill_label(best["percent"], config),
                "quote": quote, "detail": best["reason"],
            })
        for row in ordered:
            if row["percent"] >= config["skill"]["meeting"]:
                continue
            outcome = _THEORY_OUTCOME.get(row["id"], "W2")
            quote = row["evidence"] if _contains(row["evidence"], text) else ""
            if row["id"] == "language":
                slipped = mock._quote(text, slip=True) if text else ""
                if _contains(slipped, text):
                    quote = slipped
            gaps.append({
                "name": row["name"], "percent": row["percent"], "outcome": outcome,
                "detail": row["reason"] or f"{row['percent']}% against a {config['pass_line']}% pass line.",
                "quote": quote, "task": CATCH_UP.get(outcome, CATCH_UP["W2"]),
            })
    elif theory["in_class"]:
        gaps.append({
            "name": "Theory essay", "percent": 0, "outcome": "W1",
            "detail": theory["why"], "quote": "", "task": CATCH_UP["missing_essay"],
        })

    if practical["in_class"] and practical["marked"]:
        log = practical.get("text") or ""
        best = max(practical["criteria"], key=lambda row: row["percent"])
        if best["percent"] >= config["skill"]["strong"]:
            quote = best["evidence"] if _contains(best["evidence"], log) else ""
            strengths.append({
                "name": best["name"], "percent": best["percent"], "label": skill_label(best["percent"], config),
                "quote": quote, "detail": best["reason"],
            })
        weak_outcomes = [row for row in practical["outcomes"] if row["percent"] < config["skill"]["meeting"]]
        repeated = [phrase for phrase in failure_phrases(practical.get("wrongs") or []) if "twice" in phrase or "times" in phrase]
        if repeated and not any(row["id"] == "H3" for row in weak_outcomes):
            weak_outcomes.insert(0, {
                "id": "H3", "name": "CPU and RAM", "percent": next((row["percent"] for row in practical["outcomes"] if row["id"] == "H3"), 0),
                "detail": repeated[0][0].upper() + repeated[0][1:] + ".",
            })
        chosen = sorted(weak_outcomes, key=lambda item: item["percent"])[:3]
        if repeated and not any(row["id"] == "H3" for row in chosen):
            chosen = [next(row for row in weak_outcomes if row["id"] == "H3")] + chosen[:2]
        for row in chosen:
            quote = _log_quote(log, row["id"])
            gaps.append({
                "name": f"{row['id']} {row['name']}", "percent": row["percent"], "outcome": row["id"],
                "detail": row["detail"], "quote": quote, "task": CATCH_UP.get(row["id"], CATCH_UP["H6"]),
            })
    elif practical["in_class"]:
        gaps.append({
            "name": "Hardware / PC assembly", "percent": 0, "outcome": "H6",
            "detail": practical["why"], "quote": "", "task": CATCH_UP["missing_practical"],
        })

    for row in windows_rows:
        if row["percent"] >= config["skill"]["meeting"]:
            continue
        gaps.append({
            "name": f"Windows {row['id']}", "percent": row["percent"], "outcome": row["id"],
            "detail": row["detail"], "quote": "",
            "task": f"Revisit Windows outcome {row['id']} with the teacher before the next sitting.",
        })
    if not strengths and theory["marked"]:
        best = max(theory["criteria"], key=lambda row: row["percent"])
        strengths.append({
            "name": best["name"], "percent": best["percent"], "label": skill_label(best["percent"], config),
            "quote": best["evidence"] if _contains(best["evidence"], theory.get("text") or "") else "",
            "detail": "This is the strongest part of the work so far.",
        })
    return strengths[:3], gaps[:4]


def _reasons(sub, theory, practical, windows_rows, pass_line, practical_pct):
    reasons = []
    if not theory["marked"]:
        reasons.append(f"No theory mark against a {pass_line}% pass line. {theory['why']}")
        theory_clause = f"No theory mark against a {pass_line}% pass line"
    else:
        reviewer = theory.get("reviewer_total")
        marked = (f"Marker {theory['score']}/{theory['max']}"
                  + (f", Reviewer {reviewer}/{theory['max']}" if reviewer is not None else ""))
        reasons.append(f"Theory {theory['percent']}% ({marked}) against a {pass_line}% pass line.")
        weak = [row for row in theory["criteria"] if row["percent"] < pass_line]
        for row in sorted(weak, key=lambda item: item["percent"])[:2]:
            reasons.append(f"{row['name']} is {row['percent']}%, under the {pass_line}% pass line.")
        if theory["percent"] < pass_line:
            theory_clause = f"Theory {theory['percent']}% against a {pass_line}% pass line"
        elif weak:
            worst = min(weak, key=lambda row: row["percent"])
            theory_clause = f"{worst['name']} {worst['percent']}% against a {pass_line}% pass line"
        else:
            theory_clause = None

    practical_clause = None
    if practical["in_class"] and not practical["marked"]:
        reasons.append(f"No PC assembly attempt on record, so H1–H6 cannot be credited against the {pass_line}% pass line.")
        practical_clause = "no PC assembly attempt on record"
    elif practical["in_class"]:
        reasons.append(f"PC assembly {practical['percent']}% (Marker {practical['score']}/{practical['max']}) against a {pass_line}% pass line.")
        phrases = failure_phrases(practical.get("wrongs") or [])
        if not practical.get("completed"):
            practical_clause = f"did not finish the PC build, with {len(practical.get('wrongs') or [])} parts tried out of turn"
            reasons.append(practical_clause[0].upper() + practical_clause[1:] + ".")
        elif phrases:
            practical_clause = next((phrase for phrase in phrases if "RAM" in phrase), phrases[0])
            shown = "; ".join(phrases)
            reasons.append(shown[0].upper() + shown[1:] + ".")
        weak_steps = [row for row in practical["outcomes"] if row["percent"] < pass_line]
        for row in sorted(weak_steps, key=lambda item: item["percent"])[:2]:
            reasons.append(f"{row['id']} {row['name']} is {row['percent']}%: {row['detail']}")
    if windows_rows:
        mean = _round(sum(row["percent"] for row in windows_rows) / len(windows_rows))
        reasons.append(f"Windows outcomes average {mean}% against a {pass_line}% pass line.")

    if theory_clause and practical_clause:
        line = f"{theory_clause}; {practical_clause}"
    elif theory_clause:
        line = theory_clause
    elif practical_clause:
        line = practical_clause[0].upper() + practical_clause[1:]
    elif practical_pct is None:
        line = f"Theory {theory['percent']}%, on or above the {pass_line}% pass line"
    else:
        line = (f"Theory {theory['percent']}% and PC assembly {practical['percent']}%, "
                f"both on or above the {pass_line}% pass line")
    return " ".join(line.split()), reasons


def _theory_block(sub, rubric, overlay_sub, config):
    min_words = rubric.get("min_words", 50)
    text = sub.get("text") or ""
    words = len(text.split())
    overlay = _overlay_marks(overlay_sub)
    if overlay:
        marker, reviewer, final = overlay
        source = "settled"
    elif words < min_words:
        why = (f"The essay has {words} words and needs at least {min_words}, so it was not marked."
               if words else "Nothing was handed in for the essay, so it was not marked.")
        return {"in_class": True, "marked": False, "percent": 0, "score": 0, "max": rubric["total"],
                "source": "none", "why": why, "criteria": [], "text": text, "rubric": rubric,
                "marker": None, "reviewer": None, "final": None}
    else:
        marker, reviewer = _offline_marks(text, rubric, sub["id"], "essay")
        final = marker
        source = "offline"
    criteria = _criteria(final, rubric)
    return {
        "in_class": True, "marked": True, "percent": _pct(final["total"], rubric["total"]),
        "score": final["total"], "max": rubric["total"], "source": source,
        "marker_total": marker["total"], "reviewer_total": reviewer["total"] if reviewer else None,
        "why": "", "criteria": criteria, "text": text, "rubric": rubric,
        "marker": marker, "reviewer": reviewer, "final": final,
    }


def _practical_block(sub, rubric, attempt, overlay_sub):
    if rubric is None:
        return {"in_class": False, "marked": False, "percent": None, "outcomes": [], "criteria": [], "wrongs": []}
    limits = rubric.get("limits") or {}
    parts = rubric.get("parts") or []
    outcomes = _pc_outcomes(attempt, parts, limits)
    wrongs = _wrongs(attempt, parts) if attempt else []
    if not attempt:
        return {
            "in_class": True, "marked": False, "percent": 0, "score": 0, "max": rubric["total"],
            "source": "none", "why": "No PC assembly attempt is on record.",
            "criteria": [], "outcomes": outcomes, "wrongs": [], "completed": False,
            "text": "", "rubric": rubric, "marker": None, "reviewer": None, "final": None, "attempt": None,
        }
    log = tools.render_attempt(attempt, rubric)
    overlay = _overlay_marks(overlay_sub)
    if overlay:
        marker, reviewer, final = overlay
        source = "settled"
    else:
        marker, reviewer = _offline_marks(log, rubric, sub["id"], "practical")
        final = marker
        source = "offline"
    facts = tools.attempt_facts(attempt, parts)
    return {
        "in_class": True, "marked": True, "percent": _pct(final["total"], rubric["total"]),
        "score": final["total"], "max": rubric["total"], "source": source,
        "marker_total": marker["total"], "reviewer_total": reviewer["total"] if reviewer else None,
        "why": "", "criteria": _criteria(final, rubric), "outcomes": outcomes, "wrongs": wrongs,
        "completed": facts["completed"], "text": log, "rubric": rubric,
        "marker": marker, "reviewer": reviewer, "final": final, "attempt": attempt,
    }


def _attempts(data_dir, live_dir, parts):
    found = tools._read_attempts(Path(data_dir) / "attempts", parts) if parts else {}
    live = tools._read_attempts(live_dir, parts) if parts else {}
    found.update(live)  # a build saved in the lab replaces the sample file
    return found


def assess(data_dir, overlay=None, assessment=None, live_dir=None, windows=None, config=None):
    """Risk and score reports for the class in ``data_dir``.

    ``overlay`` is the run's submissions when a marking run is underway. Essay runs
    replace the theory side with the marks just settled; practical runs replace the
    PC mark. The other side still comes from the work on disk, scored the way the
    offline Marker and Reviewer score it.

    ``windows`` maps a learner id to outcome percentages, for example
    ``{"E04": {"S1": 40, "S2": 55, "S3": 70, "S4": 35}}``.
    """
    config = config or RISK
    data_dir = Path(data_dir)
    essay_rubric = tools.load_rubric(data_dir, "essay")
    practical_path = data_dir / tools.RUBRIC_FILES["practical"]
    practical_rubric = tools.load_rubric(data_dir, "practical") if practical_path.exists() else None
    subs = tools.load_submissions(data_dir)
    parts = (practical_rubric or {}).get("parts") or []
    attempts = _attempts(data_dir, live_dir, parts)
    by_overlay = {s["id"]: s for s in overlay or []}
    windows_by = _load_windows(data_dir, windows)
    station = config["stations"]["windows"]

    learners = []
    for sub in subs:
        overlay_sub = by_overlay.get(sub["id"])
        theory_overlay = overlay_sub if assessment == "essay" else None
        practical_overlay = overlay_sub if assessment == "practical" else None
        # An essay run may have replaced the typed file with a transcript. A practical run's text is the attempt log.
        if assessment == "essay" and isinstance(overlay_sub, dict) and overlay_sub.get("text"):
            sub = {**sub, "text": overlay_sub["text"]}
        theory = _theory_block(sub, essay_rubric, theory_overlay, config)
        attempt = attempts.get(sub["id"])
        practical = _practical_block(sub, practical_rubric, attempt, practical_overlay)
        windows_rows = _windows_outcomes(windows_by.get(sub["id"]), station)
        for row in windows_rows:
            row["label"] = skill_label(row["percent"], config)
        for row in practical["outcomes"]:
            row["label"] = skill_label(row["percent"], config)
        learners.append(_learner_report(sub, theory, practical, windows_rows, config))

    learners.sort(key=lambda row: (-row["risk"], row["learner"]))
    counts = {"High": 0, "Medium": 0, "Low": 0}
    for row in learners:
        counts[row["band"]] = counts.get(row["band"], 0) + 1
    average = _round(sum(row["overall"] for row in learners) / len(learners)) if learners else 0
    passed = sum(row["result"] == "Pass" for row in learners)
    weakest = _weakest(learners)
    high_names = [row["learner"] for row in learners if row["band"] == "High"]
    narrative = (
        f"{len(learners)} learners. Class average {average} out of 100, against a pass line of {config['pass_line']}. "
        f"{len(learners) - passed} not yet at the pass line. "
        f"{counts.get('High', 0)} at high risk"
        + (f": {', '.join(high_names)}." if high_names else ".")
    )
    return {
        "ok": True,
        "title": "Colleague Zero: Matric Rescue",
        "config": {
            "pass_line": config["pass_line"],
            "weights": config["weights"],
            "bands": config["bands"],
            "skill": config["skill"],
            "area_shortfall_weight": config["area_shortfall_weight"],
            "shortfall_cap": config["shortfall_cap"],
            "stations": config["stations"],
        },
        "counts": counts,
        "average": average,
        "passed": passed,
        "not_yet": len(learners) - passed,
        "narrative": narrative,
        "weakest_area": weakest,
        "learners": learners,
    }


def _log_quote(log, outcome_id):
    """A wrong step from the attempt log, chosen for the outcome it illustrates."""
    lines = [line.strip() for line in (log or "").splitlines() if ". Wrong:" in line]
    if outcome_id == "H3":
        picked = next((line for line in lines if "RAM" in line or "CPU" in line), "")
    elif outcome_id == "H5":
        picked = next((line for line in lines if "power supply" in line.lower() or "PSU" in line), "")
    elif outcome_id == "H4":
        picked = next((line for line in lines if "SSD" in line), "") or next((line for line in lines if "GPU" in line), "")
    elif outcome_id == "H6":
        picked = next((line.strip() for line in (log or "").splitlines() if "Hints used:" in line), "")
    else:
        picked = lines[0] if lines else ""
    if not picked and lines and outcome_id in {"H2", "H3", "H4", "H5"}:
        picked = lines[0]
    return picked if _contains(picked, log) else ""


def _weakest(learners):
    totals = {}
    for learner in learners:
        for area in learner["areas"]:
            if area["id"] == "theory":  # the stand-in bar when an essay was not marked
                continue
            bucket = totals.setdefault(area["name"], [])
            bucket.append(area["percent"])
    if not totals:
        return None
    name, percents = min(totals.items(), key=lambda item: sum(item[1]) / len(item[1]))
    return {"name": name, "percent": _round(sum(percents) / len(percents))}
