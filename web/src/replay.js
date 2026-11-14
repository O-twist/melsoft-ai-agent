/**
 * Playing back a run that finished inside one request.
 *
 * On a serverless deployment the server cannot keep a run going between requests, so it does the whole
 * loop in the request that starts it and sends back the finished run with a small picture ("frame") of
 * where things stood at every log line. Here that recording is turned back into what the dashboard
 * would have seen if it had polled at a given moment, so the loop, the team board and the log fill in
 * step by step exactly as they do against a local server.
 */

export const LONGEST = 30; // seconds a playback may take; a longer run is played faster
export const TAIL = 0.6; // seconds the last step stays "working" before the run shows as finished

const PARTS = { plan: "plan", report: "report", support: "support", lesson: "lesson", consistency: "consistency", intake: "scripts" };
const EMPTY = { t: 0, n: 0, agents: null, stats: {}, spans: 0, subs: {}, has: [] };

/** How many seconds of the run one second of playback covers. */
export function replaySpeed(run) {
  const frames = run?.frames || [];
  const total = frames.length ? frames[frames.length - 1].t : 0;
  return total > LONGEST ? total / LONGEST : 1;
}

/** The finished run as the server last reported it, without the recording. */
export function finalState(run) {
  const { frames, file_texts: fileTexts, events, ...state } = run;
  return state;
}

/** The run as it stood when `frame` was taken, `now` seconds in. */
function stateAt(run, frame, now) {
  const has = new Set(frame.has || []);
  const state = finalState(run);
  const waiting = Object.fromEntries(Object.keys(run.agents || {}).map((key) => [key, "waiting"]));
  const parts = Object.fromEntries(Object.entries(PARTS).map(([flag, key]) => [key, has.has(flag) ? run[key] : null]));
  return {
    ...state,
    ...parts,
    status: "running",
    agents: frame.agents || waiting,
    stats: frame.stats || {},
    spans: (run.spans || []).slice(0, frame.spans).map((span) => (span.end == null || span.end > now ? { ...span, end: null } : span)),
    subs: (run.subs || []).map((sub) => {
      const at = frame.subs?.[sub.id];
      if (!at) return { ...sub, status: "received", marker: null, reviewer: null, final: null, feedback: null };
      const [status, marker, reviewer, final, feedback] = at;
      return {
        ...sub, status,
        marker: marker ? sub.marker : null, reviewer: reviewer ? sub.reviewer : null,
        final: final ? sub.final : null, feedback: feedback ? sub.feedback : null,
      };
    }),
    files: [],
    corrections: null,
    elapsed: Math.round(now),
    t: now,
  };
}

/**
 * What the dashboard shows `seconds` after playback began.
 * Returns { state, events, finished }. Past the end, or with nothing recorded, it is the finished run.
 */
export function replayAt(run, seconds) {
  const frames = run?.frames || [];
  const total = frames.length ? frames[frames.length - 1].t : 0;
  const now = seconds * replaySpeed(run);
  if (!frames.length || !(now < total + TAIL)) {
    return { state: finalState(run), events: run.events || [], finished: true };
  }
  let frame = EMPTY;
  for (const next of frames) {
    if (next.t > now) break;
    frame = next;
  }
  return { state: stateAt(run, frame, Math.min(now, total)), events: (run.events || []).slice(0, frame.n), finished: false };
}
