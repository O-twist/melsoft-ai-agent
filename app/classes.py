"""A teacher's own class: a class list and essays uploaded from the dashboard, checked in code, kept as a data folder.

The folder looks exactly like data/ (class.csv, essays/<id>.txt, rubric.json, memo.md, outcomes.json), so a run
reads it the way it reads the sample class. A rubric or outcomes file the teacher does not upload is copied from the
sample class. The sample memo is copied only with the sample rubric: a memo written for another task would mislead
the markers, so a teacher's own rubric without a memo is marked from the rubric alone. Nothing is changed in data/.
"""
import csv
import io
import json
import re
import secrets
import shutil
from pathlib import Path

from . import tools

CLASS_ID = re.compile(r"^[0-9a-f]{12}$")
LEARNER_ID = re.compile(r"^[A-Za-z0-9_-]{1,20}$")  # it names a file, so nothing that could reach outside the folder
MAX_LEARNERS = 200
MAX_ESSAY_BYTES = 200_000
ESSAY_TYPES = (".txt", ".md")


class ClassError(ValueError):
    """An upload that cannot be used, with every reason a teacher can act on."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


def read_text(data):
    """Text from a file a teacher made: UTF-8 (with or without a byte-order mark), else Windows' own encoding."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_class_list(data):
    """The learners in a class list. Returns (rows, problems). Commas, semicolons or tabs between columns all work."""
    text = read_text(data).strip()
    if not text:
        return [], ["the class list is empty"]
    first = text.splitlines()[0]
    delimiter = max(",;\t", key=first.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = [h.strip().lower() for h in next(reader)]
    missing = [col for col in ("id", "name") if col not in header]
    if missing:
        return [], [f"the class list has no {' or '.join(missing)} column (the first row must name the columns: id, name, email, previous)"]
    at = {col: header.index(col) for col in ("id", "name", "email", "previous") if col in header}
    rows, problems, seen = [], [], {}
    for n, row in enumerate(reader, 2):
        cell = lambda col: row[at[col]].strip() if col in at and at[col] < len(row) else ""
        sid = cell("id")
        if not any(c.strip() for c in row):
            continue
        if not LEARNER_ID.match(sid):
            problems.append(f"row {n}: the id “{sid}” must be letters, digits, - or _ (up to 20)")
            continue
        first = seen.get(sid.lower())
        if first:  # essay files are matched without regard to capitals, so A1 and a1 cannot both be ids
            problems.append(f"row {n}: the id {sid} is used twice" if first == sid else
                            f"row {n}: the id {sid} is the same as {first} apart from capital letters")
            continue
        seen[sid.lower()] = sid
        previous = cell("previous")
        if previous and tools._percent(previous) is None:
            problems.append(f"row {n}: the previous mark “{previous}” is not a percentage from 0 to 100")
        rows.append({"id": sid, "name": cell("name") or sid, "email": cell("email"), "previous": previous})
    if not rows and not problems:
        problems.append("the class list has no learners")
    if len(rows) > MAX_LEARNERS:
        problems.append(f"the class list has {len(rows)} learners; at most {MAX_LEARNERS} can be marked in one run")
    return rows, problems


def match_essays(files, rows):
    """Which essay file is whose. A file belongs to a learner when its name is the learner's id, alone or followed
    by a space, - or _ (E01.txt, E01_Thandi.txt). Returns ({learner id: text}, [files not matched, with why])."""
    ids = {r["id"].lower(): r["id"] for r in rows}
    matched, unmatched = {}, []
    for name, data in files:
        stem, suffix = Path(name).stem, Path(name).suffix.lower()
        if suffix not in ESSAY_TYPES:
            unmatched.append(f"{name} (only .txt essays can be read)")
            continue
        if len(data) > MAX_ESSAY_BYTES:
            unmatched.append(f"{name} (larger than {MAX_ESSAY_BYTES // 1000} kB)")
            continue
        m = re.match(r"([A-Za-z0-9_-]+?)(?:[\s_-].*)?$", stem)
        sid = ids.get(stem.lower()) or (ids.get(m.group(1).lower()) if m else None)
        if not sid:
            unmatched.append(f"{name} (no learner on the class list has this id)")
        elif sid in matched:
            unmatched.append(f"{name} (a second essay for {sid}; the first one is used)")
        else:
            matched[sid] = read_text(data).strip()
    return matched, unmatched


def check_rubric(data):
    """Problems with an uploaded rubric.json, so that a broken one is refused before any marking."""
    try:
        rubric = json.loads(read_text(data))
    except ValueError as e:
        return [f"rubric.json is not valid JSON ({e})"]
    if not isinstance(rubric, dict):
        return ["rubric.json must be an object with a title, a task and criteria"]
    problems = [f"rubric.json has no {key}" for key in ("title", "task") if not str(rubric.get(key) or "").strip()]
    criteria = rubric.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return problems + ["rubric.json has no criteria"]
    ids = set()
    for n, c in enumerate(criteria, 1):
        if not isinstance(c, dict):
            problems.append(f"criterion {n} is not an object")
            continue
        cid = str(c.get("id") or "")
        if not cid or cid in ids:
            problems.append(f"criterion {n} needs an id of its own")
        ids.add(cid)
        if not isinstance(c.get("max"), int) or c["max"] <= 0:
            problems.append(f"criterion {cid or n} needs a whole-number max above 0")
        bands = c.get("bands")
        if not isinstance(bands, list) or not bands or not all(
                isinstance(b, dict) and isinstance(b.get("range"), list) and len(b["range"]) == 2 and b.get("text") for b in bands):
            problems.append(f"criterion {cid or n} needs bands, each with a range [low, high] and a text")
    return problems


MAX_MEMO_BYTES = 100_000


def create_class(root, sample_dir, class_list, essays, rubric=None, outcomes=None, memo=None):
    """Check an upload and keep it as a class folder. Returns (class id, summary), or raises ClassError.

    A problem that would make marking wrong (no ids, an id used twice, a broken rubric) refuses the upload.
    Anything a teacher may simply want to know (a learner with no essay, a file that matched nobody) is reported.
    """
    rows, problems = parse_class_list(class_list or b"")
    if rubric:
        problems += check_rubric(rubric)
    if outcomes:
        try:
            json.loads(read_text(outcomes))
        except ValueError as e:
            problems.append(f"outcomes.json is not valid JSON ({e})")
    if memo is not None and len(memo) > MAX_MEMO_BYTES:
        problems.append(f"the memo is larger than {MAX_MEMO_BYTES // 1000} kB")
    elif memo is not None and not read_text(memo).strip():
        problems.append("the memo is empty")
    if problems:
        raise ClassError(problems)
    matched, unmatched = match_essays(essays, rows)
    cid = secrets.token_hex(6)
    folder = Path(root) / cid
    (folder / "essays").mkdir(parents=True)
    with open(folder / "class.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "email", "previous"])
        w.writerows([r["id"], r["name"], r["email"], r["previous"]] for r in rows)
    for sid, text in matched.items():
        (folder / "essays" / f"{sid}.txt").write_text(text, encoding="utf-8")
    for name, data in (("rubric.json", rubric), ("outcomes.json", outcomes)):
        if data:
            (folder / name).write_text(read_text(data), encoding="utf-8")
        elif (Path(sample_dir) / name).exists():
            shutil.copy(Path(sample_dir) / name, folder / name)
    if memo:
        (folder / tools.MEMO_FILES["essay"]).write_text(read_text(memo).strip() + chr(10), encoding="utf-8")
    elif not rubric and (Path(sample_dir) / tools.MEMO_FILES["essay"]).exists():
        shutil.copy(Path(sample_dir) / tools.MEMO_FILES["essay"], folder / tools.MEMO_FILES["essay"])
    for name in ("practical_rubric.json", tools.MEMO_FILES["practical"]):
        if (Path(sample_dir) / name).exists():
            shutil.copy(Path(sample_dir) / name, folder / name)
    subs = tools.load_submissions(folder)
    rubric_now = tools.load_rubric(folder)
    tools.triage(subs, rubric_now)
    summary = {
        "class": cid, "learners": len(rows), "essays": len(matched),
        "missing": [r["id"] for r in rows if r["id"] not in matched], "unmatched": unmatched,
        "rubric": rubric_now["title"], "own_rubric": bool(rubric), "own_outcomes": bool(outcomes),
        "own_memo": bool(memo), "memo": bool(rubric_now.get("memo")),
        "preview": [{"id": s["id"], "learner": s["learner"], "words": s["words"], "flags": s["flags"]} for s in subs],
    }
    (folder / "upload.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return cid, summary


def class_folder(root, cid):
    """The folder of an uploaded class, or ClassError."""
    folder = Path(root) / str(cid or "")
    if not CLASS_ID.match(str(cid or "")) or not (folder / "class.csv").is_file():
        raise ClassError(["that class is not known; upload it again"])
    return folder
