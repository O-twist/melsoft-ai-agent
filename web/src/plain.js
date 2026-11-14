/** Plain words for the teacher: risk reasons, outcome names, and how far a run has got. */

export const OUTCOME_NAMES = {
  H1: "Safety and preparation", H2: "Build order", H3: "CPU and RAM", H4: "Cards and storage", H5: "Power last", H6: "Independent build",
  S1: "Create a folder", S2: "Rename a file", S3: "Change the wallpaper", S4: "Find system info",
};

/** "CPU and RAM" for H3, with the code kept for a tooltip. */
export const outcomeName = (id) => OUTCOME_NAMES[id] || id;

/** One short line a teacher can read: "Essay 46%. Did not finish the PC build, with 4 parts tried out of turn." */
export function plainReason(row) {
  if (!row) return "";
  if (row.theory_pass_note) {
    return "Passed the essay, but the practical shows gaps" + (row.theory_pass_note.split(":").slice(1).join(":").split(";")[0] ? `: ${row.theory_pass_note.split(":").slice(1).join(":").split(";")[0].trim()}.` : ".");
  }
  const text = String(row.reason || "")
    .replace(/Theory (\d+%) and PC assembly (\d+%), both on or above the \d+% pass line/i, "Essay $1 and PC build $2, both on track")
    .replace(/No theory mark against a \d+% pass line/gi, "No essay marked yet")
    .replace(/^Theory (\d+%)/i, "Essay $1")
    .replace(/ against a \d+% pass line/gi, "")
    .replace(/no PC assembly attempt on record/gi, "no PC build on record")
    .replace(/Theory (\d+%) and PC assembly (\d+%), both on or above the \d+% pass line/i, "Essay $1 and PC build $2, both on track");
  const parts = text.split(";").map((p) => p.trim()).filter(Boolean).map((p) => p[0].toUpperCase() + p.slice(1));
  return parts.join(". ") + (parts.length ? "." : "");
}

export const BAND_WORDS = { High: "Needs help now", Medium: "Keep an eye on", Low: "On track" };
export const BAND_TONE = { High: "hi", Medium: "md", Low: "ok" };

/** The one next step for a learner on the risk board. */
export function nextStep(row, sub) {
  if (sub?.status === "escalated" && sub.script_hold) return { key: "script", label: "Decide on script" };
  if (sub?.status === "escalated") return { key: "decide", label: "Decide on mark" };
  if (sub && (sub.status === "resubmit" || !sub.words)) return { key: "resubmit", label: "Ask to resubmit" };
  if (row.band === "High" || row.band === "Medium") return { key: "plan", label: "Build catch-up plan" };
  return { key: "open", label: "Open" };
}

const toMark = (subs) => subs.filter((s) => s.status !== "resubmit" && !s.script_hold);

/**
 * How far the run has got, in one headline and a fraction.
 * Returns { headline, fraction, eta, steps: [{ id, label, state, note }] }.
 */
export function runProgress(state) {
  const subs = state?.subs || [];
  const stats = state?.stats || {};
  const agents = state?.agents || {};
  const status = state?.status || "idle";
  const plan = state?.plan;
  const noun = state?.rubric?.work === "practical attempt" ? "attempt" : "essay";
  const nouns = (n) => `${n} ${noun}${n === 1 ? "" : "s"}`;
  const working = (k) => agents[k] === "working";
  const marking = toMark(subs);
  const n = marking.length || 1;
  const marked = marking.filter((s) => s.marker).length;
  const reviewed = marking.filter((s) => s.reviewer || s.final || s.status === "escalated").length;
  const settled = marking.filter((s) => s.final || s.status === "escalated").length;
  const wantsFeedback = plan ? plan.deliver?.feedback !== false : true;
  const fed = marking.filter((s) => s.feedback).length;
  const scripts = state?.scripts;
  const extra = plan && (plan.deliver?.support || plan.deliver?.lesson);

  let headline = "Ready";
  if (status === "done") headline = "Finished";
  else if (status === "failed") headline = "This run stopped";
  else if (status === "running") {
    if (!plan) headline = "Planning the work";
    else if (working("CL")) headline = "Reading the handwritten pages";
    else if (working("MK") && marked < marking.length) headline = `Marking ${Math.max(marked, 1)} of ${marking.length}`;
    else if (working("RV") && reviewed < marking.length) headline = `Second-marking ${Math.max(reviewed, 1)} of ${marking.length}`;
    else if (working("MK")) headline = `Correcting ${stats.sent_back || 1} sent back`;
    else if (working("MS") && wantsFeedback && fed < settled) headline = `Writing feedback ${Math.max(fed, 1)} of ${settled}`;
    else if (working("CO")) headline = "Writing catch-up plans";
    else if (working("DS")) headline = "Drafting the next lesson";
    else if (working("RV")) headline = "Checking the work";
    else if (working("MS")) headline = "Sending the results";
    else headline = "Finishing up";
  }

  let fraction = 0;
  if (status === "done") fraction = 1;
  else if (status === "running") {
    fraction = (plan ? 0.06 : 0.02) + 0.32 * (marked / n) + 0.3 * (reviewed / n);
    fraction += wantsFeedback ? 0.2 * (fed / n) : (settled === marking.length ? 0.2 : 0);
    if (extra && (working("CO") || working("DS") || state.support || state.lesson)) fraction += 0.06;
    fraction = Math.min(0.97, fraction);
  }
  const elapsed = state?.elapsed || 0;
  const eta = status === "running" && fraction > 0.12 ? Math.max(5, Math.round((elapsed / fraction - elapsed) / 5) * 5) : null;

  const done = status === "done";
  const stepState = (finished, active) => (done || finished ? "done" : active ? "now" : "todo");
  const steps = [];
  steps.push({
    id: "plan", label: "Plan the work", state: stepState(Boolean(plan), status === "running" && !plan),
    note: plan ? `${plan.steps?.length || 0} steps · marking ${plan.batch_size} at a time` : "The Planner reads your brief",
  });
  if (scripts || agents.CL) {
    const held = (scripts?.scripts || []).filter((r) => r.status === "held").length;
    const pages = scripts?.pages?.length || 0;
    steps.push({
      id: "read", label: `Read ${pages || "the"} handwritten page${pages === 1 ? "" : "s"}`,
      state: stepState(scripts?.status === "done" || agents.CL === "off", working("CL")),
      note: agents.CL === "off" ? "Not needed for this brief" : scripts?.status === "done" ? (held ? `${held} held for you` : "Every page passed its checks") : "Clerk · checks names and page numbers",
    });
  }
  const setAside = subs.filter((s) => s.status === "resubmit").length;
  steps.push({
    id: "mark", label: `Mark ${nouns(marking.length)}`, state: stepState(marked >= marking.length && marking.length > 0, working("MK") && marked < marking.length),
    note: setAside ? `${setAside} set aside: too short or nothing handed in` : `Marker · ${marked} of ${marking.length} done`,
  });
  steps.push({
    id: "check", label: "Second-mark without seeing the first mark",
    state: stepState(reviewed >= marking.length && marking.length > 0, working("RV") && reviewed < marking.length),
    note: `Reviewer · ${reviewed} of ${marking.length} done${stats.sent_back ? ` · ${stats.sent_back} sent back` : ""}${stats.escalated ? ` · ${stats.escalated} held for you` : ""}`,
  });
  steps.push({
    id: "correct", label: "Correct what failed a check",
    state: stepState(settled >= marking.length && marking.length > 0, working("MK") && marked >= marking.length),
    note: stats.sent_back ? `${stats.fixed || 0} of ${stats.sent_back} corrected · anything still wrong is held for you` : "Nothing sent back so far",
  });
  const deliverParts = [wantsFeedback ? "feedback" : "mark sheet", plan?.deliver?.support && "catch-up plans", plan?.deliver?.lesson && "a lesson"].filter(Boolean);
  steps.push({
    id: "deliver", label: `Deliver ${deliverParts.join(", ").replace(/, ([^,]*)$/, " and $1")}`,
    state: stepState(false, working("MS") || working("CO") || working("DS")),
    note: done ? `${stats.delivered || 0} messages ready${state.support ? ` · ${(state.support.learners || []).filter((e) => e.status === "ready").length} catch-up plans` : ""}` : "Starts when marks are settled",
  });
  return { headline, fraction, eta, steps };
}

/** A finished run, small enough to keep in a history list. */
export function runSummary(state) {
  const stats = state.stats || {};
  return {
    id: state.id, goal: state.goal, assessment: state.assessment, status: state.status,
    elapsed: state.elapsed, marked: stats.marked || 0, held: stats.escalated || 0, sent_back: stats.sent_back || 0,
    fixed: stats.fixed || 0, delivered: stats.delivered || 0, planted: state.corrections?.planted || 0,
    plans: (state.support?.learners || []).filter((e) => e.status === "ready").length,
    when: Date.now(),
  };
}

/** A short title for a run, from the brief the teacher gave. */
export function runTitle(goal) {
  const g = String(goal || "");
  const practical = /practical/i.test(g);
  const what = practical ? "PC assembly practical" : "theory essays";
  if (/lesson/i.test(g) && /falling behind|catch-up/i.test(g)) return `The whole job: ${what}`;
  if (/falling behind|catch-up/i.test(g)) return `Who is falling behind? ${practical ? "(practical)" : "(essays)"}`;
  if (/lesson/i.test(g)) return `Mark ${what} and plan the next lesson`;
  if (/handwritten/i.test(g)) return "Handwritten scripts and marking";
  if (/do not send feedback|no messages|only want the mark sheet/i.test(g)) return `Mark ${what}, no messages`;
  return `Mark ${what} and send feedback`;
}
