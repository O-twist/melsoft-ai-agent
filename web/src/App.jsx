import { useCallback, useEffect, useState } from "react";
import { fileUrl, heldWeek, holdWeek, resetWeek2, runWeek2, startRun, useRun } from "./api.js";
import Icon from "./components/Icon.jsx";
import { Disc } from "./components/Badge.jsx";
import TopBar from "./components/TopBar.jsx";
import GoalBar, { DEFAULT_GOAL, PRACTICAL_GOAL } from "./components/GoalBar.jsx";
import StatTiles from "./components/StatTiles.jsx";
import TeamBoard from "./components/TeamBoard.jsx";
import PlanCard from "./components/PlanCard.jsx";
import LiveLog from "./components/LiveLog.jsx";
import SubmissionsTable from "./components/SubmissionsTable.jsx";
import AgreementChart from "./components/AgreementChart.jsx";
import LevelsChart from "./components/LevelsChart.jsx";
import CriteriaMeters from "./components/CriteriaMeters.jsx";
import ClassReport from "./components/ClassReport.jsx";
import SupportCard from "./components/SupportCard.jsx";
import LessonCard from "./components/LessonCard.jsx";
import ConsistencyCard from "./components/ConsistencyCard.jsx";
import ScriptIngest from "./components/ScriptIngest.jsx";
import IngestReview from "./components/IngestReview.jsx";
import PCAssembly from "./components/PCAssembly.jsx";
import WindowsStation from "./components/WindowsStation.jsx";
import PartModels from "./components/PartModels.jsx";
import CorrectionsPanel from "./components/CorrectionsPanel.jsx";
import ClassUpload from "./components/ClassUpload.jsx";
import DetailDrawer from "./components/DetailDrawer.jsx";
import RiskBoard from "./components/RiskBoard.jsx";
import LoopStatus from "./components/LoopStatus.jsx";
import ScoreReport from "./components/ScoreReport.jsx";

const DOWNLOADS = [
  { name: "marks.csv", label: "Mark sheet (CSV)" },
  { name: "class_report.md", label: "Class report" },
];

/**
 * Bring a section to the top of the window and keep it there while the page settles. The lab's pictures, the 3D
 * model and the simulator finish loading after the scroll starts and push the target away, so aim again until
 * it holds still. The first touch or wheel movement hands the page back to the person using it.
 */
function settleOn(id, forMs = 3500) {
  const target = document.getElementById(id);
  if (!target) return undefined;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  const began = Date.now();
  const stop = () => {
    clearInterval(timer);
    window.removeEventListener("wheel", stop);
    window.removeEventListener("touchstart", stop);
  };
  const timer = setInterval(() => {
    const age = Date.now() - began;
    if (age > forMs) return stop();
    const margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
    if (age > 700 && Math.abs(target.getBoundingClientRect().top - margin) > 24) target.scrollIntoView({ behavior: "auto", block: "start" });
    return undefined;
  }, 250);
  window.addEventListener("wheel", stop, { passive: true });
  window.addEventListener("touchstart", stop, { passive: true });
  return stop;
}

function Splash({ offline, problem }) {
  return (
    <main className="splash">
      {problem ? (
        <>
          <h1>The server reported a problem</h1>
          <p>{problem}</p>
          <p className="splash-hint">Check the files in the data folder, then this page will carry on by itself.</p>
        </>
      ) : offline ? (
        <>
          <h1>Cannot reach LabLess</h1>
          <p>Start the server with <code>start.cmd</code> or <code>python run.py</code>. This page reconnects by itself.</p>
        </>
      ) : (
        <p>Loading…</p>
      )}
    </main>
  );
}

export default function App() {
  const { state, events, offline, problem, refresh } = useRun();
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [injectFault, setInjectFault] = useState(false);
  const [scripts, setScripts] = useState(null); // photographed pages to read: { batch, pages } in reading order
  const [injectOcrFault, setInjectOcrFault] = useState(false);
  const [assessment, setAssessment] = useState("essay"); // essays, or the PC assembly practical
  const [mine, setMine] = useState(null); // the teacher's own class, once uploaded and checked
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);
  const [view, setView] = useState("board"); // landing is the at-risk list; the marking desk stays mounted
  const [focusId, setFocusId] = useState(null);
  const [notice, setNotice] = useState("");
  const [weekHold, setWeekHold] = useState(heldWeek);
  const [station, setStation] = useState(null);
  const [partId, setPartId] = useState("");
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

  useEffect(() => {
    if (!station) return;
    const id = station.kind === "windows" ? "windows-station" : station.kind === "model" ? "part-viewer" : "virtual-lab";
    return settleOn(id);
  }, [station]);

  if (!state) return <Splash offline={offline} problem={problem} />;

  const week2 = state.week2?.ok ? state.week2 : weekHold;

  const running = state.status === "running";
  const selected = state.subs.find((s) => s.id === openId);
  const hasMarks = state.subs.some((s) => s.marker);
  const failure = state.status === "failed" ? [...events].reverse().find((e) => e.kind === "ERROR") : null;
  const downloads = DOWNLOADS.filter((d) => state.files.includes(d.name));
  // The Coach and the Designer only work when the goal asks for them, so their cards appear only then.
  const wantsSupport = Boolean(state.plan?.deliver.support);
  const wantsLesson = Boolean(state.plan?.deliver.lesson);
  const behind = (state.support?.learners || []).map((e) => e.id);

  async function start() {
    setError("");
    setOpenId(null);
    try {
      const pages = scripts?.pages.length ? { batch: scripts.batch, order: scripts.pages.map((p) => p.id) } : null;
      const essays = assessment === "essay";
      await startRun(goal.trim(), injectFault, essays ? pages : null, injectOcrFault, assessment, essays ? mine?.class : null);
      refresh();
      // Bring the progress, the team and the log into view: from here on the goal box is not the interesting part.
      settleOn("loop-status");
    } catch (e) {
      setError(e.message);
    }
  }

  function openReport(id) {
    setFocusId(id);
    setView("report");
  }

  function openCatchUp(learner, link) {
    setStation({ ...link, learnerId: learner.id, nonce: Date.now() });
    if (link.kind === "model") setPartId(link.target);
    if (link.kind !== "windows") setAssessment("practical");
    setView("desk");
  }

  async function week(learnerId) {
    setError("");
    try {
      const result = await runWeek2(learnerId || null);
      if (result?.ok) {
        holdWeek(result);
        setWeekHold(result);
      }
      refresh();
      setNotice(learnerId ? `Week 2 scored for ${learnerId}.` : "Week 2 scored for the class.");
    } catch (e) {
      setNotice("");
      setError(e.message);
    }
  }

  async function clearWeek() {
    setError("");
    try {
      await resetWeek2();
      holdWeek(null);
      setWeekHold(null);
      refresh();
      setNotice("");
    } catch (e) {
      setError(e.message);
    }
  }

  function openDesk(kind) {
    if (kind === "practical" || kind === "essay") {
      setAssessment(kind);
      setGoal(kind === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL);
    }
    setView("desk");
  }

  async function rescue(row) {
    const practicalOn = Boolean(state.features?.practical) && row.practical?.in_class;
    const theoryPct = row.theory?.marked ? row.theory.percent : 0;
    const practicalPct = row.practical?.marked ? row.practical.percent : 0;
    const which = practicalOn && practicalPct < theoryPct ? "practical" : "essay";
    const existing = (state.support?.learners || []).find((entry) => entry.id === row.id);
    if (existing && (state.assessment === which || state.status === "done")) {
      setView("desk");
      setOpenId(row.id);
      return;
    }
    if (running) {
      setView("desk");
      return;
    }
    const base = which === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL;
    const goalText = `${row.learner} needs a rescue plan. ${base} Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.`;
    setAssessment(which);
    setGoal(goalText);
    setError("");
    setNotice(`Rescue plan started for ${row.learner}. The Coach and the Designer are on this run.`);
    try {
      const pages = which === "essay" && scripts?.pages.length ? { batch: scripts.batch, order: scripts.pages.map((page) => page.id) } : null;
      await startRun(goalText, injectFault, pages, injectOcrFault, which, which === "essay" ? mine?.class : null);
      refresh();
    } catch (e) {
      setNotice("");
      setError(e.message);
    }
  }

  const high = state.risk?.counts?.High;

  return (
    <div className="app-frame">
      <nav className="dock no-print" aria-label="Views">
        <p className="dock-brand">LABLESS</p>
        {[
          ["board", "Home", "home"],
          ["report", "Reports", "flag"],
          ["desk", "Lab", "chip"],
        ].map(([key, label, icon]) => (
          <button
            key={key}
            type="button"
            className={view === key ? "on" : ""}
            aria-current={view === key ? "page" : undefined}
            onClick={() => setView(key)}
          >
            <Icon name={icon} size={18} />
            <span className="label-full">{label}{key === "board" && high ? ` · ${high}` : ""}</span>
          </button>
        ))}
      </nav>
      <div className="app-main">
      <TopBar
        llm={state.llm}
        status={state.status}
        elapsed={state.elapsed}
        offline={offline}
      />

      {(offline || problem || failure) && (
        <div className="page page-tight no-print">
          {(offline || problem) && (
            <div className="banner" role="status">
              <Disc tone="serious" icon="alert" />
              <div>
                <b>{problem ? "The server reported a problem." : "Lost contact with the server."}</b>{" "}
                {problem || "Showing the last thing it sent. This page reconnects by itself."}
              </div>
            </div>
          )}
          {failure && (
            <div className="banner banner-critical" role="alert">
              <Disc tone="critical" icon="alert" />
              <div>
                <b>The run stopped before it finished.</b> {failure.msg.replace(/^Run stopped:\s*/, "")}
              </div>
            </div>
          )}
        </div>
      )}

      {view === "board" && (
        <div className="page no-print">
          <RiskBoard state={{ ...state, week2 }} onReport={openReport} onRescue={rescue} onWeek2={week} onWeekReset={clearWeek} onDesk={openDesk} notice={notice} error={error} />
        </div>
      )}
      {view === "report" && (
        <div className="page">
          <ScoreReport risk={state.risk} week2={week2} focusId={focusId} onCatchUp={openCatchUp} />
        </div>
      )}

      <main className="page" hidden={view !== "desk"}>
        <GoalBar
          goal={goal}
          onGoal={setGoal}
          injectFault={injectFault}
          onInjectFault={setInjectFault}
          running={running}
          hasRun={Boolean(state.id)}
          onStart={start}
          error={error}
          assessment={assessment}
          practicalAvailable={Boolean(state.features?.practical)}
          onAssessment={(next) => {
            setAssessment(next);
            setGoal(next === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL);
          }}
        />

        {(assessment === "practical" || station?.kind === "model" || station?.kind === "lab" || station?.kind === "windows") && (
          <header className="lab-hero">
            <h2>{station?.kind === "windows" ? "Windows 11 tasks" : "Your virtual lab"}</h2>
            <p>{station?.kind === "windows" ? "Software practical · outcomes S1–S4. Simulator by win11.blueedge.me." : "Hardware practical · outcomes H1–H6. Drag a part into the glowing spot, or open a 3D model."}</p>
          </header>
        )}
        {(assessment === "practical" || station?.kind === "model") && (
          <div id="virtual-lab">
            <PCAssembly
              subs={state.subs}
              focus={station?.kind === "lab" ? station : station?.kind === "model" ? { learnerId: station.learnerId, step: station.target, nonce: station.nonce } : null}
              onViewModel={(id) => {
                setPartId(id);
                document.getElementById("part-viewer")?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            />
          </div>
        )}
        {(assessment === "practical" || station?.kind === "model") && (
          <PartModels part={partId || (station?.kind === "model" ? station.target : "pc")} nonce={station?.nonce} />
        )}

        <WindowsStation subs={state.subs} focus={station?.kind === "windows" ? station : null} onSaved={refresh} />

        {/* Photographed scripts are essays, so the card is offered only when essays are being marked. */}
        {assessment === "essay" && <ClassUpload mine={mine} onMine={setMine} running={running} />}

        {assessment === "essay" && (
          <ScriptIngest
            scripts={scripts}
            onScripts={setScripts}
            injectOcrFault={injectOcrFault}
            onInjectOcrFault={setInjectOcrFault}
            running={running}
          />
        )}

        <section className="card" id="loop-status">
          <header className="card-head">
            <div>
              <h2>The loop</h2>
              <p>Plan → Do → Check → Correct → Deliver. Anything that fails a check goes back once, then to the teacher.</p>
            </div>
          </header>
          <LoopStatus state={state} />
        </section>

        <StatTiles stats={state.stats} subs={state.subs} plan={state.plan} rubric={state.rubric} />

        <div className="cols wide-narrow">
          <TeamBoard agents={state.agents} spans={state.spans} now={state.t} status={state.status} />
          <PlanCard plan={state.plan} status={state.status} />
        </div>

        <div className="cols even">
          <LiveLog events={events} onOpen={setOpenId} />
          <SubmissionsTable subs={state.subs} rubric={state.rubric} behind={behind} selectedId={openId} onOpen={setOpenId} />
        </div>

        <CorrectionsPanel corrections={state.corrections} status={state.status} subs={state.subs} onOpen={setOpenId} />

        {state.scripts && (
          <IngestReview scripts={state.scripts} subs={state.subs} status={state.status} files={state.files} onOpen={setOpenId} onChanged={refresh} />
        )}

        {hasMarks && (
          <>
            <div className="section-head">
              <div>
                <h2>Results</h2>
                <p>
                  {running ? "Filling in as each batch is checked." : "From the marks the two markers settled on."}
                  {state.where && downloads.length > 0 && <> Files are saved in <span className="mono">{state.where}</span>.</>}
                </p>
              </div>
              {downloads.length > 0 && (
                <div className="downloads">
                  {downloads.map((d) => (
                    <a key={d.name} className="btn small" href={fileUrl(d.name)} download={d.name}>
                      <Icon name="download" size={14} />{d.label}
                    </a>
                  ))}
                </div>
              )}
            </div>

            <div className="cols wide-narrow">
              <AgreementChart subs={state.subs} rubric={state.rubric} selectedId={openId} onOpen={setOpenId} />
              <div className="stack">
                <LevelsChart subs={state.subs} rubric={state.rubric} />
                <CriteriaMeters subs={state.subs} rubric={state.rubric} />
              </div>
            </div>
          </>
        )}

        {(wantsSupport || wantsLesson) && (
          <>
            <div className="section-head">
              <div>
                <h2>Beyond the marks</h2>
                <p>
                  {wantsSupport && wantsLesson
                    ? "Who needs help, what to teach next, and whether the two agree"
                    : wantsSupport ? "Who needs help" : "What to teach next"}
                  , worked out from the settled marks.
                </p>
              </div>
            </div>
            {wantsSupport && (
              <SupportCard support={state.support} outcomes={state.outcomes} status={state.status} files={state.files} onOpen={setOpenId} noun={state.rubric?.work} />
            )}
            {wantsLesson && (
              <LessonCard lesson={state.lesson} outcomes={state.outcomes} status={state.status} files={state.files} practical={state.rubric?.kind === "practical"} />
            )}
            {wantsSupport && wantsLesson && (
              <ConsistencyCard consistency={state.consistency} status={state.status} />
            )}
          </>
        )}

        {state.report && <ClassReport report={state.report} noun={state.rubric?.work} onOpen={setOpenId} />}
      </main>

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
      </div>
    </div>
  );
}
