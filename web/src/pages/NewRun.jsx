import { useEffect, useState } from "react";
import ScriptIngest from "../components/ScriptIngest.jsx";
import { DEFAULT_GOAL, PRACTICAL_GOAL } from "../components/GoalBar.jsx";
import { href } from "../router.js";
import { AGENT_ROLES, Confirm, Head, Ico } from "./ui.jsx";

const WHOLE = " Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.";
const BEHIND = " Then tell me who is falling behind, work out why, and prepare a catch-up plan for each of them.";
const LESSON = " Then draft a 45-minute lesson on the class's weakest area, with exercises checked against the learning outcomes.";

export function options(kind) {
  const base = kind === "practical" ? PRACTICAL_GOAL : DEFAULT_GOAL;
  const what = kind === "practical" ? "attempt" : "essay";
  const list = [
    { key: "mark", title: "Mark and send feedback", text: `Marks every ${what}, second-marks it blind, writes to each learner.`, goal: base, team: ["PL", "MK", "RV", "MS"] },
    { key: "marks", title: "Marks only, no messages", text: "Mark sheet and class report. Nothing goes to learners.",
      goal: kind === "practical" ? "Mark the PC assembly practical against the rubric. Do not send feedback to learners: I only want the mark sheet and the class report." : "Mark the Grade 12 CAT theory papers against the rubric. Do not send feedback to learners: I only want the mark sheet and the class report.", team: ["PL", "MK", "RV", "MS"] },
    { key: "behind", title: "Who is falling behind?", text: "Adds a catch-up plan for each learner who needs one.", goal: base + BEHIND, team: ["PL", "MK", "RV", "CO", "MS"] },
    { key: "lesson", title: "Plan the next lesson", text: "Drafts a 45-minute lesson on the weakest area.", goal: base + LESSON, team: ["PL", "MK", "RV", "DS", "MS"] },
    { key: "whole", title: "The whole job", text: "Marks, feedback, catch-up plans and a lesson.", goal: base + WHOLE, team: ["PL", "MK", "RV", "CO", "DS", "MS"] },
    { key: "own", title: "Write my own", text: "Describe the task in your own words.", goal: "", team: null },
  ];
  return list;
}

/** Who the Planner is likely to bring in for a brief, read the same way the offline Planner reads it. */
export function likelyTeam(goal, scripts) {
  const g = goal.toLowerCase();
  const team = ["PL"];
  if (scripts) team.push("CL");
  team.push("MK", "RV");
  if (/falling behind|catch-up|catch up|support/.test(g)) team.push("CO");
  if (/lesson|exercise/.test(g)) team.push("DS");
  team.push("MS");
  return team;
}

const WHAT = {
  PL: (n) => ["Plan the work", "Planner · reads your brief and picks the team"],
  CL: () => ["Read the handwritten pages", "Clerk · checks names and page numbers"],
  MK: (n, kind) => [`Mark each ${kind === "practical" ? "attempt" : "essay"}`, `Marker · against the ${kind === "practical" ? "40" : "50"}-mark rubric`],
  RV: () => ["Second-mark without seeing the first mark", "Reviewer · disagreements go back once, or to you"],
  CO: () => ["Write catch-up plans", "Coach · three steps for each learner who is behind"],
  DS: () => ["Draft the next lesson", "Designer · on the weakest area, never sees names"],
  MS: (n, kind, goal) => [/do not send feedback/i.test(goal) ? "Write the mark sheet and class report" : "Write and send feedback", "Messenger · one message per learner"],
};

export default function NewRun({ state, mine, scripts, onScripts, test, uploads, practicalOn, start, initialScripts, canPause = true }) {
  const [step, setStep] = useState(1);
  const [kind, setKind] = useState("essay");
  const [classId, setClassId] = useState(mine ? "mine" : "sample");
  const [withScripts, setWithScripts] = useState(Boolean(initialScripts || scripts?.pages?.length || test.sample));
  const [choice, setChoice] = useState("mark");
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [confirm, setConfirm] = useState(false);
  const [checkFirst, setCheckFirst] = useState(true); // the run waits for the teacher to check the memo, rubric and scripts before planning
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = state?.status === "running";
  const opts = options(kind);
  const n = (state?.subs || []).length || 12;
  const useScripts = kind === "essay" && withScripts && uploads;
  const team = likelyTeam(goal, useScripts && (scripts?.pages?.length || test.sample));

  const briefFor = (key) => {
    const o = options(kind).find((x) => x.key === key);
    if (!o || o.key === "own") return null;
    return useScripts && o.key !== "marks" ? `Read the photographed handwritten scripts first, then ${o.goal[0].toLowerCase()}${o.goal.slice(1)}` : o.goal;
  };
  useEffect(() => {
    const next = briefFor(choice);
    if (next) setGoal(next);
  }, [kind, useScripts]);

  async function go() {
    setBusy(true);
    setError("");
    try {
      await start({ goal: goal.trim(), assessment: kind, classId: kind === "essay" && classId === "mine" ? mine?.class : null, scripts: useScripts, review: canPause && checkFirst });
    } catch (e) {
      setError(e.message);
      setConfirm(false);
    } finally {
      setBusy(false);
    }
  }

  const stepper = (
    <div className="l-stepper" aria-label="Steps">
      {[["1", "Class and work"], ["2", "What to do"], ["3", "Check and start"]].map(([k, t], i) => (
        <span key={k} style={{ display: "contents" }}>
          {i > 0 && <span className="l-muted">—</span>}
          <button type="button" className={`s l-btn sm ${step > i + 1 ? "done" : step === i + 1 ? "on" : ""}`} style={{ border: 0, background: step > i + 1 ? "var(--ok-bg)" : step === i + 1 ? "var(--blue-bg)" : "#EEF0F4", color: step > i + 1 ? "var(--ok)" : step === i + 1 ? "var(--navy)" : "var(--ink-2)", boxShadow: step === i + 1 ? "0 0 0 1px var(--navy) inset" : "none" }}
            onClick={() => setStep(i + 1)} aria-current={step === i + 1 ? "step" : undefined}>
            {step > i + 1 && <Ico name="check" size={12} />} {k} · {t}
          </button>
        </span>
      ))}
    </div>
  );

  const preview = (
    <div className="l-col" style={{ flex: 1 }}>
      <section className="l-card">
        <div className="hd"><h2>What will happen</h2></div>
        <div className="l-steps">
          {team.map((k, i) => {
            const [t, d] = WHAT[k](n, kind, goal);
            return <div className="l-step" key={k}><span className="b">{i + 1}</span><div><b>{t}</b><div className="n">{d}</div></div></div>;
          })}
        </div>
      </section>
      <div className="l-callout">About 1 minute for {n} learners. You can leave this page: the run keeps going, and Today shows anything that needs you.</div>
    </div>
  );

  return (
    <div className="l-page narrow">
      <Head title="New run" sub="Tell your colleague what to do. It plans the work, checks itself, and asks you before anything uncertain goes out." />
      {stepper}
      {running && <div className="l-callout warn" style={{ marginBottom: 14 }}>A run is going now. <a className="l-link" href={href("run")}>Watch it</a>, or start a new one when it finishes.</div>}

      {step === 1 && (
        <div className="l-row">
          <div className="l-col" style={{ flex: 1.5 }}>
            <section className="l-card">
              <div className="hd"><h2>Class</h2><span className="r"><a className="l-btn sm ghost" href={href("classes")}>Manage classes</a></span></div>
              <div className="bd l-opts">
                <button type="button" className={`l-opt ${classId === "sample" ? "on" : ""}`} onClick={() => setClassId("sample")}><span className="radio" /><span><b>Grade 12 CAT</b><small>Sample class · 12 learners · essays and practical</small></span></button>
                {mine ? (
                  <button type="button" className={`l-opt ${classId === "mine" ? "on" : ""}`} onClick={() => { setClassId("mine"); setKind("essay"); }}><span className="radio" /><span><b>{mine.name || "Your class"}</b><small>Your upload · {mine.learners ?? mine.count ?? ""} learners · essays</small></span></button>
                ) : uploads ? (
                  <a className="l-opt" href={href("classes")} style={{ textDecoration: "none" }}><Ico name="arrow" /><span><b>Upload your own class</b><small>A CSV class list and one .txt essay per learner</small></span></a>
                ) : null}
              </div>
            </section>
            <section className="l-card">
              <div className="hd"><h2>What to mark</h2></div>
              <div className="bd l-opts">
                <button type="button" className={`l-opt ${kind === "essay" ? "on" : ""}`} onClick={() => setKind("essay")}><span className="radio" /><span><b>Theory essays</b><small>Typed essays on file{uploads ? ", and handwritten photos if you add them" : ""}</small></span></button>
                {practicalOn && (
                  <button type="button" className={`l-opt ${kind === "practical" ? "on" : ""}`} disabled={classId === "mine"} onClick={() => setKind("practical")}><span className="radio" /><span><b>PC assembly practical</b><small>Attempts from the Lab, marked against outcomes H1–H6</small></span></button>
                )}
              </div>
            </section>
            {kind === "essay" && uploads && (
              <section className="l-card">
                <div className="bd" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <input id="with-scripts" type="checkbox" checked={withScripts} onChange={(e) => setWithScripts(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2, accentColor: "#041B3A" }} />
                  <label htmlFor="with-scripts" style={{ flex: 1 }}><b>Include handwritten scripts</b> <span className="l-chip gr">optional</span>
                    <div className="l-small l-muted">Photos are read first by the Clerk, matched to the class list, then marked like typed essays.</div></label>
                </div>
                {withScripts && <div className="l-embed" style={{ padding: "0 16px 16px" }}><ScriptIngest scripts={scripts} onScripts={onScripts} running={running} /></div>}
              </section>
            )}
          </div>
          {preview}
        </div>
      )}

      {step === 2 && (
        <div className="l-row">
          <div className="l-col" style={{ flex: 1.5 }}>
            <section className="l-card">
              <div className="bd">
                <div className="l-small l-muted" style={{ marginBottom: 8 }}>Marking: <b style={{ color: "var(--ink)" }}>{kind === "practical" ? "PC assembly practical" : "Theory essays"}</b> for <b style={{ color: "var(--ink)" }}>{classId === "mine" ? mine?.name || "your class" : "Grade 12 CAT (sample class)"}</b> · <button type="button" className="l-link" onClick={() => setStep(1)}>change</button></div>
                <h2 style={{ fontSize: 15, fontWeight: 600, margin: "4px 0 10px" }}>What should your colleague do?</h2>
                <div className="l-opts">
                  {opts.map((o) => (
                    <button type="button" key={o.key} className={`l-opt ${choice === o.key ? "on" : ""}`} onClick={() => { setChoice(o.key); setGoal(o.key === "own" ? "" : briefFor(o.key)); }} aria-pressed={choice === o.key}>
                      <span className="radio" /><span><b>{o.title}</b><small>{o.text}</small></span>
                    </button>
                  ))}
                </div>
                <label className="l-label" htmlFor="brief" style={{ marginTop: 14 }}>Your colleague will work from this brief (you can edit it)</label>
                <textarea id="brief" className="l-field" rows={3} value={goal} onChange={(e) => { setGoal(e.target.value); setChoice("own"); }} placeholder="For example: mark the essays and tell me who is falling behind." />
              </div>
            </section>
          </div>
          {preview}
        </div>
      )}

      {step === 3 && (
        <div className="l-row">
          <div className="l-col" style={{ flex: 1.5 }}>
            <section className="l-card">
              <div className="hd"><h2>Check and start</h2></div>
              <div className="bd l-small" style={{ display: "grid", gridTemplateColumns: "140px 1fr", rowGap: 10 }}>
                <span className="l-muted">Class</span><b>{classId === "mine" ? mine?.name || "Your class" : "Grade 12 CAT (sample class)"}</b>
                <span className="l-muted">Marking</span><b>{kind === "practical" ? "PC assembly practical" : useScripts ? "Theory essays, with handwritten scripts" : "Theory essays"}</b>
                <span className="l-muted">Brief</span><span>{goal || <i className="l-muted">Write a brief in step 2.</i>}</span>
                <span className="l-muted">Colleagues</span><span>{team.map((k) => AGENT_ROLES[k][0]).join(", ")}</span>
                <span className="l-muted">Test mode</span><span>{test.fault || (useScripts && test.ocr) ? <span className="l-chip md">On: a fault will be planted on purpose</span> : "Off"}</span>
              </div>
            </section>
            {canPause && (
              <section className="l-card">
                <div className="bd" style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <input id="check-first" type="checkbox" checked={checkFirst} onChange={(e) => setCheckFirst(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2, accentColor: "#041B3A" }} />
                  <label htmlFor="check-first" style={{ flex: 1 }}><b>Check the memo, rubric and scripts first</b>
                    <div className="l-small l-muted">The run loads the class, then waits for you before the Planner plans anything. You can add a note for the Planner.</div></label>
                </div>
              </section>
            )}
            {useScripts && !(scripts?.pages?.length) && !test.sample && <div className="l-callout warn">No photos are added yet. Go back to step 1 to add them, or switch handwritten scripts off.</div>}
          </div>
          {preview}
        </div>
      )}

      {error && <p className="l-error">{error}</p>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 16 }}>
        {step > 1 && <button type="button" className="l-btn" onClick={() => setStep(step - 1)}>Back</button>}
        {step < 3 ? (
          <button type="button" className="l-btn p lg" onClick={() => setStep(step + 1)} disabled={step === 2 && !goal.trim()}>Next: {step === 1 ? "what to do" : "check and start"} <Ico name="arrow" size={14} /></button>
        ) : (
          <button type="button" className="l-btn p lg" disabled={running || !goal.trim() || (useScripts && !scripts?.pages?.length && !test.sample)} onClick={() => setConfirm(true)}><Ico name="play" size={14} />Start work</button>
        )}
      </div>
      {confirm && (
        <Confirm title="Start this run?" yes="Start work" busy={busy} onYes={go} onNo={() => setConfirm(false)}>
          {state?.llm?.name === "mock" ? "This uses the offline demo marker." : "This uses AI marking."} It takes about 1 minute for {n} learners. Nothing uncertain is sent to a learner without you.
        </Confirm>
      )}
    </div>
  );
}
