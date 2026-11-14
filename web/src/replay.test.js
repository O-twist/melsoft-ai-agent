import assert from "node:assert/strict";
import { test } from "node:test";
import { LONGEST, TAIL, finalState, replayAt, replaySpeed } from "./replay.js";
import { advanceLoop, loopStatus } from "./loop.js";

const mark = { total: 30, scores: {} };
const sub = (id, extra = {}) => ({ id, learner: `Learner ${id}`, status: "delivered", marker: mark, reviewer: mark, final: mark, feedback: { body: "Well done." }, ...extra });

/** A small finished run, recorded the way the server records one. */
function recording() {
  const waiting = { PL: "waiting", MK: "waiting", RV: "waiting", MS: "waiting", CO: "off", DS: "off" };
  const none = { E01: ["received", false, false, false, false], E02: ["received", false, false, false, false] };
  return {
    id: "run-1", status: "done", goal: "Mark the practical.", elapsed: 6, t: 6,
    agents: { PL: "done", MK: "done", RV: "done", MS: "done", CO: "off", DS: "off" },
    stats: { marked: 2, sent_back: 1, fixed: 1, delivered: 2 },
    plan: { understanding: "Mark it.", steps: ["Mark"], deliver: { feedback: true } },
    report: { summary: "Fine." }, support: null, lesson: null, consistency: null, scripts: null,
    subs: [sub("E01"), sub("E02")],
    spans: [
      { agent: "PL", what: "Planning", start: 0, end: 1 },
      { agent: "MK", what: "Marking", start: 1, end: 2 },
      { agent: "RV", what: "Second mark", start: 2, end: 3 },
      { agent: "MK", what: "Re-marking", start: 3, end: 4 },
      { agent: "MS", what: "Feedback", start: 4, end: 6 },
    ],
    files: ["marks.csv"], corrections: { stories: [{ subject: "E02: mark" }], counts: { fixed: 1 }, planted: 0 },
    events: [
      { t: 0, agent: "PL", kind: "INFO", msg: "Goal received." },
      { t: 1, agent: "PL", kind: "PLAN", msg: "Mark it." },
      { t: 2, agent: "MK", kind: "MARK", msg: "Marked 30/40.", sid: "E01" },
      { t: 3, agent: "RV", kind: "REJECT", msg: "Sent back to the Marker.", sid: "E02" },
      { t: 4, agent: "MK", kind: "FIX", msg: "Corrected the mark.", sid: "E02" },
      { t: 6, agent: "PL", kind: "DONE", msg: "2 marked." },
    ],
    frames: [
      { t: 0, n: 1, agents: { ...waiting, PL: "working" }, stats: {}, spans: 1, subs: none, has: [] },
      { t: 1, n: 2, agents: { ...waiting, MK: "working" }, stats: {}, spans: 2, subs: none, has: ["plan"] },
      { t: 2, n: 3, agents: { ...waiting, RV: "working" }, stats: {}, spans: 3,
        subs: { E01: ["marked", true, false, false, false], E02: ["marked", true, false, false, false] }, has: ["plan"] },
      { t: 3, n: 4, agents: { ...waiting, MK: "working" }, stats: { marked: 1, sent_back: 1 }, spans: 4,
        subs: { E01: ["agreed", true, true, true, false], E02: ["disputed", true, true, false, false] }, has: ["plan"] },
      { t: 4, n: 5, agents: { ...waiting, MS: "working" }, stats: { marked: 2, sent_back: 1, fixed: 1 }, spans: 5,
        subs: { E01: ["agreed", true, true, true, false], E02: ["agreed", true, true, true, false] }, has: ["plan"] },
      { t: 6, n: 6, agents: { ...waiting, MS: "working" }, stats: { marked: 2, sent_back: 1, fixed: 1, delivered: 2 }, spans: 5,
        subs: { E01: ["delivered", true, true, true, true], E02: ["delivered", true, true, true, true] }, has: ["plan", "report"] },
    ],
    file_texts: { "marks.csv": "id,total\n" },
  };
}

test("at the start nothing has been marked and the plan is not yet shown", () => {
  const { state, events, finished } = replayAt(recording(), 0.5);
  assert.equal(finished, false);
  assert.equal(state.status, "running");
  assert.equal(state.agents.PL, "working");
  assert.equal(state.plan, null);
  assert.equal(events.length, 1);
  assert.deepEqual(state.subs.map((s) => [s.status, s.marker, s.final]), [["received", null, null], ["received", null, null]]);
  assert.deepEqual(state.spans, [{ agent: "PL", what: "Planning", start: 0, end: null }]); // still at work, so the bar is open
});

test("each moment shows only what had happened by then", () => {
  const { state, events } = replayAt(recording(), 3.2);
  assert.equal(events.length, 4);
  assert.equal(events.at(-1).kind, "REJECT");
  assert.equal(state.stats.sent_back, 1);
  assert.deepEqual(state.subs.map((s) => s.status), ["agreed", "disputed"]);
  assert.equal(state.subs[1].final, null); // the disputed mark is not shown as settled
  assert.equal(state.subs[0].feedback, null); // nothing has been written to a learner yet
  assert.equal(state.report, null);
  assert.equal(state.corrections, null);
  assert.deepEqual(state.files, []);
  assert.equal(state.spans.length, 4);
  assert.equal(state.spans[2].end, 3); // the Reviewer's second mark is over
  assert.equal(state.spans[3].end, null); // the Marker is re-marking now
});

test("the loop lights up in order through a playback, and Correct shows the send-back", () => {
  const run = recording();
  let frontier = -1;
  const rows = [];
  const at = {};
  for (let s = 0; s <= 8; s += 0.25) {
    const { state } = replayAt(run, s);
    frontier = advanceLoop(frontier, state);
    at[s] = loopStatus(frontier, state).map((p) => p.state);
    rows.push(at[s]);
  }
  assert.deepEqual(at[0.5], ["working", "waiting", "waiting", "waiting", "waiting"]); // Plan is at work first
  assert.deepEqual(at[3.5], ["done", "done", "done", "working", "waiting"]); // Correct, while the Marker re-marks
  const settled = rows.map((row) => row.filter((s) => s === "done" || s === "clear").length);
  assert.deepEqual(settled, [...settled].sort((a, b) => a - b)); // phases only ever move forward
  assert.deepEqual(rows.at(-1), ["done", "done", "done", "done", "done"]);
});

test("past the end it is the finished run, exactly as the server reported it", () => {
  const run = recording();
  const { state, events, finished } = replayAt(run, 6 + TAIL);
  assert.equal(finished, true);
  assert.deepEqual(state, finalState(run));
  assert.equal(state.status, "done");
  assert.equal(events.length, 6);
  assert.equal(state.frames, undefined);
  assert.equal(replayAt(run, Infinity).finished, true);
  assert.equal(replayAt(run, 5.9).finished, false);
});

test("a run with nothing recorded is shown finished at once", () => {
  const { frames, ...plain } = recording();
  assert.equal(replayAt(plain, 0).finished, true);
  assert.equal(replayAt({ ...plain, frames: [] }, 0).state.status, "done");
});

test("a long run is played back faster, never slower", () => {
  const run = recording();
  assert.equal(replaySpeed(run), 1);
  const long = { ...run, frames: run.frames.map((f) => ({ ...f, t: f.t * 20 })) }; // two minutes of live-model work
  assert.equal(replaySpeed(long), 120 / LONGEST);
  assert.equal(replayAt(long, LONGEST / 2).events.length, 4); // half way through playback is half way through the run
  assert.equal(replayAt(long, LONGEST + 1).finished, true);
});
