"""Optional Supabase copy of the class. Missing settings, or any error, leave the demo on the files.

The dashboard is still scored from data/ (and from a live run's memory). Supabase is a
copy: learners, marks, H1–H6 and S1–S4, risk scores, rescue plans and score reports.
Nothing in here is allowed to raise into a request.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import risk, tools, week2

DATA = Path(__file__).resolve().parents[1] / "data"
MIGRATION = "supabase/migrations/20261113233000_lablest.sql"
SEED = "supabase/seed.sql"
_state = {"saved": {}, "week": None, "miss_until": 0.0, "fail_until": 0.0}


def credentials():
    """URL plus the service key when it is set, otherwise the anon key. Both stay in the environment."""
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        return None
    return url, key


def reset_cache():
    """Drop the in-process copy. Tests use this so one case cannot leak into the next."""
    _state["saved"] = {}
    _state["week"] = None
    _state["miss_until"] = 0.0
    _state["fail_until"] = 0.0


def _paused():
    return time.time() < _state["fail_until"]


def _request(method, path, payload=None):
    creds = credentials()
    if not creds or _paused():
        return None
    url, key = creds
    data = None if payload is None else json.dumps(payload).encode()
    prefer = "return=representation" if method == "GET" else "resolution=merge-duplicates,return=minimal"
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        data=data,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": prefer,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as res:
            raw = res.read()
            return json.loads(raw) if raw else []
    except urllib.error.HTTPError as exc:
        exc.read()
        exc.close()
    except Exception:
        pass
    _state["fail_until"] = time.time() + 120
    return None


def _class_index(data_dir):
    found = {}
    if not data_dir:
        return found
    try:
        for sub in tools.load_submissions(data_dir):
            found[sub["id"]] = sub
    except Exception:
        return {}
    return found


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def snapshot(board, data_dir=None, week=1):
    """Plain rows for one week. Week 1 is the class as it stands. Week 2 is after the rescue plan."""
    known = _class_index(data_dir)
    learners, marks, outcomes, scores, reports = [], [], [], [], []
    for row in board.get("learners") or []:
        learner_id = row.get("id")
        if not learner_id:
            continue
        meta = known.get(learner_id) or {}
        person = {"id": learner_id, "name": row.get("learner") or meta.get("learner") or learner_id}
        if meta.get("email"):
            person["email"] = meta["email"]
        previous = _number(meta.get("previous"))
        if previous is not None:
            person["previous"] = previous
        learners.append(person)
        theory, practical = row.get("theory") or {}, row.get("practical") or {}
        for kind, block in (("theory", theory), ("practical", practical)):
            marks.append({
                "learner_id": learner_id, "kind": kind, "week": week,
                "percent": _number(block.get("percent")), "score": _number(block.get("score")),
                "max_score": _number(block.get("max")), "result": None,
            })
        marks.append({
            "learner_id": learner_id, "kind": "overall", "week": week,
            "percent": _number(row.get("overall")), "score": None, "max_score": 100,
            "result": row.get("result"),
        })
        for group in (practical.get("outcomes") or [], row.get("windows") or []):
            if not isinstance(group, list):
                continue
            for source in group:
                if not isinstance(source, dict):
                    continue
                outcome_id = source.get("id")
                percent = _number(source.get("percent"))
                if not outcome_id or percent is None:
                    continue
                outcomes.append({
                    "learner_id": learner_id, "outcome_id": outcome_id, "week": week,
                    "percent": percent, "detail": source.get("detail") or "",
                })
        scores.append({
            "learner_id": learner_id, "week": week, "risk": _number(row.get("risk")),
            "band": row.get("band"), "overall": _number(row.get("overall")),
            "result": row.get("result"), "reason": row.get("reason") or "",
        })
        reports.append({"learner_id": learner_id, "week": week, "report": row})
    return {
        "learners": learners, "marks": marks, "practical_outcomes": outcomes,
        "risk_scores": scores, "score_reports": reports,
    }


def _fingerprint(board, week):
    parts = [str(week)]
    for row in board.get("learners") or []:
        parts.append(f"{row.get('id')}:{row.get('risk')}:{row.get('overall')}:{row.get('band')}")
    return "|".join(parts)


def _write_rows(rows):
    order = (
        ("learners?on_conflict=id", "learners"),
        ("marks?on_conflict=learner_id,kind,week", "marks"),
        ("practical_outcomes?on_conflict=learner_id,outcome_id,week", "practical_outcomes"),
        ("risk_scores?on_conflict=learner_id,week", "risk_scores"),
        ("score_reports?on_conflict=learner_id,week", "score_reports"),
    )
    for path, key in order:
        batch = rows.get(key) or []
        if batch and _request("POST", path, batch) is None:
            return False
    return True


def remember(board, data_dir=None):
    """Save a Week 1 board. A missing database, or a refused write, is ignored."""
    try:
        if not credentials() or _paused() or not isinstance(board, dict) or not board.get("learners"):
            return
        fp = _fingerprint(board, 1)
        if _state["saved"].get(1) == fp:
            return
        if _write_rows(snapshot(board, data_dir, week=1)):
            _state["saved"][1] = fp
    except Exception:
        _state["fail_until"] = time.time() + 120


def remember_week(result, data_dir=None):
    """Save the Week 2 comparison, the moved risk scores and one rescue-plan row per learner."""
    try:
        if not credentials() or _paused() or not isinstance(result, dict) or not result.get("ok"):
            return
        after = result.get("after")
        if not isinstance(after, dict) or not after.get("learners"):
            return
        fp = _fingerprint(after, 2)
        if _state["saved"].get(2) != fp:
            if not _write_rows(snapshot(after, data_dir, week=2)):
                return
            plans = []
            for change in result.get("changes") or []:
                plans.append({
                    "learner_id": change.get("id"),
                    "summary": result.get("summary") or "",
                    "risk_before": change.get("risk_before"),
                    "risk_after": change.get("risk_after"),
                    "band_before": change.get("band_before"),
                    "band_after": change.get("band_after"),
                    "overall_before": change.get("overall_before"),
                    "overall_after": change.get("overall_after"),
                    "result_before": change.get("result_before"),
                    "result_after": change.get("result_after"),
                })
            if plans and _request("POST", "rescue_plans", plans) is None:
                return
            _state["saved"][2] = fp
        if _request("POST", "week_runs?on_conflict=id", [{"id": 1, "payload": result}]) is None:
            return
        _state["week"] = result
        _state["miss_until"] = 0.0
    except Exception:
        _state["fail_until"] = time.time() + 120


def load_week():
    """The last Week 2 comparison, if Supabase has one. Otherwise None, and the files stand."""
    try:
        if _state["week"] is not None:
            return _state["week"]
        now = time.time()
        if not credentials() or now < _state["miss_until"] or now < _state["fail_until"]:
            return None
        rows = _request("GET", "week_runs?id=eq.1&select=payload")
        if rows is None:
            return None
        payload = rows[0].get("payload") if rows and isinstance(rows[0], dict) else None
        if not isinstance(payload, dict) or not payload.get("ok"):
            _state["miss_until"] = time.time() + 5
            return None
        _state["week"] = payload
        return payload
    except Exception:
        _state["fail_until"] = time.time() + 120
        return None


def clear_week():
    """Forget the comparison. Rescue-plan rows stay as history."""
    try:
        _state["week"] = None
        _state["miss_until"] = time.time() + 60
        _state["saved"].pop(2, None)
        if credentials() and not _paused():
            _request("DELETE", "week_runs?id=eq.1")
    except Exception:
        _state["fail_until"] = time.time() + 120


def _sql(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dict, list)):
        return _dollar(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return _dollar(str(value))


def _dollar(text):
    tag = "labless"
    while f"${tag}$" in text:
        tag += "x"
    return f"${tag}${text}${tag}$"


def _insert(table, columns, rows, conflict):
    if not rows:
        return ""
    lines = []
    for row in rows:
        lines.append("(" + ", ".join(_sql(row.get(column)) for column in columns) + ")")
    statement = (
        f"insert into public.{table} ({', '.join(columns)}) values\n  "
        + ",\n  ".join(lines)
    )
    if conflict:
        updates = ", ".join(f"{column} = excluded.{column}" for column in columns if column not in conflict)
        statement += f"\non conflict ({', '.join(conflict)}) do update set {updates}"
    return statement + ";\n"


def _policies():
    tables = ("learners", "marks", "practical_outcomes", "risk_scores", "rescue_plans", "score_reports", "week_runs")
    return "\n".join(
        f"alter table public.{name} enable row level security;\n"
        f"drop policy if exists {name}_read on public.{name};\n"
        f"create policy {name}_read on public.{name} for select to anon, authenticated using (true);\n"
        f"revoke insert, update, delete on public.{name} from anon, authenticated;\n"
        f"grant select on public.{name} to anon, authenticated;\n"
        f"grant select, insert, update, delete on public.{name} to service_role;"
        for name in tables
    )


def schema_sql():
    """Tables and row level security only. Apply this before supabase/seed.sql."""
    return f"""-- LabLess tables. Run this in the Supabase SQL editor, then run supabase/seed.sql.
-- Do not put keys in this file. The server reads SUPABASE_URL, SUPABASE_ANON_KEY
-- and SUPABASE_SERVICE_ROLE_KEY from the environment.

create table if not exists public.learners (
  id text primary key,
  name text not null,
  email text,
  previous integer
);

create table if not exists public.marks (
  learner_id text not null references public.learners (id) on delete cascade,
  kind text not null check (kind in ('theory', 'practical', 'overall')),
  week integer not null default 1 check (week in (1, 2)),
  percent integer,
  score integer,
  max_score integer,
  result text,
  primary key (learner_id, kind, week)
);

create table if not exists public.practical_outcomes (
  learner_id text not null references public.learners (id) on delete cascade,
  outcome_id text not null check (outcome_id in ('H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'S1', 'S2', 'S3', 'S4')),
  week integer not null default 1 check (week in (1, 2)),
  percent integer not null,
  detail text,
  primary key (learner_id, outcome_id, week)
);

create table if not exists public.risk_scores (
  learner_id text not null references public.learners (id) on delete cascade,
  week integer not null default 1 check (week in (1, 2)),
  risk integer not null,
  band text not null check (band in ('High', 'Medium', 'Low')),
  overall integer not null,
  result text not null,
  reason text,
  primary key (learner_id, week)
);

create table if not exists public.rescue_plans (
  id bigint generated always as identity primary key,
  learner_id text not null references public.learners (id) on delete cascade,
  summary text,
  risk_before integer,
  risk_after integer,
  band_before text,
  band_after text,
  overall_before integer,
  overall_after integer,
  result_before text,
  result_after text,
  created_at timestamptz not null default now()
);

create table if not exists public.score_reports (
  learner_id text not null references public.learners (id) on delete cascade,
  week integer not null default 1 check (week in (1, 2)),
  report jsonb not null,
  primary key (learner_id, week)
);

create table if not exists public.week_runs (
  id integer primary key,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);

{_policies()}
grant usage, select on all sequences in schema public to service_role;
"""


def seed_sql():
    """The demo class, including Week 2 for Bongani: risk 53 to 22, overall 57 to 78.

    week_runs is left empty so the dashboard still opens on Week 1.
    """
    before = risk.assess(DATA)
    after = week2.project(DATA)
    week1 = snapshot(before, DATA, week=1)
    week2_rows = snapshot(after["after"], DATA, week=2)
    plans = [{
        "learner_id": change["id"],
        "summary": after["summary"],
        "risk_before": change["risk_before"],
        "risk_after": change["risk_after"],
        "band_before": change["band_before"],
        "band_after": change["band_after"],
        "overall_before": change["overall_before"],
        "overall_after": change["overall_after"],
        "result_before": change["result_before"],
        "result_after": change["result_after"],
    } for change in after["changes"]]
    ids = ", ".join(_sql(row["id"]) for row in week1["learners"])
    return f"""-- LabLess demo class. Run supabase/migrations/20261113233000_lablest.sql first.
-- Week 1 for Bongani Sithole (E10) is risk 53 (High) and overall 57 (Pass).
-- Week 2, after the rescue plan, is risk 22 (Low) and overall 78 (Pass).
-- week_runs is left empty so the dashboard still opens on Week 1.

{_insert("learners", ["id", "name", "email", "previous"], week1["learners"], ["id"])}
{_insert("marks", ["learner_id", "kind", "week", "percent", "score", "max_score", "result"], week1["marks"] + week2_rows["marks"], ["learner_id", "kind", "week"])}
{_insert("practical_outcomes", ["learner_id", "outcome_id", "week", "percent", "detail"], week1["practical_outcomes"] + week2_rows["practical_outcomes"], ["learner_id", "outcome_id", "week"])}
{_insert("risk_scores", ["learner_id", "week", "risk", "band", "overall", "result", "reason"], week1["risk_scores"] + week2_rows["risk_scores"], ["learner_id", "week"])}
delete from public.rescue_plans where learner_id in ({ids});
{_insert("rescue_plans", ["learner_id", "summary", "risk_before", "risk_after", "band_before", "band_after", "overall_before", "overall_after", "result_before", "result_after"], plans, [])}
{_insert("score_reports", ["learner_id", "week", "report"], week1["score_reports"] + week2_rows["score_reports"], ["learner_id", "week"])}
"""
