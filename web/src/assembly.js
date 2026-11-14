/**
 * The PC assembly practical's rules, kept apart from the screen so they can be tested on their own.
 *
 * Ported from CompuClass's screens/PCAssemblyScreen.js: the same six parts, slot positions and order, and the
 * same two kinds of mistake. Trying a part before its turn is a wrong placement; dropping the right part
 * outside its slot is a slot miss. Both count as mistakes. What this adds is the record: every try is kept so
 * the attempt can be saved in the Phase 2 schema and marked from its log.
 */

/** `slot` is where the part sits in the open case, as fractions of case-open.png (from CompuClass). */
export const PARTS = [
  { id: "motherboard", name: "Motherboard", img: "motherboard.png",
    slot: { left: 0.14, top: 0.13, width: 0.46, height: 0.51 },
    tip: "Screw the motherboard onto the standoffs on the back plate of the case." },
  { id: "CPU", name: "CPU", img: "cpu.png",
    slot: { left: 0.3285, top: 0.25, width: 0.085, height: 0.11 },
    tip: "Line up the golden triangle and drop the CPU into the socket — no force needed." },
  { id: "RAM", name: "RAM", img: "ram.png", rotate: true,
    slot: { left: 0.466, top: 0.158, width: 0.068, height: 0.3 },
    tip: "Push the RAM sticks into the DIMM slots beside the CPU until the clips click." },
  { id: "GPU", name: "Graphics Card", img: "gpu.png",
    slot: { left: 0.05, top: 0.44, width: 0.42, height: 0.24 },
    tip: "Seat the graphics card in the long PCIe x16 slot and screw it to the rear bracket." },
  { id: "SSD", name: "SSD", img: "ssd.png",
    slot: { left: 0.675, top: 0.3, width: 0.12, height: 0.14 },
    tip: "Mount the SSD in the drive bay behind the motherboard tray." },
  { id: "PSU", name: "Power supply", img: "psu.png",
    slot: { left: 0.07, top: 0.72, width: 0.3, height: 0.19 },
    tip: "Slide the power supply into the bottom shroud, fan facing down." },
];
export const ORDER = PARTS.map((p) => p.id);
export const CASE_RATIO = 712 / 548; // width / height of case-open.png
export const HIT_PAD = 14; // px of forgiveness around small slots like the CPU

/** A fresh attempt for one learner. `now` is a clock in milliseconds. */
export function newAttempt(learnerId, now) {
  return { learnerId, startedAt: now, installed: [], tried: [], wrong: [], mistakes: 0, hints: 0, hinted: false, stoppedAt: null };
}

export const expectedPart = (a) => ORDER[a.installed.length] || null;
export const isDone = (a) => a.installed.length === ORDER.length;
const seconds = (a, now) => Math.max(0, Math.round((now - a.startedAt) / 1000));

/**
 * One try: the learner put `partId` into the case, on its slot or not. Returns [new attempt, what happened],
 * where what happened is "installed", "wrong_part" (tried out of turn) or "wrong_spot" (right part, missed the slot).
 */
export function tryPart(a, partId, onSlot, now) {
  if (isDone(a) || a.stoppedAt != null || a.installed.includes(partId)) return [a, "ignored"];
  const expected = expectedPart(a);
  if (partId === expected && onSlot) {
    return [{ ...a, installed: [...a.installed, partId], tried: [...a.tried, partId], hinted: false }, "installed"];
  }
  if (partId !== expected) {
    const wrong = [...a.wrong, { part: partId, expected, t: seconds(a, now) }];
    return [{ ...a, tried: [...a.tried, partId], wrong, mistakes: a.mistakes + 1 }, "wrong_part"];
  }
  return [{ ...a, mistakes: a.mistakes + 1 }, "wrong_spot"]; // not an order error, so not in order_tried
}

/** The learner asked for a hint on this step. Counted once per step. */
export function takeHint(a) {
  return a.hinted || isDone(a) ? a : { ...a, hints: a.hints + 1, hinted: true };
}

export const stop = (a, now) => (a.stoppedAt != null ? a : { ...a, stoppedAt: now });

/** The attempt in the Phase 2 schema (data/attempts/<learner>.json). */
export function toRecord(a, now) {
  const end = a.stoppedAt ?? now;
  return {
    learner_id: a.learnerId,
    order_tried: [...a.tried],
    mistakes: a.mistakes,
    hints: a.hints,
    wrong_placements: a.wrong.map((w) => ({ ...w })),
    completed: isDone(a),
    duration_seconds: seconds(a, end),
  };
}

/** Is the point (px, py), in case pixels, on the part's slot? The slot grows by HIT_PAD on every side. */
export function onSlot(part, px, py, caseW, caseH) {
  const s = part.slot;
  const x = s.left * caseW, y = s.top * caseH, w = s.width * caseW, h = s.height * caseH;
  return px >= x - HIT_PAD && px <= x + w + HIT_PAD && py >= y - HIT_PAD && py <= y + h + HIT_PAD;
}
