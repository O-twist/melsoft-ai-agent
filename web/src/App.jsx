import { useCallback, useEffect, useState } from "react";
import { startRun, useRun } from "./api.js";
import { useTheme } from "./theme.js";
import { useRoute } from "./router.js";
import { DEFAULT_GOAL, PRACTICAL_GOAL, goalFor } from "./goals.js";
import { attention } from "./progress.js";
import AppShell from "./components/AppShell.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import Icon from "./components/Icon.jsx";
import { Disc } from "./components/Badge.jsx";
import Today from "./pages/Today.jsx";
import NewRun from "./pages/NewRun.jsx";
import Run from "./pages/Run.jsx";
import Runs from "./pages/Runs.jsx";
import Learners from "./pages/Learners.jsx";
import Classes from "./pages/Classes.jsx";
import Lab from "./pages/Lab.jsx";
import Messages from "./pages/Messages.jsx";
import Settings from "./pages/Settings.jsx";

function Splash({ offline, problem }) {
  return (
    <main className="splash">
      <span className="brand-mark"><Icon name="logo" size={22} strokeWidth="2.8" /></span>
      {problem ? (
        <>
          <h1>The server reported a problem</h1>
          <p>{problem}</p>
          <p className="h-note">Check the files in the data folder. This page carries on by itself once it is sorted.</p>
        </>
      ) : offline ? (
        <>
          <h1>Cannot reach your colleague</h1>
          <p>The dashboard is open but the server is not answering.</p>
          <p className="h-note">Start it with <code>start.cmd</code>, or <code>python run.py</code>. This page reconnects by itself.</p>
        </>
      ) : (
        <p>Loading…</p>
      )}
    </main>
  );
}

export default function App() {
  const { state, events, offline, problem, refresh } = useRun();
  const [theme, toggleTheme] = useTheme();
  const [route, go] = useRoute();
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [injectFault, setInjectFault] = useState(false);
  const [reviewFirst, setReviewFirst] = useState(true); // the run waits for the teacher to check the materials before planning
  const [scripts, setScripts] = useState(null); // photographed pages to read: { batch, pages } in reading order
  const [injectOcrFault, setInjectOcrFault] = useState(false);
  const [assessment, setAssessment] = useState("essay"); // essays, a subject test (maths, science, history), or the PC practical
  const [mine, setMine] = useState(null); // the teacher's own class, once uploaded and checked
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);
  const [focusId, setFocusId] = useState(null);
  const [notice, setNotice] = useState("");
  const closeDrawer = useCallback(() => setOpenId(null), []);

  // Joining a run that is already under way (a reload, or a second window): show the goal it was given.
  const runId = state?.id;
  useEffect(() => {
    if (runId && state.goal) {
      setGoal(state.goal);
      setInjectFault(Boolean(state.inject_fault));
      setInjectOcrFault(Boolean(state.inject_ocr_fault));
      setAssessment(state.assessment || "essay");
    }
    // Deliberately keyed on the run alone: this must not fire on every poll and undo the user's typing.
  }, [runId]);

  // A learner can be linked to from anywhere (#/learners?id=E04); that opens their drawer.
  const linkedId = route.page === "learners" ? route.params.id : null;
  useEffect(() => {
    if (linkedId) setOpenId(linkedId);
  }, [linkedId]);

  // When a run stops to have its materials checked, bring the teacher to them from wherever they are.
  const awaiting = Boolean(state?.review?.waiting);
  useEffect(() => {
    if (awaiting) go("run");
  }, [awaiting, runId, go]);

  if (!state) return <Splash offline={offline} problem={problem} />;

  const running = state.status === "running";
  const selected = state.subs.find((s) => s.id === openId);
  const failure = state.status === "failed" ? [...events].reverse().find((e) => e.kind === "ERROR") : null;

  /** Start a run from the current choices. Returns true if the server took it. */
  async function start() {
    setError("");
    setOpenId(null);
    try {
      const pages = scripts?.pages.length ? { batch: scripts.batch, order: scripts.pages.map((p) => p.id) } : null;
      const essays = assessment === "essay";
      await startRun(goal.trim(), injectFault, essays ? pages : null, injectOcrFault, assessment, essays ? mine?.class : null, reviewFirst);
      refresh();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }

  /** The next step for a learner who needs help: open their decision, or start a run that plans their catch-up. */
  async function rescue(row) {
    const sub = state.subs.find((s) => s.id === row.id);
    if (sub && (sub.status === "escalated" || sub.script_hold)) {
      setOpenId(row.id);
      return;
    }
    const practicalOn = Boolean(state.features?.practical) && row.practical?.in_class;
    const theoryPct = row.theory?.marked ? row.theory.percent : 0;
    const practicalPct = row.practical?.marked ? row.practical.percent : 0;
    const which = practicalOn && practicalPct < theoryPct ? "practical" : "essay";
    const existing = (state.support?.learners || []).find((entry) => entry.id === row.id);
    if (existing && (state.assessment === which || state.status === "done")) {
      setOpenId(row.id);
      return;
    }
    if (running) {
      go("run");
      return;
    }
    const base = which === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL;
    const goalText = `${row.learner} needs a rescue plan. ${base} Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.`;
    setAssessment(which);
    setGoal(goalText);
    setError("");
    setNotice(`Catch-up plan started for ${row.learner}. The Coach and the Designer are on this run.`);
    try {
      const pages = which === "essay" && scripts?.pages.length ? { batch: scripts.batch, order: scripts.pages.map((page) => page.id) } : null;
      await startRun(goalText, injectFault, pages, injectOcrFault, which, which === "essay" ? mine?.class : null, reviewFirst);
      refresh();
      go("run");
    } catch (e) {
      setNotice("");
      setError(e.message);
    }
  }

  const needs = attention(state);
  const counts = { today: needs.length, learners: state.risk?.counts?.High || 0 };
  const shared = { state, go, refresh, running };

  return (
    <AppShell page={route.page} go={go} state={state} offline={offline} counts={counts} testMode={injectFault || injectOcrFault}>
      {(offline || problem) && (
        <div className="banner" role="status">
          <Disc tone="serious" icon="alert" />
          <div>
            <b>{problem ? "The server reported a problem." : "Lost contact with the server."}</b>{" "}
            {problem || "Showing the last thing it sent. This page reconnects by itself."}
          </div>
        </div>
      )}

      {route.page === "today" && <Today {...shared} onOpen={setOpenId} onAddScripts={() => go("new")} />}

      {route.page === "new" && (
        <NewRun
          {...shared}
          goal={goal}
          onGoal={setGoal}
          assessment={assessment}
          onAssessment={setAssessment}
          scripts={scripts}
          onScripts={setScripts}
          injectOcrFault={injectOcrFault}
          onInjectOcrFault={setInjectOcrFault}
          mine={mine}
          onMine={setMine}
          reviewFirst={reviewFirst}
          onReviewFirst={setReviewFirst}
          onStart={start}
          error={error}
        />
      )}

      {route.page === "run" && (
        <Run
          {...shared}
          events={events}
          tab={route.params.tab || "progress"}
          onTab={(tab) => go("run", { tab })}
          onOpen={setOpenId}
          openId={openId}
          failure={failure}
        />
      )}

      {route.page === "runs" && <Runs {...shared} />}

      {route.page === "learners" && (
        <Learners
          {...shared}
          onOpen={setOpenId}
          onRescue={rescue}
          notice={notice}
          error={error}
          focusId={focusId}
          onFocus={setFocusId}
        />
      )}

      {route.page === "classes" && <Classes {...shared} mine={mine} onMine={setMine} assessment={assessment} />}

      {route.page === "lab" && <Lab {...shared} />}

      {route.page === "messages" && <Messages {...shared} onOpen={setOpenId} />}

      {route.page === "settings" && (
        <Settings
          {...shared}
          theme={theme}
          onToggleTheme={toggleTheme}
          injectFault={injectFault}
          onInjectFault={setInjectFault}
          injectOcrFault={injectOcrFault}
          onInjectOcrFault={setInjectOcrFault}
        />
      )}

      {selected && (
        <DetailDrawer
          sub={selected}
          rubric={state.rubric}
          support={state.support?.learners.find((e) => e.id === selected.id)}
          outcomes={state.outcomes}
          onClose={closeDrawer}
          onChanged={refresh}
        />
      )}
    </AppShell>
  );
}
