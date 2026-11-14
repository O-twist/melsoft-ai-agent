import { useCallback, useEffect, useRef, useState } from "react";

async function post(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Cannot reach the server. Is it still running?");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || "The server could not do that.");
  return json;
}

/** scripts: { batch, order } of photographed pages for the Clerk to read, or null for typed essays only. */
/** review: the run waits, before anything is planned, for the teacher to check the memo, rubric and scripts. */
export const startRun = (goal, injectFault, scripts = null, injectOcrFault = false, assessment = "essay", classId = null, review = false) =>
  post("/api/run", { goal, inject_fault: injectFault, scripts, inject_ocr_fault: Boolean(scripts && injectOcrFault), assessment, class: classId, review });

/** The teacher's answer while a run waits on the materials: go ahead and plan (with an optional note), or stop. */
export const reviewRun = (go, note = "") => post("/api/review", { go, note });

/** The memo, the rubric and every learner's script: of the current run (fromRun), or what is on disk before a run. */
export async function fetchMaterials({ fromRun = false, assessment = "essay", classId = null } = {}) {
  const query = fromRun
    ? "source=run"
    : `assessment=${encodeURIComponent(assessment)}${classId ? `&class=${encodeURIComponent(classId)}` : ""}`;
  let res;
  try {
    res = await fetch(`/api/materials?${query}`);
  } catch {
    throw new Error("Cannot reach the server. Is it still running?");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || "Could not load the materials.");
  return json;
}

/** Upload a teacher's own class. files: { classList, essays: [], rubric, memo, outcomes }. Returns the server's summary. */
export async function uploadClass(files) {
  const form = new FormData();
  form.append("class_list", files.classList, files.classList.name);
  for (const essay of files.essays) form.append("essays", essay, essay.name);
  if (files.rubric) form.append("rubric", files.rubric, files.rubric.name);
  if (files.outcomes) form.append("outcomes", files.outcomes, files.outcomes.name);
  if (files.memo) form.append("memo", files.memo, files.memo.name);
  let res;
  try {
    res = await fetch("/api/class", { method: "POST", body: form });
  } catch {
    throw new Error("Cannot reach the server. Is it still running?");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(json.error || "The server could not take that class."), { problems: json.problems || [] });
  return json;
}
export const resolveEssay = (id, choice) => post("/api/resolve", { id, choice });
export const resolveScript = (id, choice, learner = null) => post("/api/resolve", { kind: "script", id, choice, learner });
export const fileUrl = (name) => `/api/file?name=${encodeURIComponent(name)}`;
export const pageUrl = (batch, id) => `/api/page?batch=${encodeURIComponent(batch)}&id=${encodeURIComponent(id)}`;

async function sendPages(url, form) {
  let res;
  try {
    res = await fetch(url, { method: "POST", body: form });
  } catch {
    throw new Error("Cannot reach the server. Is it still running?");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || "The server could not take those photos.");
  return json; // { batch, pages: [{ id, original, mime, bytes, sha256 }] }
}

/** Upload photos of handwritten pages. Pass the batch to add to one already started. */
export function uploadPages(files, batch = null) {
  const form = new FormData();
  if (batch) form.append("batch", batch);
  for (const file of files) form.append("pages", file, file.name);
  return sendPages("/api/ingest", form);
}

/** Keep an attempt from the virtual lab for the next practical run. Returns { ok, saved, log }. */
export const saveAttempt = (record) => post("/api/attempt", record);

/** The attempts recorded live in the virtual lab: [{ learner_id, saved }]. */
export async function listLiveAttempts() {
  const res = await fetch("/api/attempts");
  if (!res.ok) throw new Error("Could not list the recorded attempts.");
  return (await res.json()).attempts;
}

/** Start a batch with the sample handwritten scripts that ship in data/scripts. */
export const samplePages = () => sendPages("/api/ingest?sample=1", new FormData());

/**
 * Polls the server for the current run. The server only sends log lines we have not seen yet,
 * so the log is accumulated here and started afresh whenever a different run appears.
 *
 * Returns the latest state, the full log, whether the server is unreachable, any problem the
 * server reported, and refresh() to poll at once after an action.
 */
export function useRun(intervalMs = 700) {
  const [state, setState] = useState(null);
  const [events, setEvents] = useState([]);
  const [offline, setOffline] = useState(false);
  const [problem, setProblem] = useState("");
  const cursor = useRef({ run: undefined, since: 0 });
  const inFlight = useRef(false);

  const poll = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      // A second pass happens only when the run changed under us and its log must be read from the start.
      for (let pass = 0; pass < 2; pass++) {
        const res = await fetch(`/api/state?since=${cursor.current.since}`);
        const s = await res.json();
        if (!res.ok) {
          setProblem(s.error || "The server reported a problem.");
          setOffline(false);
          return;
        }
        const run = s.id || "idle";
        if (run !== cursor.current.run) {
          const midLog = cursor.current.since > 0;
          cursor.current = { run, since: 0 };
          setEvents([]);
          if (midLog) continue;
        }
        cursor.current.since = s.next;
        if (s.events.length) setEvents((prev) => [...prev, ...s.events]);
        setState(s);
        setOffline(false);
        setProblem("");
        return;
      }
    } catch {
      setOffline(true);
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let timer;
    const loop = async () => {
      await poll();
      if (alive) timer = setTimeout(loop, intervalMs);
    };
    loop();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [poll, intervalMs]);

  return { state, events, offline, problem, refresh: poll };
}
