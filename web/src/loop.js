/** Plan → Do → Check → Correct → Deliver, read off the run the server already reports. */

export const LOOP = [
  { id: "plan", label: "Plan" },
  { id: "do", label: "Do" },
  { id: "check", label: "Check" },
  { id: "correct", label: "Correct" },
  { id: "deliver", label: "Deliver" },
];

function workingAgents(state) {
  const agents = state?.agents || {};
  return Object.keys(agents).filter((key) => agents[key] === "working");
}

/**
 * How far this snapshot has got, from -1 (not started) to 4 (deliver).
 * A later Reviewer pass does not rewind the loop: the caller keeps the furthest rank.
 */
export function loopRank(state) {
  if (!state) return -1;
  const status = state.status || "idle";
  if (status === "idle") return -1;
  if (status === "done") return 4;
  const working = workingAgents(state);
  const sentBack = (state.stats?.sent_back || 0) > 0;
  const subs = state.subs || [];
  let rank = status === "running" || status === "failed" ? 0 : -1;
  if (state.plan || working.includes("PL")) rank = Math.max(rank, 0);
  if (working.includes("CL") || working.includes("MK") || subs.some((sub) => sub.marker)) rank = Math.max(rank, 1);
  if (working.includes("RV") || subs.some((sub) => sub.reviewer || sub.final)) rank = Math.max(rank, 2);
  const correcting = (working.includes("MK") && sentBack)
    || (sentBack && subs.some((sub) => sub.status === "agreed" || sub.status === "escalated" || sub.status === "delivered"));
  if (correcting) rank = Math.max(rank, 3);
  const delivering = working.some((key) => key === "MS" || key === "CO" || key === "DS")
    || subs.some((sub) => sub.feedback)
    || Boolean(state.report || state.support || state.lesson);
  if (delivering) rank = Math.max(rank, 4);
  return rank;
}

/** Furthest phase reached on this run. Idle resets it. A finished run is Deliver. */
export function advanceLoop(previous, state) {
  if (!state || state.status === "idle" || !state.status) return -1;
  if (state.status === "done") return 4;
  return Math.max(previous ?? -1, loopRank(state));
}

/** Each phase is waiting, working, done, or clear (Correct, when nothing had to be fixed). */
export function loopStatus(frontier, state) {
  const sentBack = (state?.stats?.sent_back || 0) > 0;
  const status = state?.status || "idle";
  return LOOP.map((phase, index) => {
    const settled = phase.id === "correct" && !sentBack ? "clear" : "done";
    if (frontier < 0 || status === "idle") return { ...phase, state: "waiting" };
    if (status === "done") return { ...phase, state: settled };
    if (status === "failed") return { ...phase, state: index < frontier ? settled : "waiting" };
    if (index < frontier) return { ...phase, state: settled };
    if (index === frontier) {
      if (phase.id === "correct" && !sentBack) return { ...phase, state: "clear" };
      return { ...phase, state: "working" };
    }
    return { ...phase, state: "waiting" };
  });
}
