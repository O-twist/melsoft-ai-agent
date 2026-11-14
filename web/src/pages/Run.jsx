import Icon from "../components/Icon.jsx";
import { Disc } from "../components/Badge.jsx";
import TeamBoard from "../components/TeamBoard.jsx";
import PlanCard from "../components/PlanCard.jsx";
import LiveLog from "../components/LiveLog.jsx";
import SubmissionsTable from "../components/SubmissionsTable.jsx";
import AgreementChart from "../components/AgreementChart.jsx";
import LevelsChart from "../components/LevelsChart.jsx";
import CriteriaMeters from "../components/CriteriaMeters.jsx";
import ClassReport from "../components/ClassReport.jsx";
import SupportCard from "../components/SupportCard.jsx";
import LessonCard from "../components/LessonCard.jsx";
import ConsistencyCard from "../components/ConsistencyCard.jsx";
import CorrectionsPanel from "../components/CorrectionsPanel.jsx";
import IngestReview from "../components/IngestReview.jsx";
import MaterialsPanel from "../components/MaterialsPanel.jsx";
import LoopStatus from "../components/LoopStatus.jsx";
import { fileUrl } from "../api.js";
import { headline, steps } from "../progress.js";
import { clock, plural } from "../format.js";

const DOWNLOADS = [
  { name: "marks.csv", label: "Mark sheet (CSV)" },
  { name: "class_report.md", label: "Class report" },
  { name: "corrections.md", label: "Self-check report" },
  { name: "scripts/all_pages.pdf", label: "Photo PDF" },
  { name: "scripts/clerk_report.md", label: "Clerk's report" },
];

const TABS = [
  ["progress", "Progress"],
  ["submissions", "Submissions"],
  ["checks", "Self-checks"],
  ["results", "Results"],
  ["scripts", "Clerk's reading"],
  ["log", "Activity log"],
];

/** One run, from the brief to the files it wrote. Everything about it lives behind these tabs. */
export default function Run({ state, events, go, tab, onTab, onOpen, openId, refresh, failure }) {
  if (state.status === "idle") {
    return (
      <section className="card">
        <div className="card-body empty-state">
          <h3>No run yet</h3>
          <p>Start one and this page shows the progress, the checks it ran on itself, and the files it wrote.</p>
          <button type="button" className="btn primary" onClick={() => go("new")}><Icon name="plus" size={15} />New run</button>
        </div>
      </section>
    );
  }

  const running = state.status === "running";
  const head = headline(state);
  const rows = steps(state);
  const downloads = DOWNLOADS.filter((d) => state.files.includes(d.name));
  const hasMarks = state.subs.some((s) => s.marker);
  const wantsSupport = Boolean(state.plan?.deliver.support);
  const wantsLesson = Boolean(state.plan?.deliver.lesson);
  const behind = (state.support?.learners || []).map((e) => e.id);
  const counts = {
    submissions: state.subs.length,
    checks: (state.corrections || []).length,
    scripts: state.scripts?.scripts?.length || 0,
  };
  const shown = TABS.filter(([key]) => key !== "scripts" || state.scripts);

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">{state.goal}</h2>
          <p className="lede">
            {running ? "Started" : state.status === "done" ? "Finished" : "Stopped"} · {clock(state.elapsed)} ·{" "}
            {plural(state.subs.length, "learner")}
            {state.scripts && " · handwritten scripts included"}
            {state.inject_fault && " · test mode"}
          </p>
        </div>
        <div className="head-actions">
          {running
            ? <span className="chip"><span className="live-dot" />Running · <span className="num">{clock(state.elapsed)}</span></span>
            : state.status === "done"
              ? <span className="chip chip-ok"><Disc tone="good" icon="check" />Finished</span>
              : <span className="chip chip-bad"><Disc tone="critical" icon="alert" />Stopped</span>}
          <button type="button" className="btn" onClick={() => go("new")}><Icon name="refresh" size={14} />Run again</button>
        </div>
      </header>

      {failure && (
        <div className="banner banner-critical" role="alert">
          <Disc tone="critical" icon="alert" />
          <div><b>This run stopped before it finished.</b> {failure.msg.replace(/^Run stopped:\s*/, "")} Nothing further was marked or sent.</div>
        </div>
      )}

      <nav className="tabs" aria-label="This run">
        {shown.map(([key, label]) => (
          <button key={key} type="button" className={tab === key ? "on" : ""} aria-current={tab === key ? "page" : undefined} onClick={() => onTab(key)}>
            {label}
            {counts[key] > 0 && <span className="tab-count">{counts[key]}</span>}
          </button>
        ))}
      </nav>

      {tab === "progress" && (
        <>
          {state.review?.waiting && <MaterialsPanel state={state} assessment={state.assessment} classId={null} scripts={null} onChanged={refresh} />}
          <div className="cols wide-narrow">
            <div className="stack">
              <section className="card">
                <div className="card-body">
                  <div className="progress-head">
                    <h3 className="h-big">{head.title}</h3>
                    {running && <span className="h-note">{head.detail}</span>}
                  </div>
                  <span className="meter meter-lg" aria-hidden="true"><i style={{ width: `${Math.round(head.fraction * 100)}%` }} /></span>
                  <p className="h-note">
                    {running
                      ? "Marks only count once two markers agree. Disagreements are sent back, or held for you."
                      : head.detail}
                  </p>
                </div>
                <ol className="steps steps-run">
                  {rows.map((row) => (
                    <li key={row.id} className={`step is-${row.state}`}>
                      <span className="step-mark">{row.state === "done" ? <Icon name="check" size={12} /> : <span className="num">{rows.indexOf(row) + 1}</span>}</span>
                      <div>
                        <b>{row.name}</b>
                        <p className="h-note">{row.detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
                <div className="card-body card-foot-area">
                  <p className="h-note">Plan, do, check, correct, deliver: the loop every run follows.</p>
                  <LoopStatus state={state} />
                </div>
              </section>
              <PlanCard plan={state.plan} status={state.status} />
            </div>
            <TeamBoard agents={state.agents} spans={state.spans} now={state.t} status={state.status} />
          </div>
        </>
      )}

      {tab === "submissions" && (
        <SubmissionsTable subs={state.subs} rubric={state.rubric} behind={behind} selectedId={openId} onOpen={onOpen} />
      )}

      {tab === "checks" && (
        <CorrectionsPanel corrections={state.corrections} status={state.status} subs={state.subs} onOpen={onOpen} />
      )}

      {tab === "scripts" && state.scripts && (
        <IngestReview scripts={state.scripts} subs={state.subs} status={state.status} files={state.files} onOpen={onOpen} onChanged={refresh} />
      )}

      {tab === "results" && (
        <>
          {downloads.length > 0 && (
            <section className="card">
              <header className="card-head">
                <h3>Files</h3>
                {state.where && <p className="h-note">Saved in <span className="mono">{state.where}</span></p>}
              </header>
              <div className="card-body downloads">
                {downloads.map((d) => (
                  <a key={d.name} className="btn small" href={fileUrl(d.name)} download>
                    <Icon name="download" size={14} />{d.label}
                  </a>
                ))}
              </div>
            </section>
          )}
          {!hasMarks && <p className="empty-note">Nothing is marked yet. The results fill in as each batch is checked.</p>}
          {hasMarks && (
            <div className="cols wide-narrow">
              <AgreementChart subs={state.subs} rubric={state.rubric} selectedId={openId} onOpen={onOpen} />
              <div className="stack">
                <LevelsChart subs={state.subs} rubric={state.rubric} />
                <CriteriaMeters subs={state.subs} rubric={state.rubric} />
              </div>
            </div>
          )}
          {wantsSupport && (
            <SupportCard support={state.support} outcomes={state.outcomes} status={state.status} files={state.files} onOpen={onOpen} noun={state.rubric?.work} />
          )}
          {wantsLesson && (
            <LessonCard lesson={state.lesson} outcomes={state.outcomes} status={state.status} files={state.files} practical={state.rubric?.kind === "practical"} />
          )}
          {wantsSupport && wantsLesson && <ConsistencyCard consistency={state.consistency} status={state.status} />}
          {state.report && <ClassReport report={state.report} noun={state.rubric?.work} onOpen={onOpen} />}
        </>
      )}

      {tab === "log" && <LiveLog events={events} onOpen={onOpen} />}
    </>
  );
}
