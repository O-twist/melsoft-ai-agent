/** Seconds as mm:ss. */
export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** What is being marked, from the rubric: "essay", or "practical attempt" for the PC assembly practical. */
export const workNoun = (rubric) => rubric?.work || "essay";
export const capital = (text) => `${text[0].toUpperCase()}${text.slice(1)}`;

/**
 * The agents, in the order work flows through them. The Clerk joins only a run that was given photos of
 * handwritten scripts; the server's list of agents says who is on the team for a run.
 */
export const AGENTS = {
  PL: { name: "Planner", job: "Plans the work and scores the risk" },
  CL: { name: "Clerk", job: "Reads photographed scripts" },
  MK: { name: "Marker", job: "Marks theory and the practical" },
  RV: { name: "Reviewer", job: "Marks again blind, checks the evidence" },
  MS: { name: "Messenger", job: "Writes feedback and score reports" },
  CO: { name: "Coach", job: "Writes each rescue plan" },
  DS: { name: "Designer", job: "Drafts the next lesson, without names" },
};

/** Who an entry in an essay's history belongs to: an agent key, or a tone for people and tests. */
export const WHO = {
  Planner: { agent: "PL" },
  Clerk: { agent: "CL" },
  Marker: { agent: "MK" },
  Reviewer: { agent: "RV" },
  Messenger: { agent: "MS" },
  Coach: { agent: "CO" },
  Designer: { agent: "DS" },
  Teacher: { tone: "accent", icon: "user" },
  Test: { tone: "warn", icon: "zap" },
};

/** Where a submission is in the workflow. Tone picks the colour; the icon and label always go with it. */
export const STATUS = {
  received: { label: "Received", tone: "idle", icon: "dot" },
  marked: { label: "Awaiting second mark", tone: "idle", icon: "clock" },
  disputed: { label: "Sent back", tone: "warn", icon: "undo" },
  agreed: { label: "Mark approved", tone: "good", icon: "check" },
  escalated: { label: "Needs teacher", tone: "serious", icon: "alert" },
  resubmit: { label: "Asked to resubmit", tone: "idle", icon: "undo" },
  delivered: { label: "Feedback sent", tone: "good", icon: "send" },
};

/** A submission's status as shown. An essay that was set aside only counts as "asked" once a request exists. */
export function statusOf(s) {
  if (s.status === "resubmit" && !s.feedback) return { label: "Not marked", tone: "idle", icon: "x" };
  return STATUS[s.status] || { label: s.status, tone: "idle", icon: "dot" };
}

export const FLAGS = {
  too_short: "Too short",
  missing: "Nothing submitted",
  instruction_to_marker: "Tries to instruct the marker",
};

/** How each kind of log line is shown. Lines with a tone are the ones worth noticing. */
export const KINDS = {
  INFO: {},
  PLAN: {},
  DECIDE: {},
  ACT: {},
  MARK: {},
  CHECK: {},
  WAIT: { quiet: true },
  FLAG: { tone: "warn", icon: "flag" },
  GUARD: { tone: "warn", icon: "shield" },
  TEST: { tone: "warn", icon: "zap", wash: true },
  REJECT: { tone: "warn", icon: "undo", wash: true },
  FIX: { tone: "accent", icon: "refresh", wash: true },
  APPROVE: { tone: "good", icon: "check" },
  ESCALATE: { tone: "serious", icon: "alert", wash: true },
  DROP: { tone: "serious", icon: "x", wash: true },
  HUMAN: { tone: "accent", icon: "user", wash: true },
  SEND: { tone: "good", icon: "send" },
  DONE: { tone: "good", icon: "check", wash: true },
  ERROR: { tone: "critical", icon: "alert", wash: true },
};

/** South African CAPS seven-point achievement scale, by percentage. */
export const LEVELS = [
  { n: 1, lo: 0, hi: 29, name: "Not achieved" },
  { n: 2, lo: 30, hi: 39, name: "Elementary" },
  { n: 3, lo: 40, hi: 49, name: "Moderate" },
  { n: 4, lo: 50, hi: 59, name: "Adequate" },
  { n: 5, lo: 60, hi: 69, name: "Substantial" },
  { n: 6, lo: 70, hi: 79, name: "Meritorious" },
  { n: 7, lo: 80, hi: 100, name: "Outstanding" },
];

export const pct = (score, max) => (max ? Math.round((100 * score) / max) : 0);
export const levelOf = (percent) => LEVELS.find((l) => percent <= l.hi) || LEVELS[LEVELS.length - 1];

/** True for essays whose mark is settled, which are the ones class figures are built from. */
export const settled = (s) => Boolean(s.final) && (s.status === "agreed" || s.status === "delivered");

/** Did the Marker's mark actually change after it was sent back? */
export const wasCorrected = (s) => Boolean(s.rejected && s.marker && s.rejected.total !== s.marker.total);

/** One short phrase for how the two markers ended up on an essay. */
export function outcomeOf(s) {
  if (s.status === "escalated") return { tone: "serious", icon: "alert", label: "Needs teacher" };
  if (s.history.some((h) => h.who === "Teacher")) return { tone: "accent", icon: "user", label: "Teacher decided" };
  if (s.status === "disputed") return { tone: "warn", icon: "undo", label: "Sent back" };
  if (s.status === "marked") return { tone: "idle", icon: "clock", label: "Awaiting second mark" };
  if (!s.final) return null;
  if (!s.rejected) return { tone: "good", icon: "check", label: "Agreed" };
  return wasCorrected(s)
    ? { tone: "warn", icon: "undo", label: "Sent back, corrected" }
    : { tone: "warn", icon: "undo", label: "Sent back, mark stood" };
}
