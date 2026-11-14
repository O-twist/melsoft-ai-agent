import assert from "node:assert/strict";
import { test } from "node:test";
import { nextStep, plainReason, runProgress, runTitle } from "./plain.js";

const sub = (id, extra = {}) => ({ id, status: "received", words: 200, marker: null, reviewer: null, final: null, feedback: null, ...extra });
const mark = { total: 30 };

test("risk reasons are put in plain words", () => {
  assert.equal(plainReason({ reason: "Theory 46% against a 50% pass line; did not finish the PC build, with 4 parts tried out of turn" }),
    "Essay 46%. Did not finish the PC build, with 4 parts tried out of turn.");
  assert.equal(plainReason({ reason: "No theory mark against a 50% pass line; no PC assembly attempt on record" }),
    "No essay marked yet. No PC build on record.");
  assert.equal(plainReason({ reason: "Theory 66% and PC assembly 100%, both on or above the 50% pass line" }), "Essay 66% and PC build 100%, both on track.");
  assert.match(plainReason({ reason: "x", theory_pass_note: "Passed theory, but the practical shows gaps: placed the GPU before the motherboard; placed the RAM before the CPU." }),
    /^Passed the essay, but the practical shows gaps: placed the GPU before the motherboard\.$/);
});

test("each learner gets one next step", () => {
  assert.equal(nextStep({ band: "High" }, sub("E10", { status: "escalated", script_hold: true })).label, "Decide on script");
  assert.equal(nextStep({ band: "High" }, sub("E08", { status: "resubmit", words: 9 })).label, "Ask to resubmit");
  assert.equal(nextStep({ band: "Medium" }, sub("E02", { status: "delivered" })).label, "Build catch-up plan");
  assert.equal(nextStep({ band: "Low" }, sub("E01", { status: "delivered" })).label, "Open");
});

test("the progress headline says how far the run has got", () => {
  const plan = { steps: ["a", "b"], batch_size: 4, deliver: { feedback: true } };
  const base = { status: "running", plan, stats: {}, elapsed: 10, rubric: { work: "essay" } };
  let p = runProgress({ ...base, plan: null, agents: { PL: "working" }, subs: [sub("E01"), sub("E02")] });
  assert.equal(p.headline, "Planning the work");
  assert.equal(p.steps[0].state, "now");
  const subs = [sub("E01", { marker: mark, reviewer: mark }), sub("E02", { marker: mark }), sub("E03", { marker: mark }), sub("E04", { status: "resubmit", words: 9 })];
  p = runProgress({ ...base, agents: { RV: "working" }, subs });
  assert.equal(p.headline, "Second-marking 1 of 3");
  assert.deepEqual(p.steps.map((s) => s.state), ["done", "done", "now", "todo", "todo"]);
  assert.match(p.steps[1].note, /1 set aside/);
  assert.ok(p.fraction > 0.3 && p.fraction < 0.97);
  assert.ok(p.eta >= 5);
  p = runProgress({ ...base, status: "done", agents: {}, subs });
  assert.equal(p.headline, "Finished");
  assert.equal(p.fraction, 1);
  assert.ok(p.steps.every((s) => s.state === "done"));
  assert.equal(runProgress({ ...base, status: "failed", agents: {}, subs }).headline, "This run stopped");
});

test("runs get a short title from the brief", () => {
  assert.equal(runTitle("Mark the Grade 12 CAT theory papers against the rubric and send every learner personalised feedback."), "Mark theory essays and send feedback");
  assert.equal(runTitle("Mark the PC assembly practical ... Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson"), "The whole job: PC assembly practical");
});
