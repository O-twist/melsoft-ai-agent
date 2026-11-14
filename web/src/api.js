import { useCallback, useEffect, useRef, useState } from "react";
import { replayAt } from "./replay.js";

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
export const startRun = (goal, injectFault, scripts = null, injectOcrFault = false, assessment = "essay", classId = null) =>
  post("/api/run", { goal, inject_fault: injectFault, scripts, inject_ocr_fault: Boolean(scripts && injectOcrFault), assessment, class: classId });

/** Upload a teacher's own class. files: { classList, essays: [], rubric, outcomes }. Returns the server's summary. */
export async function uploadClass(files) {
  const form = new FormData();
  form.append("class_list", files.classList, files.classList.name);
  for (const essay of files.essays) form.append("essays", essay, essay.name);
  if (files.rubric) form.append("rubric", files.rubric, files.rubric.name);
  if (files.outcomes) form.append("outcomes", files.outcomes, files.outcomes.name);
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

const RUN_KEY = "lablest.run";
const TEXT_TYPES = { csv: "text/csv", md: "text/markdown", txt: "text/plain" };
let heldFiles = {}; // the text files of a run this browser is holding, by name

/**
 * A run that finished inside the request that started it (a serverless deployment). The browser keeps it,
 * so the page can play it back and still show it when the next request lands on an instance with no memory.
 */
export function heldRun() {
  try {
    const run = JSON.parse(sessionStorage.getItem(RUN_KEY) || "null");
    heldFiles = run?.file_texts || {};
    return run && run.id ? run : null;
  } catch {
    return null;
  }
}

export function holdRun(run) {
  heldFiles = run?.file_texts || {};
  try {
    if (run) sessionStorage.setItem(RUN_KEY, JSON.stringify(run));
    else sessionStorage.removeItem(RUN_KEY);
  } catch {
    // A full browser store must not stop the demo: the run still plays, it just will not survive a refresh.
  }
}

/** Where to download one of the run's files: from the server, or from the run this browser is holding. */
export const fileUrl = (name) => {
  if (name in heldFiles) {
    const type = TEXT_TYPES[name.split(".").pop()] || "text/plain";
    return `data:${type};charset=utf-8,${encodeURIComponent(heldFiles[name])}`;
  }
  return `/api/file?name=${encodeURIComponent(name)}`;
};
export const correctionsUrl = () => ("corrections.md" in heldFiles ? fileUrl("corrections.md") : "/api/corrections.md");
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
export const runWeek2 = (learnerId) => post("/api/week2", learnerId ? { learner: learnerId } : {});
export const resetWeek2 = () => post("/api/week2", { reset: true });

const WEEK_KEY = "lablest.week2";

/** Week 2 from the last response, so a serverless instance without memory can still show it. */
export function heldWeek() {
  try {
    const raw = sessionStorage.getItem(WEEK_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && parsed.ok ? parsed : null;
  } catch {
    return null;
  }
}

export function holdWeek(result) {
  try {
    if (result && result.ok) sessionStorage.setItem(WEEK_KEY, JSON.stringify(result));
    else sessionStorage.removeItem(WEEK_KEY);
  } catch {
    // A full browser store must not stop the demo.
  }
}
export const submitWindows = (learnerId, answers) => post("/api/windows", { learner_id: learnerId, answers });

/** The Windows checklist, without the answers the Reviewer is holding. */
export async function windowsTasks() {
  const res = await fetch("/api/windows");
  if (!res.ok) throw new Error("Could not load the Windows tasks.");
  return res.json();
}

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
  // A run handed over whole by a serverless server: { run, began }. `began` is when playback started,
  // or null once it has been shown to the end (and after a refresh, when there is nothing to play back).
  const [held, setHeld] = useState(() => {
    const run = heldRun();
    return run ? { run, began: null } : null;
  });
  const [, setTick] = useState(0);

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

  /** Take over a run the server finished inside the request (or pass null to go back to polling for one). */
  const adopt = useCallback((run) => {
    holdRun(run || null);
    setHeld(run ? { run, began: Date.now() } : null);
  }, []);

  // While a held run is playing back, redraw a few times a second so the loop and the log move.
  const playing = Boolean(held?.began);
  useEffect(() => {
    if (!playing) return undefined;
    const timer = setInterval(() => setTick((n) => n + 1), 150);
    return () => clearInterval(timer);
  }, [playing]);

  if (state && held) {
    const view = replayAt(held.run, held.began == null ? Infinity : (Date.now() - held.began) / 1000);
    if (view.finished && held.began != null) setTimeout(() => setHeld((now) => (now && now.run === held.run ? { run: now.run, began: null } : now)), 0);
    // The class, the risk scores and Week 2 still come from the server; the run itself comes from the recording.
    return { state: { ...state, ...view.state }, events: view.events, offline, problem, refresh: poll, adopt };
  }

  return { state, events, offline, problem, refresh: poll, adopt };
}
