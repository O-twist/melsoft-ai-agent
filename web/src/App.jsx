import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMe, heldWeek, holdWeek, loadSampleClass, runWeek2, samplePages, saveRunSummary, startRun, useRun } from "./api.js";
import { useAuth } from "./auth.js";
import { DEFAULT_GOAL, PRACTICAL_GOAL } from "./components/GoalBar.jsx";
import ScoreReport from "./components/ScoreReport.jsx";
import { runSummary, runTitle } from "./plain.js";
import { RUNS_KEY, TEST_KEY, TEST_OFF, remember, usePref } from "./prefs.js";
import { go, useRoute } from "./router.js";
import Auth from "./pages/Auth.jsx";
import Classes from "./pages/Classes.jsx";
import Lab from "./pages/Lab.jsx";
import Learners, { LearnerDrawer } from "./pages/Learners.jsx";
import Messages from "./pages/Messages.jsx";
import NewRun from "./pages/NewRun.jsx";
import Run from "./pages/Run.jsx";
import Runs from "./pages/Runs.jsx";
import Settings from "./pages/Settings.jsx";
import Shell from "./pages/Shell.jsx";
import Today, { attentionItems } from "./pages/Today.jsx";
import { Confirm, Ico } from "./pages/ui.jsx";

const GUEST_KEY = "lablest.guest";

export default function App() {
  const auth = useAuth();
  const [guest, setGuest] = useState(() => {
    try {
      return sessionStorage.getItem(GUEST_KEY) === "1";
    } catch {
      return false;
    }
  });
  if (!auth.ready) return <div className="l-auth"><p style={{ color: "#5F6779" }}>Loading LabLess…</p></div>;
  if (auth.enabled && !auth.session && !guest) {
    return <Auth onGuest={() => { try { sessionStorage.setItem(GUEST_KEY, "1"); } catch { /* still works for this visit */ } setGuest(true); }} />;
  }
  return <Workspace auth={auth} />;
}

const CRUMBS = {
  today: "Today", new: "Runs / New run", run: "Runs / Latest run", runs: "Runs", learners: "Learners", classes: "Classes",
  lab: "Lab", messages: "Messages", settings: "Settings", report: "Learners / Score report",
};

function Workspace({ auth }) {
  const { state, events, offline, problem, refresh, adopt } = useRun();
  const route = useRoute();
  const [menu, setMenu] = useState(false);
  const [mine, setMine] = useState(null);
  const [scripts, setScripts] = useState(null);
  const [test] = usePref(TEST_KEY, TEST_OFF);
  const runsKey = `${RUNS_KEY}.${auth.session?.user?.id || "guest"}`; // each teacher's history is their own
  const [history] = usePref(runsKey, []);
  const [drawer, setDrawer] = useState(null); // { id, tab }
  const [ask, setAsk] = useState(null); // a learner whose catch-up plan run is waiting for a yes
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [weekView, setWeekView] = useState("1");
  const [weekHold, setWeekHold] = useState(heldWeek);
  const [profile, setProfile] = useState(null);
  const [serverRuns, setServerRuns] = useState([]);
  const rescueFor = useRef(null);
  const uid = auth.session?.user?.id;
  const [onboarded, setOnboarded] = usePref(`lablest.onboarded.${uid || "guest"}`, false);

  useEffect(() => {
    if (!uid) return;
    fetchMe().then((me) => {
      if (!me) return;
      setProfile(me.profile || null);
      setServerRuns(me.runs || []);
      if ((me.runs || []).length || (me.classes || []).length) setOnboarded(true);
    });
  }, [uid, setOnboarded]);

  // A learner opened by address (#/learners/E10) opens the drawer.
  const linked = route.page === "learners" ? route.parts[1] : null;
  useEffect(() => {
    if (linked) setDrawer({ id: linked, tab: route.query.tab || "overview" });
  }, [linked, route.query.tab]);
  // Moving to another page closes the drawer and the phone menu.
  useEffect(() => {
    if (!linked) setDrawer(null);
    setMenu(false);
  }, [route.page, linked]);

  // Keep finished runs in the history, here and in the teacher's account.
  const status = state?.status;
  useEffect(() => {
    if (!state?.id || (status !== "done" && status !== "failed")) return;
    const summary = runSummary(state);
    remember(summary, runsKey);
    if (uid) saveRunSummary(summary);
    const who = rescueFor.current;
    if (who && who.after !== state.id) {
      rescueFor.current = null;
      const entry = (state.support?.learners || []).find((e) => e.id === who.id);
      setNotice(entry?.status === "ready" ? `Catch-up plan ready for ${who.name}.` : entry ? `The Coach's plan for ${who.name} failed its checks twice, so it is held for you.` : `No warning sign was found for ${who.name} in this work, so no catch-up plan was needed.`);
      setDrawer({ id: who.id, tab: "overview" });
    }
    // Keyed on the run ending, not on every poll.
  }, [state?.id, status]);

  const week2 = state?.week2?.ok ? state.week2 : weekHold;
  const uploads = state?.features?.uploads !== false;
  const practicalOn = Boolean(state?.features?.practical);
  const testOn = Boolean(test.fault || test.ocr);
  const teacher = profile?.display_name || auth.session?.user?.name || "";
  const allRuns = [...history, ...serverRuns.filter((r) => !history.some((h) => h.id === r.id))].sort((a, b) => (b.when || 0) - (a.when || 0));

  const openLearner = useCallback((id, tab = "overview") => setDrawer({ id, tab }), []);
  const closeDrawer = useCallback(() => {
    setDrawer(null);
    if (linked) go("learners");
  }, [linked]);

  async function launch(goal, assessment, classId, pages, fault, ocr, review = false) {
    const out = await startRun(goal, fault, pages, ocr, assessment, classId, review);
    adopt(out.run); // a serverless server hands the finished run back to be played here; a local one is polled
    refresh();
    go("run");
  }

  async function startFromForm({ goal, assessment, classId, scripts: wantScripts, review }) {
    let pages = null;
    if (wantScripts) {
      let batch = scripts;
      if (!batch?.pages?.length && test.sample) {
        batch = await samplePages();
        setScripts(batch);
      }
      if (batch?.pages?.length) pages = { batch: batch.batch, order: batch.pages.map((p) => p.id) };
    }
    await launch(goal, assessment, classId, pages, test.fault, Boolean(pages && test.ocr), review);
  }

  function action(row, step) {
    if (step.key === "plan") setAsk(row);
    else if (step.key === "resubmit") openLearner(row.id, "messages");
    else openLearner(row.id, step.key === "decide" ? "essay" : "overview");
  }

  async function buildPlan(row) {
    setBusy(true);
    const practical = practicalOn && row.practical?.in_class && (row.practical?.marked ? row.practical.percent : 0) < (row.theory?.marked ? row.theory.percent : 0);
    const which = practical ? "practical" : "essay";
    const goal = `${row.learner} needs a rescue plan. ${which === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL} Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.`;
    try {
      rescueFor.current = { id: row.id, name: row.learner, after: state?.id };
      setDrawer(null);
      await launch(goal, which, null, null, test.fault, false);
      setNotice(`Building a catch-up plan for ${row.learner}. The Coach and the Designer are on this run.`);
    } catch (e) {
      rescueFor.current = null;
      setNotice(e.message);
    } finally {
      setBusy(false);
      setAsk(null);
    }
  }

  async function scoreWeek2(id) {
    try {
      const result = await runWeek2(id || null);
      if (result?.ok) {
        holdWeek(result);
        setWeekHold(result);
        setWeekView("2");
      }
      refresh();
    } catch (e) {
      setNotice(e.message);
    }
  }

  async function chooseWeek(view) {
    setWeekView(view);
    if (view === "2" && !week2) await scoreWeek2();
  }

  function catchUp(row, link) {
    setDrawer(null);
    const n = Date.now();
    if (link.kind === "windows") go("lab", { tab: "windows", learner: row.id, task: link.target, n });
    else if (link.kind === "model") go("lab", { tab: "parts", part: link.target, learner: row.id, n });
    else go("lab", { tab: "pc", learner: row.id, step: link.target, n });
  }

  async function loadSample() {
    await loadSampleClass();
    setMine(null);
    setOnboarded(true);
  }

  // A run that stops for the materials to be checked brings the teacher to it, from whichever page they are on.
  const awaiting = Boolean(state?.review?.waiting);
  useEffect(() => {
    if (awaiting) go("run");
  }, [awaiting, state?.id]);

  const page = CRUMBS[route.page] ? route.page : "today";
  const items = attentionItems(state);
  const badges = { today: items.length || null, learners: state?.risk?.counts?.High || null };
  const crumb = page === "run" && state?.id ? <>Runs / <b>{runTitle(state.goal)}</b></> : <b>{CRUMBS[page]}</b>;

  const onboarding = auth.enabled && uid && !onboarded ? (
    <div className="l-page narrow">
      <div className="l-head"><div><h1>Welcome{teacher ? `, ${teacher}` : ""}</h1><div className="l-sub">Create your first class, then start your first run.</div></div></div>
      <div className="l-row">
        <section className="l-card" style={{ flex: 1 }}><div className="bd">
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Load the sample Grade 12 CAT class</h2>
          <p className="l-muted" style={{ margin: "6px 0 14px" }}>Twelve example learners with essays, PC assembly attempts and Windows tasks. No real learner data.</p>
          <button type="button" className="l-btn p" onClick={loadSample}>Load the sample class</button>
        </div></section>
        <section className="l-card" style={{ flex: 1 }}><div className="bd">
          <h2 style={{ fontSize: 15, fontWeight: 600 }}>Upload your own class</h2>
          <p className="l-muted" style={{ margin: "6px 0 14px" }}>A CSV class list (id, name, email, previous) and one .txt essay per learner.</p>
          <button type="button" className="l-btn" onClick={() => { setOnboarded(true); go("classes"); }}>Upload a class</button>
        </div></section>
      </div>
    </div>
  ) : null;

  let body;
  if (!state) body = <div className="l-page"><div className="l-skel" style={{ height: 28, width: 260, marginBottom: 16 }} /><div className="l-kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="l-skel" style={{ height: 90 }} />)}</div><div className="l-skel" style={{ height: 300 }} /></div>;
  else if (page === "today") body = <Today state={state} history={allRuns} teacher={teacher} onOpenLearner={openLearner} onAction={action} onChanged={refresh} onboarding={onboarding} />;
  else if (page === "new") body = <NewRun state={state} mine={mine} scripts={scripts} onScripts={setScripts} test={test} uploads={uploads} practicalOn={practicalOn} start={startFromForm} initialScripts={route.query.scripts === "1"} canPause={!state.features?.replay} />;
  else if (page === "run") body = <Run state={state} events={events} tab={route.query.tab || "progress"} onTab={(t) => go("run", { tab: t })} onOpen={openLearner} onChanged={refresh} onRunAgain={() => launch(state.goal, state.assessment, null, null, state.inject_fault, false)} />;
  else if (page === "runs") body = <Runs state={state} history={allRuns} />;
  else if (page === "learners") body = <Learners state={state} week2={week2} weekView={weekView} onWeek={chooseWeek} onOpen={openLearner} onAction={action} />;
  else if (page === "classes") body = <Classes state={state} mine={mine} onMine={setMine} uploads={uploads} scripts={scripts} onChanged={refresh} onLoadSample={auth.enabled && uid ? loadSample : null} />;
  else if (page === "lab") body = <Lab state={state} query={route.query} onChanged={refresh} />;
  else if (page === "messages") body = <Messages state={state} />;
  else if (page === "settings") body = <Settings state={state} tab={route.query.tab || "test"} auth={auth} profile={profile} onProfile={setProfile} uploads={uploads} />;
  else if (page === "report") body = (
    <div className="l-page">
      <button type="button" className="l-btn sm no-print" style={{ marginBottom: 12 }} onClick={() => go("learners")}><Ico name="undo" size={14} />Back to learners</button>
      <ScoreReport key={`${route.parts[1]}-${route.query.mode}`} risk={state.risk} week2={week2} focusId={route.parts[1] || null} initialMode={route.query.mode === "class" ? "class" : "learner"} initialWeek={route.query.week === "2" && week2 ? "after" : "before"} onCatchUp={catchUp} />
    </div>
  );

  return (
    <Shell page={page === "report" ? "learners" : page === "run" ? "runs" : page} crumb={crumb} badges={badges} llm={state?.llm} className={mine?.name || "Grade 12 CAT"} learners={(state?.subs || []).length || 12}
      testOn={testOn} menuOpen={menu} onMenu={setMenu}>
      {(offline || problem) && (
        <div className="l-callout bad" role="status" style={{ marginBottom: 14 }}>
          <b>{problem ? "The server reported a problem." : "Lost contact with LabLess."}</b> {problem || "Showing the last thing it sent. This page reconnects by itself."}
        </div>
      )}
      {notice && (
        <div className="l-callout" role="status" style={{ marginBottom: 14, display: "flex", gap: 10, alignItems: "center" }}>
          <span style={{ flex: 1 }}>{notice}</span><button type="button" className="l-btn sm ghost" onClick={() => setNotice("")} aria-label="Dismiss"><Ico name="x" size={14} /></button>
        </div>
      )}
      {body}
      {drawer && state && (
        <LearnerDrawer id={drawer.id} tab={drawer.tab} onTab={(t) => setDrawer({ ...drawer, tab: t })} state={state} week2={week2} weekView={weekView}
          onClose={closeDrawer} onChanged={refresh} onAction={action} onCatchUp={catchUp} onWeek2={(id) => scoreWeek2(id)} />
      )}
      {ask && (
        <Confirm title={`Build a catch-up plan for ${ask.learner}?`} yes="Start" busy={busy} onYes={() => buildPlan(ask)} onNo={() => setAsk(null)}>
          This starts a run: the class is marked again, the Coach writes a catch-up plan for each learner who is behind, and the Designer drafts a lesson. About 1 minute.
        </Confirm>
      )}
    </Shell>
  );
}
