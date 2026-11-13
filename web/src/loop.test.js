import { test } from "node:test";
import assert from "node:assert/strict";
import { advanceLoop, loopRank, loopStatus } from "./loop.js";

const idle = { status: "idle", agents: {}, subs: [], stats: {} };

test("before a run every phase is waiting", () => {
  const phases = loopStatus(advanceLoop(-1, idle), idle);
  assert.deepEqual(phases.map((phase) => phase.state), ["waiting", "waiting", "waiting", "waiting", "waiting"]);
});

test("the Marker lights Do, and a send-back moves the loop to Correct", () => {
  const marking = { status: "running", plan: { deliver: {} }, agents: { MK: "working" }, subs: [{ marker: { total: 1 } }], stats: {} };
  assert.equal(loopRank(marking), 1);
  const sentBack = { ...marking, stats: { sent_back: 1 } };
  assert.equal(loopRank(sentBack), 3);
  const phases = loopStatus(3, sentBack);
  assert.equal(phases.find((phase) => phase.id === "correct").state, "working");
  assert.equal(phases.find((phase) => phase.id === "plan").state, "done");
});

test("a later Reviewer pass does not rewind Deliver", () => {
  const delivering = {
    status: "running", plan: {}, agents: { RV: "working" }, subs: [{ marker: {}, reviewer: {}, final: {}, feedback: {} }],
    stats: {}, support: { learners: [] },
  };
  assert.equal(loopRank(delivering), 4);
  assert.equal(advanceLoop(4, delivering), 4);
});

test("a clean run marks Correct as nothing to fix", () => {
  const done = { status: "done", stats: { sent_back: 0 }, subs: [] };
  const phases = loopStatus(advanceLoop(2, done), done);
  assert.equal(phases.find((phase) => phase.id === "correct").state, "clear");
  assert.equal(phases.find((phase) => phase.id === "deliver").state, "done");
});
