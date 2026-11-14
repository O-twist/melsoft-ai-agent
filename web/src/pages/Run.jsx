import { useState } from "react";
import { correctionsUrl, fileUrl } from "../api.js";
import { clock } from "../format.js";
import { runProgress, runTitle } from "../plain.js";
import { href } from "../router.js";
import AgreementChart from "../components/AgreementChart.jsx";
import ClassReport from "../components/ClassReport.jsx";
import ConsistencyCard from "../components/ConsistencyCard.jsx";
import CorrectionsPanel from "../components/CorrectionsPanel.jsx";
import CriteriaMeters from "../components/CriteriaMeters.jsx";
import IngestReview from "../components/IngestReview.jsx";
import LessonCard from "../components/LessonCard.jsx";
import LevelsChart from "../components/LevelsChart.jsx";
import LiveLog from "../components/LiveLog.jsx";
import MaterialsPanel from "../components/MaterialsPanel.jsx";
import LoopStatus from "../components/LoopStatus.jsx";
import PlanCard from "../components/PlanCard.jsx";
import SubmissionsTable from "../components/SubmissionsTable.jsx";
import SupportCard from "../components/SupportCard.jsx";
import TeamBoard from "../components/TeamBoard.jsx";
import { AGENT_ROLES, Av, Empty, Head, Ico, Kpi, Tabs } from "./ui.jsx";

const DOWNLOADS = [
  ["marks.csv", "Mark sheet (CSV)"], ["class_report.md", "Class report"], ["scripts/all_pages.pdf", "Photo PDF"],
  ["scripts/clerk_report.md", "Clerk's report"], ["support_plans.md", "Catch-up plans"], ["lesson_plan.md", "Lesson plan"],
];

function agentLine(key, state) {
  const status = state.agents?.[key];
  const live = [...(state.spans || [])].reverse().find((s) => s.agent === key && s.end == null);
  const last = [...(state.spans || [])].reverse().find((s) => s.agent === key);
  if (status === "off") return { chip: "Not needed", tone: "gr", text: key === "CL" ? "No photos in this run" : "Not asked for in this run" };
  if (status === "working") return { chip: "Working", tone: "bl", text: live?.what || "At work" };
  if (status === "done") return { chip: "Done", tone: "ok", text: last?.what || "Finished" };
  return { chip: "Waiting", tone: "gr", text: last ? `Last: ${last.what}` : key === "MS" ? "Starts when marks are settled" : "Waiting for its turn" };
}

export default function Run({ state, events, tab, onTab, onOpen, onChanged, onRunAgain }) {
  const [busy, setBusy] = useState(false);
  if (!state?.id) {
    return (
      <div className="l-page narrow">
        <Head title="Run" />
        <Empty title="No run yet" action={<a className="l-btn p" href={href("new")}>Start a run</a>}>When you start a run, you can watch every colleague at work here.</Empty>
      </div>
    );
  }
  const p = runProgress(state);
  const corr = state.corrections || { stories: [], counts: {}, planted: 0 };
  const files = DOWNLOADS.filter(([name]) => (state.files || []).includes(name));
  const fixed = corr.counts?.fixed || 0;
  const held = (corr.counts?.held || 0) + (corr.counts?.dropped || 0);
  const running = state.status === "running";
  const failed = state.status === "failed";
  const failure = failed ? [...events].reverse().find((e) => e.kind === "ERROR") : null;
  const team = Object.keys(AGENT_ROLES).filter((k) => k in (state.agents || {}) || k !== "CL");
  const wantsSupport = Boolean(state.plan?.deliver?.support);
  const wantsLesson = Boolean(state.plan?.deliver?.lesson);
  const hasMarks = (state.subs || []).some((s) => s.marker);

  async function again() {
    setBusy(true);
    try {
      await onRunAgain();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="l-page">
      <Head title={runTitle(state.goal)} sub={`${running ? `Running for ${clock(state.elapsed)}` : failed ? `Stopped after ${clock(state.elapsed)}` : `Finished · took ${clock(state.elapsed)}`} · Grade 12 CAT · ${(state.subs || []).length} learners${state.scripts ? " · handwritten scripts included" : ""}`}>
        {state.inject_fault && <span className="l-chip md" title="A fault was planted on purpose for this run">Test mode</span>}
        <span className={`l-chip ${running ? "bl" : failed ? "hi" : "ok"}`} style={{ padding: "5px 10px" }}>{running ? `Running · ${clock(state.elapsed)}` : failed ? "Stopped" : "Finished"}</span>
        {!running && <a className="l-btn" href={correctionsUrl()} download="corrections.md"><Ico name="download" size={14} />Self-check report</a>}
      </Head>
      {failed && (
        <div className="l-callout bad" style={{ marginBottom: 14, display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ flex: 1 }}><b>This run stopped.</b> {failure ? failure.msg.replace(/^Run stopped:\s*/, "") : "It did not finish."} Nothing uncertain was sent.</span>
          <button type="button" className="l-btn sm p" disabled={busy} onClick={again}>Run again</button>
        </div>
      )}
      {state.review?.waiting && (
        <div className="l-embed" style={{ marginBottom: 16 }}>
          <MaterialsPanel state={state} assessment={state.assessment} classId={null} scripts={null} onChanged={onChanged} />
        </div>
      )}
      <Tabs label="Run sections" value={tab} onChange={onTab} tabs={[
        ["progress", "Progress"], ["team", "Team"], ["checks", "Checks", corr.stories.length || null],
        ["results", "Results"], ["log", "Activity log", (state.subs || []).length],
      ]} />

      {tab === "progress" && (
        <div className="l-row">
          <section className="l-card" style={{ flex: 1.35 }}>
            <div className="bd">
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <div style={{ fontSize: 22, fontWeight: 650 }} aria-live="polite">{p.headline}</div>
                {p.eta != null && <span className="l-muted">about {p.eta} seconds left</span>}
              </div>
              <div className="l-bar big" style={{ margin: "12px 0 6px" }} role="progressbar" aria-valuenow={Math.round(p.fraction * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${Math.round(p.fraction * 100)}%` }} className={failed ? "hi" : state.status === "done" ? "ok" : ""} /></div>
              <div className="l-small l-muted">{running ? "You can leave this page; the run keeps going. " : ""}Marks only count once two markers agree. Disagreements go back once, or are held for you.</div>
            </div>
            <div className="l-steps" style={{ borderTop: "1px solid var(--line2)", paddingTop: 6 }}>
              {p.steps.map((s, i) => (
                <div className={`l-step ${s.state}`} key={s.id}>
                  <span className="b">{s.state === "done" ? <Ico name="check" size={12} /> : i + 1}</span>
                  <div><b>{s.label}</b><div className="n">{s.note}</div></div>
                </div>
              ))}
            </div>
          </section>
          <section className="l-card" style={{ flex: 1 }}>
            <div className="hd"><h2>Who is working</h2><span className="r l-small l-muted">7 colleagues</span></div>
            <div className="l-list">
              {team.map((k) => {
                const [name, role] = AGENT_ROLES[k];
                const line = agentLine(k, state);
                return (
                  <div className="it" key={k}>
                    <Av name={name} />
                    <div className="grow"><div className="t">{name} <span className="l-muted" style={{ fontWeight: 400 }}>· {role}</span></div><div className="d">{line.text}</div></div>
                    <span className="r"><span className={`l-chip ${line.tone}`}>{line.chip}</span></span>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}

      {tab === "team" && (
        <div className="l-col">
          <section className="l-card"><div className="hd"><h2>The loop</h2><span className="r l-small l-muted">Plan → Do → Check → Correct → Deliver</span></div><div className="bd"><LoopStatus state={state} /></div></section>
          <div className="l-row l-embed">
            <div style={{ flex: 1.5, minWidth: 0 }}><TeamBoard agents={state.agents} spans={state.spans} now={state.t} status={state.status} /></div>
            <div style={{ flex: 1, minWidth: 0 }}><PlanCard plan={state.plan} status={state.status} /></div>
          </div>
          <section className="l-card">
            <div className="hd"><h2>What each colleague does</h2></div>
            <div className="l-list">{Object.entries(AGENT_ROLES).map(([k, [n, , d]]) => <div className="it" key={k}><Av name={n} /><div className="grow"><div className="t">{n}</div><div className="d">{d}</div></div></div>)}</div>
          </section>
        </div>
      )}

      {tab === "checks" && (
        <div className="l-col">
          <div className="l-kpis" style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))", marginBottom: 0 }}>
            <Kpi label="Caught and fixed" value={fixed} />
            <Kpi label="Held for you" value={held + ((state.stats?.escalated || 0) && !held ? state.stats.escalated : 0)} />
            <Kpi label="Planted on purpose (test mode)" value={corr.planted || 0} note={state.inject_fault ? "Each planted fault is labelled below" : "Off for this run"} />
          </div>
          {corr.stories.length ? (
            <div className="l-embed"><CorrectionsPanel corrections={corr} status={state.status} subs={state.subs} onOpen={onOpen} /></div>
          ) : (
            <Empty title={running ? "No check has stopped the work yet" : "Every check passed first time"}>
              Want to see the checks catch a mistake? Turn on <a className="l-link" href={href("settings", { tab: "test" })}>Test mode</a> in Settings: one mark is spoiled on purpose, and the Reviewer has to find it.
            </Empty>
          )}
        </div>
      )}

      {tab === "results" && (
        <div className="l-col">
          <section className="l-card">
            <div className="hd"><h2>Downloads</h2></div>
            <div className="bd" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {files.length ? files.map(([name, label]) => <a key={name} className="l-btn sm" href={fileUrl(name)} download={name.split("/").pop()}><Ico name="download" size={13} />{label}</a>)
                : <span className="l-muted">{running ? "Files appear here as the run writes them." : "This run wrote no files."}</span>}
            </div>
          </section>
          {state.scripts && <div className="l-embed"><IngestReview scripts={state.scripts} subs={state.subs} status={state.status} files={state.files} onOpen={onOpen} onChanged={onChanged} /></div>}
          {hasMarks && (
            <div className="l-row l-embed">
              <div style={{ flex: 1.4, minWidth: 0 }}><AgreementChart subs={state.subs} rubric={state.rubric} onOpen={onOpen} /></div>
              <div style={{ flex: 1, minWidth: 0 }} className="l-col"><LevelsChart subs={state.subs} rubric={state.rubric} /><CriteriaMeters subs={state.subs} rubric={state.rubric} /></div>
            </div>
          )}
          {wantsSupport && <div className="l-embed"><SupportCard support={state.support} outcomes={state.outcomes} status={state.status} files={state.files} onOpen={onOpen} noun={state.rubric?.work} /></div>}
          {wantsLesson && <div className="l-embed"><LessonCard lesson={state.lesson} outcomes={state.outcomes} status={state.status} files={state.files} practical={state.rubric?.kind === "practical"} /></div>}
          {wantsSupport && wantsLesson && <div className="l-embed"><ConsistencyCard consistency={state.consistency} status={state.status} /></div>}
          {state.report && <div className="l-embed"><ClassReport report={state.report} noun={state.rubric?.work} onOpen={onOpen} /></div>}
        </div>
      )}

      {tab === "log" && (
        <div className="l-row l-embed">
          <div style={{ flex: 1, minWidth: 0 }}><LiveLog events={events} onOpen={onOpen} /></div>
          <div style={{ flex: 1, minWidth: 0 }}><SubmissionsTable subs={state.subs} rubric={state.rubric} behind={(state.support?.learners || []).map((e) => e.id)} onOpen={onOpen} /></div>
        </div>
      )}
    </div>
  );
}
