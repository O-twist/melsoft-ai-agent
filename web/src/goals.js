/** The goals the teacher can start from, in the words each kind of marking uses. */

export const DEFAULT_GOAL = "Mark the Grade 10 essays against the rubric and send every learner personalised feedback.";
export const PRACTICAL_GOAL = "Mark the PC assembly practical against the rubric and send every learner personalised feedback.";
export const testGoal = (label) => `Mark the Grade 10 ${label} test against the memo and send every learner personalised feedback.`;

const WHOLE = "Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.";
const BEHIND = "Then tell me who is falling behind, work out why, and prepare a catch-up plan for each of them.";

/** The goal to start from for whatever is being marked. */
export function goalFor(assessment, tests = []) {
  if (assessment === "practical") return PRACTICAL_GOAL;
  const test = tests.find((t) => t.key === assessment);
  return test ? testGoal(test.label) : DEFAULT_GOAL;
}

/** What is being marked, in a few words, for headings and buttons. */
export function workName(assessment, tests = []) {
  if (assessment === "practical") return "PC assembly practical";
  const test = tests.find((t) => t.key === assessment);
  return test ? `${test.label} test` : "English essays";
}

/**
 * The jobs a teacher can pick on the New run page. Each one is a whole goal, so the Planner reads
 * the same sentence whether it was chosen from a card or typed by hand.
 */
export function examplesFor(assessment, tests = []) {
  const base = goalFor(assessment, tests);
  const noMessages = base.replace(" and send every learner personalised feedback.", ".")
    + " Do not send feedback to learners: I only want the mark sheet and the class report.";
  const rows = [
    { id: "mark", label: "Mark and send feedback", why: "Marks every script, second-marks it blind, writes each learner a message.", goal: base },
    { id: "marks-only", label: "Marks only, no messages", why: "Mark sheet and class report. Nothing goes to learners.", goal: noMessages },
    { id: "behind", label: "Who is falling behind?", why: "Adds a catch-up plan for each learner who needs one.", goal: `${base} ${BEHIND}` },
    { id: "lesson", label: "Plan the next lesson", why: "Drafts a 45-minute lesson on the class's weakest area.", goal: `${base} Then draft a 45-minute lesson on the class's weakest area, with exercises checked against the learning outcomes.` },
    { id: "whole", label: "The whole job", why: "Marks, feedback, catch-up plans and a lesson.", goal: `${base} ${WHOLE}` },
  ];
  if (assessment === "essay") {
    rows.splice(4, 0, {
      id: "scripts",
      label: "Handwritten scripts too",
      why: "The Clerk reads the photographed pages first, then they are marked like typed work.",
      goal: `Read the photographed handwritten scripts first, then ${base[0].toLowerCase()}${base.slice(1)}`,
    });
  }
  return rows;
}

/** Which colleagues a goal brings in, so the New run page can say what will happen. */
export function willHappen(goal, { scripts = false, work = "essay" } = {}) {
  const g = goal.toLowerCase();
  const noSend = /(don'?t|do not|no|without)\s+(send|email|feedback)/.test(g);
  const support = /falling behind|fall(ing|en)? behind|catch[- ]?up|struggl|at risk|support plan/.test(g);
  const lesson = /lesson|exercise|worksheet/.test(g);
  const rows = [{ name: "Plan the work", who: "Planner", why: "Turns your brief into steps and picks who joins" }];
  if (scripts) rows.push({ name: "Read the handwritten pages", who: "Clerk", why: "Checks names against the class list and the page numbers" });
  rows.push(
    { name: `Mark each ${work}`, who: "Marker", why: "Against the rubric, quoting evidence" },
    { name: "Second-mark without seeing the first mark", who: "Reviewer", why: "Disagreements go back to the Marker, or to you" },
  );
  if (support) rows.push({ name: "Work out who is falling behind", who: "Coach", why: "A catch-up plan for each learner who needs one" });
  if (lesson) rows.push({ name: "Draft the next lesson", who: "Designer", why: "On the class's weakest area, with exercises tried blind" });
  rows.push(noSend
    ? { name: "Deliver the mark sheet and class report", who: "Messenger", why: "No messages to learners, as asked" }
    : { name: "Write and send feedback", who: "Messenger", why: "One message per learner" });
  return rows;
}
