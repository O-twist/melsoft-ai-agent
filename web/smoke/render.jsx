/**
 * Renders every page once, against a state captured from the real server, and fails loudly if any
 * of them throws. It catches missing imports, bad prop shapes and crashes on first paint, which is
 * what the dashboard's own unit tests cannot see. Run with: npm run smoke
 */
import { readFileSync } from "node:fs";
import { renderToString } from "react-dom/server";
import Today from "../src/pages/Today.jsx";
import NewRun from "../src/pages/NewRun.jsx";
import Run from "../src/pages/Run.jsx";
import Runs from "../src/pages/Runs.jsx";
import Learners from "../src/pages/Learners.jsx";
import Classes from "../src/pages/Classes.jsx";
import Lab from "../src/pages/Lab.jsx";
import Messages from "../src/pages/Messages.jsx";
import Settings from "../src/pages/Settings.jsx";
import AppShell from "../src/components/AppShell.jsx";
import TeamThinking from "../src/components/TeamThinking.jsx";
import DetailDrawer from "../src/components/DetailDrawer.jsx";
import { attention, headline, steps } from "../src/progress.js";
import { examplesFor, goalFor, willHappen } from "../src/goals.js";

const state = JSON.parse(readFileSync(process.argv[2], "utf8"));
const noop = () => {};
const go = () => {};
const base = { state, go, refresh: noop, running: false };

const cases = [
  ["Today", <Today {...base} onOpen={noop} onAddScripts={noop} />],
  ["New run (step 1)", <NewRun {...base} goal={state.goal} onGoal={noop} assessment="essay" onAssessment={noop} scripts={null} onScripts={noop} injectOcrFault={false} onInjectOcrFault={noop} mine={null} onMine={noop} reviewFirst onReviewFirst={noop} onStart={noop} error="" />],
  ["Run · progress", <Run {...base} events={[]} tab="progress" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Run · submissions", <Run {...base} events={[]} tab="submissions" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Run · self-checks", <Run {...base} events={[]} tab="checks" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Run · results", <Run {...base} events={[]} tab="results" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Run · log", <Run {...base} events={[{ t: 1, agent: "PL", kind: "INFO", msg: "Goal received.", sid: null }]} tab="log" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Runs", <Runs {...base} />],
  ["Learners", <Learners {...base} onOpen={noop} onRescue={noop} notice="" error="" focusId={null} onFocus={noop} />],
  ["Learners · score report", <Learners {...base} onOpen={noop} onRescue={noop} notice="" error="" focusId={state.risk.learners[0].id} onFocus={noop} />],
  ["Classes", <Classes {...base} mine={null} onMine={noop} assessment="essay" />],
  ["Lab · attempts", <Lab {...base} />],
  ["Messages", <Messages {...base} onOpen={noop} />],
  ["Settings", <Settings {...base} theme="light" onToggleTheme={noop} injectFault={false} onInjectFault={noop} injectOcrFault={false} onInjectOcrFault={noop} />],
  ["Shell", <AppShell page="today" go={go} state={state} offline={false} counts={{ today: 2 }} testMode><p>body</p></AppShell>],
  ["Learner drawer", <DetailDrawer sub={state.subs[0]} rubric={state.rubric} support={state.support?.learners?.[0]} outcomes={state.outcomes} onClose={noop} onChanged={noop} />],
];

// An empty server, before anything has been loaded or run: every page must still say something useful.
const idle = {
  ...state, status: "idle", id: null, goal: "", subs: [], stats: { marked: 0, sent_back: 0, fixed: 0, escalated: 0, resubmit: 0, feedback_redone: 0, delivered: 0, human_interventions: 0 },
  plan: null, report: null, support: null, lesson: null, consistency: null, scripts: null, corrections: [], files: [],
  risk: { ok: true, learners: [], counts: {}, config: state.risk.config },
};
const idleBase = { state: idle, go, refresh: noop, running: false };
cases.push(
  ["Today (nothing yet)", <Today {...idleBase} onOpen={noop} onAddScripts={noop} />],
  ["Run (nothing yet)", <Run {...idleBase} events={[]} tab="progress" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  ["Runs (nothing yet)", <Runs {...idleBase} />],
  ["Learners (nothing yet)", <Learners {...idleBase} onOpen={noop} onRescue={noop} notice="" error="" focusId={null} onFocus={noop} />],
  ["Messages (nothing yet)", <Messages {...idleBase} onOpen={noop} />],
);

// Team thinking: every colleague's panel, on the plain run and on a run with handwritten scripts.
for (const key of ["PL", "MK", "RV", "MS", "CO", "DS", "CL"]) {
  cases.push([`Team thinking · ${key}`, <TeamThinking state={state} events={state.events} onOpen={noop} initialAgent={key} />]);
}
if (process.argv[4]) {
  const withScripts = JSON.parse(readFileSync(process.argv[4], "utf8"));
  cases.push(
    ["Team thinking · Clerk feedback (scripts)", <TeamThinking state={withScripts} events={withScripts.events} onOpen={noop} initialAgent="CL" />],
    ["Run · team thinking tab (scripts)", <Run state={withScripts} go={go} refresh={noop} running={false} events={withScripts.events} tab="thinking" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  );
  const html = renderToString(<TeamThinking state={withScripts} events={withScripts.events} onOpen={noop} initialAgent="CL" />);
  for (const want of ["Script S3", "Held for you", "page 2 of 2 is missing", "Read twice", "sure", "Planted fault", "Failed a check"]) {
    if (!html.includes(want)) { console.log(`FAIL the Clerk's feedback does not show "${want}"`); process.exitCode = 1; }
  }
  console.log("clerk feedback checks done");
}

// A run still going: the headline must count the step it is on, not just say "working".
if (process.argv[3]) {
  const live = JSON.parse(readFileSync(process.argv[3], "utf8"));
  const liveBase = { state: live, go, refresh: noop, running: true };
  cases.push(
    ["Today (mid-run)", <Today {...liveBase} onOpen={noop} onAddScripts={noop} />],
    ["Run (mid-run)", <Run {...liveBase} events={[]} tab="progress" onTab={noop} onOpen={noop} openId={null} failure={null} />],
  );
  const liveHead = headline(live);
  console.log(`mid-run headline: "${liveHead.title}" · ${Math.round(liveHead.fraction * 100)}%`);
  console.log(`mid-run steps: ${steps(live).map((r) => `${r.name} [${r.state}]`).join(" | ")}\n`);
  if (!/\d+ of \d+/.test(liveHead.title)) {
    console.log("FAIL the mid-run headline does not count how far it is");
    process.exitCode = 1;
  }
}

let bad = 0;
for (const [name, element] of cases) {
  try {
    const html = renderToString(element);
    if (!html.trim()) throw new Error("rendered nothing");
    console.log(`  ok   ${name} (${html.length} chars)`);
  } catch (e) {
    bad += 1;
    console.log(`  FAIL ${name}: ${e.message}`);
  }
}

// The helpers the pages lean on must agree with the real snapshot, not just not throw.
const head = headline(state);
const rows = steps(state);
console.log(`\nheadline: "${head.title}" · ${Math.round(head.fraction * 100)}%`);
console.log(`steps: ${rows.map((r) => `${r.name} [${r.state}]`).join(" | ")}`);
console.log(`attention: ${attention(state).length} item(s)`);
console.log(`goals: ${examplesFor("essay", state.features.tests).length} essay, ${examplesFor("maths", state.features.tests).length} maths`);
console.log(`maths goal: ${goalFor("maths", state.features.tests)}`);
console.log(`will happen: ${willHappen(state.goal, { scripts: true }).length} steps`);

if (rows.some((r) => r.state === "now") && state.status === "done") { console.log("FAIL a finished run still shows a step in progress"); bad += 1; }
if (head.fraction !== 1 && state.status === "done") { console.log("FAIL a finished run is not at 100%"); bad += 1; }

console.log(bad ? `\n${bad} page(s) failed` : "\nevery page rendered");
process.exit(bad ? 1 : 0);
