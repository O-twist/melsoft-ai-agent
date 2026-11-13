// The PC assembly rules, tested with Node's own test runner (no packages):  npm test  (inside web/)
import { test } from "node:test";
import assert from "node:assert/strict";
import { ORDER, PARTS, isDone, newAttempt, onSlot, stop, takeHint, toRecord, tryPart } from "./assembly.js";

const run = (steps, now = 0) => {
  let a = newAttempt("E05", now);
  const results = [];
  for (const [part, slot, t] of steps) {
    let what;
    [a, what] = tryPart(a, part, slot, t * 1000);
    results.push(what);
  }
  return [a, results];
};

test("a perfect build is six installs and a clean record", () => {
  const [a, results] = run(ORDER.map((p, i) => [p, true, 10 * (i + 1)]));
  assert.deepEqual(results, Array(6).fill("installed"));
  assert.ok(isDone(a));
  assert.deepEqual(toRecord(a, 75_000), {
    learner_id: "E05", order_tried: ORDER, mistakes: 0, hints: 0, wrong_placements: [], completed: true, duration_seconds: 75,
  });
});

test("a part out of turn is a wrong placement; the right part off its slot is a slot miss", () => {
  const [a, results] = run([["motherboard", true, 5], ["GPU", true, 41], ["CPU", false, 50], ["CPU", true, 55]]);
  assert.deepEqual(results, ["installed", "wrong_part", "wrong_spot", "installed"]);
  const record = toRecord(a, 60_000);
  assert.deepEqual(record.order_tried, ["motherboard", "GPU", "CPU"]); // the slot miss is not an order error
  assert.deepEqual(record.wrong_placements, [{ part: "GPU", expected: "CPU", t: 41 }]);
  assert.equal(record.mistakes, 2);
  assert.equal(record.completed, false);
});

test("hints count once a step, and stopping early freezes the clock", () => {
  let a = newAttempt("E07", 0);
  a = takeHint(takeHint(a));
  assert.equal(a.hints, 1);
  [a] = tryPart(a, "motherboard", true, 1000);
  a = takeHint(a);
  assert.equal(a.hints, 2);
  a = stop(a, 90_000);
  const [after, what] = tryPart(a, "CPU", true, 95_000);
  assert.equal(what, "ignored");
  assert.equal(toRecord(after, 500_000).duration_seconds, 90);
  assert.equal(toRecord(after, 500_000).completed, false);
});

test("an installed part cannot be installed twice", () => {
  const [a] = run([["motherboard", true, 1]]);
  const [b, what] = tryPart(a, "motherboard", true, 2000);
  assert.equal(what, "ignored");
  assert.equal(b, a);
});

test("drops are judged on the slot, with a little forgiveness", () => {
  const cpu = PARTS.find((p) => p.id === "CPU");
  assert.ok(onSlot(cpu, 0.37 * 712, 0.3 * 548, 712, 548));
  assert.ok(onSlot(cpu, 0.3285 * 712 - 10, 0.25 * 548, 712, 548)); // inside the 14px pad
  assert.ok(!onSlot(cpu, 0.9 * 712, 0.9 * 548, 712, 548));
});
