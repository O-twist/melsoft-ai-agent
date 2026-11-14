import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { Disc } from "../components/Badge.jsx";
import ScriptIngest from "../components/ScriptIngest.jsx";
import ClassUpload from "../components/ClassUpload.jsx";
import MaterialsPanel from "../components/MaterialsPanel.jsx";
import { examplesFor, goalFor, willHappen, workName } from "../goals.js";
import { plural } from "../format.js";

const STEPS = ["Class and work", "What to do", "Check and start"];

function Steps({ at, onGo }) {
  return (
    <ol className="wizard">
      {STEPS.map((label, i) => (
        <li key={label}>
          <button type="button" className={`wizard-step ${i === at ? "on" : i < at ? "done" : ""}`} onClick={() => i < at && onGo(i)} disabled={i > at}>
            {i < at ? <Icon name="check" size={13} /> : <span className="num">{i + 1}</span>}
            {label}
          </button>
        </li>
      ))}
    </ol>
  );
}

/**
 * Starting a run, in three plain steps: what is being marked, what the colleague should do, and a
 * last look at the materials before anything is marked. The test switches are not here: they live
 * in Settings, so a teacher cannot plant a fault by accident.
 */
export default function NewRun({
  state, go, goal, onGoal, assessment, onAssessment, scripts, onScripts, injectOcrFault, onInjectOcrFault,
  mine, onMine, reviewFirst, onReviewFirst, onStart, error, running, refresh,
}) {
  const [at, setAt] = useState(0);
  const [confirm, setConfirm] = useState(false);
  const tests = state.features?.tests || [];
  const essays = assessment === "essay";
  const kinds = [
    { key: "essay", label: "English essay", note: "Typed essays on file, or photographed handwritten pages" },
    ...tests.map((t) => ({ key: t.key, label: t.label, note: t.title })),
    ...(state.features?.practical ? [{ key: "practical", label: "PC assembly practical", note: "Marked from each attempt log in the virtual lab" }] : []),
  ];
  const examples = examplesFor(assessment, tests);
  const picked = examples.find((ex) => ex.goal === goal);
  const pages = scripts?.pages?.length || 0;
  const plan = willHappen(goal, { scripts: essays && pages > 0, work: state.rubric?.work || "essay" });

  function pickKind(key) {
    onAssessment(key);
    onGoal(goalFor(key, tests));
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">New run</h2>
          <p className="lede">Tell your colleague what to do. It plans the work, checks itself, and asks you before anything uncertain goes out.</p>
        </div>
      </header>

      <Steps at={at} onGo={setAt} />

      <div className="cols wide-narrow">
        <div className="stack">
          {at === 0 && (
            <>
              <section className="card">
                <div className="card-body">
                  <h3>What are you marking?</h3>
                  <div className="opt-grid">
                    {kinds.map((k) => (
                      <button key={k.key} type="button" className={`opt ${assessment === k.key ? "on" : ""}`} disabled={running} onClick={() => pickKind(k.key)}>
                        <span className="radio" aria-hidden="true" />
                        <span>
                          <b>{k.label}</b>
                          <small>{k.note}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </section>

              {essays && <ClassUpload mine={mine} onMine={onMine} running={running} />}
              {essays && (
                <ScriptIngest
                  scripts={scripts}
                  onScripts={onScripts}
                  injectOcrFault={injectOcrFault}
                  onInjectOcrFault={onInjectOcrFault}
                  running={running}
                />
              )}
              {!essays && (
                <p className="empty-note">
                  Photographed scripts are for essays. {assessment === "practical"
                    ? "The practical is marked from the attempt logs in the Lab."
                    : "This test is marked from the answer scripts on file."}
                </p>
              )}
            </>
          )}

          {at === 1 && (
            <section className="card">
              <div className="card-body">
                <p className="h-note">
                  Marking <b>{workName(assessment, tests)}</b> for <b>{state.rubric?.title}</b> ·{" "}
                  <button type="button" className="linkish" onClick={() => setAt(0)}>change</button>
                </p>
                <h3>What should your colleague do?</h3>
                <div className="opt-grid">
                  {examples.map((ex) => (
                    <button key={ex.id} type="button" className={`opt ${picked?.id === ex.id ? "on" : ""}`} disabled={running} onClick={() => onGoal(ex.goal)}>
                      <span className="radio" aria-hidden="true" />
                      <span>
                        <b>{ex.label}</b>
                        <small>{ex.why}</small>
                      </span>
                    </button>
                  ))}
                </div>
                <label className="brief">
                  <span className="h-note">Your colleague will work from this brief (you can edit it)</span>
                  <textarea rows={3} value={goal} disabled={running} onChange={(e) => onGoal(e.target.value)} />
                </label>
              </div>
            </section>
          )}

          {at === 2 && (
            <>
              <section className="card">
                <div className="card-body">
                  <h3>Check and start</h3>
                  <dl className="facts">
                    <dt>Class</dt><dd>{state.rubric?.title}</dd>
                    <dt>Marking</dt><dd>{workName(assessment, tests)}</dd>
                    <dt>Handwritten pages</dt><dd>{essays && pages ? plural(pages, "page") : "none"}</dd>
                    <dt>The brief</dt><dd>{goal}</dd>
                  </dl>
                  <label className="switch">
                    <input type="checkbox" checked={reviewFirst} disabled={running} onChange={(e) => onReviewFirst(e.target.checked)} />
                    <span className="switch-track" />
                    <span className="switch-text">
                      Check the materials first
                      <small>The run stops after loading, so you can read the memo, the rubric and the scripts before it plans</small>
                    </span>
                  </label>
                </div>
              </section>
              <MaterialsPanel state={state} assessment={assessment} classId={essays ? mine?.class : null} scripts={scripts} onChanged={refresh} />
            </>
          )}

          {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}
        </div>

        <div className="stack">
          <section className="card">
            <header className="card-head"><h3>What will happen</h3></header>
            <ol className="steps">
              {plan.map((row, i) => (
                <li key={row.name} className="step">
                  <span className="step-mark"><span className="num">{i + 1}</span></span>
                  <div>
                    <b>{row.name}</b>
                    <p className="h-note">{row.who} · {row.why}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>
          <p className="callout">
            About a minute for {plural(state.subs?.length || 0, "learner")}. You can leave this page: the run keeps going and Today shows anything that needs you.
          </p>
          <div className="wizard-actions">
            {at > 0 && <button type="button" className="btn" onClick={() => setAt(at - 1)}>Back</button>}
            {at < 2 && <button type="button" className="btn primary" onClick={() => setAt(at + 1)}>Next: {STEPS[at + 1].toLowerCase()} <Icon name="arrow" size={14} /></button>}
            {at === 2 && (
              <button type="button" className="btn primary" disabled={running || !goal.trim()} onClick={() => setConfirm(true)}>
                <Icon name="play" size={14} />{running ? "A run is going" : "Start work"}
              </button>
            )}
          </div>
        </div>
      </div>

      {confirm && (
        <>
          <div className="scrim" onClick={() => setConfirm(false)} />
          <div className="dialog" role="dialog" aria-modal="true" aria-label="Start this run?">
            <h3>Start this run?</h3>
            <p>
              {state.llm?.name === "mock"
                ? "This runs offline, marking with simple text heuristics. It takes a few seconds."
                : `This uses AI marking (${state.llm?.name === "gemini" ? "Gemini" : state.llm?.name}). It takes about a minute for ${plural(state.subs?.length || 0, "learner")}.`}
              {reviewFirst && " It will stop and wait for you to check the materials before it plans."}
            </p>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={() => setConfirm(false)}>Cancel</button>
              <button
                type="button"
                className="btn primary"
                onClick={async () => {
                  setConfirm(false);
                  const ok = await onStart();
                  if (ok) go("run");
                }}
              >
                <Icon name="play" size={14} />Start work
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
