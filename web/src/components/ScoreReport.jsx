import { useEffect, useState } from "react";

const LABEL_CLASS = { Strong: "strong", Meeting: "meeting", "Needs work": "needs" };

function SkillBar({ area }) {
  const kind = LABEL_CLASS[area.label] || "needs";
  return (
    <div className="skill">
      <div className="skill-top">
        <span>{area.name}</span>
        <b className={`skill-label is-${kind}`}>{area.label}</b>
      </div>
      <div className="skill-track" role="img" aria-label={`${area.name}, ${area.percent} percent, ${area.label}`}>
        <span className={`is-${kind}`} style={{ width: `${Math.max(0, Math.min(100, area.percent))}%` }} />
      </div>
      <p className="skill-meta">
        <span className="num">{area.percent}%</span>
        {area.score != null && area.max != null && <span className="num">{area.score}/{area.max}</span>}
        {area.detail && <small>{area.detail}</small>}
      </p>
    </div>
  );
}

function Sheet({ learner, passLine, onCatchUp }) {
  const passed = learner.result === "Pass";
  return (
    <article className="score-sheet">
      <header className="score-banner">
        <div>
          <p className="score-brand">LabLess</p>
          <p className="score-programme">Grade 12 CAT · score report</p>
        </div>
        <p className={`score-stamp ${passed ? "is-pass" : "is-notyet"}`}>{passed ? "Pass" : "Not yet"}</p>
      </header>

      <div className="score-who">
        <div>
          <h2>{learner.learner}</h2>
          <p>Grade 12 CAT · {learner.id}</p>
        </div>
        <div className="score-overall">
          <p className="score-out-of"><span className="num">{learner.overall}</span><small>/ 100</small></p>
          <p>Pass line {passLine ?? learner.pass_line}</p>
        </div>
      </div>

      <p className="score-riskline">
        <b>Rescue risk {learner.risk}</b> · {learner.band}. {learner.reason}
      </p>
      {learner.theory_pass_note && (
        <p className="score-passnote">{learner.theory_pass_note}</p>
      )}

      <section>
        <h3>Skill areas</h3>
        <div className="skill-list">
          {learner.areas.map((area) => (
            <div key={area.id}>
              <SkillBar area={area} />
              {area.id === "pc" && learner.practical?.outcomes?.length > 0 && (
                <ul className="outcome-row">
                  {learner.practical.outcomes.map((outcome) => (
                    <li key={outcome.id}>
                      <b>{outcome.id}</b>
                      <span className="num">{outcome.percent}%</span>
                      <em>{outcome.label}</em>
                    </li>
                  ))}
                </ul>
              )}
              {area.id === "windows" && learner.windows?.length > 0 && (
                <ul className="outcome-row">
                  {learner.windows.map((outcome) => (
                    <li key={outcome.id}>
                      <b>{outcome.id}</b>
                      <span className="num">{outcome.percent}%</span>
                      <em>{outcome.name}</em>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="score-split">
        <section>
          <h3>What you did well</h3>
          {learner.strengths?.length ? learner.strengths.map((item) => (
            <div key={item.name} className="score-point">
              <p><b>{item.name}</b> · {item.percent}% · {item.label}</p>
              {item.quote && <blockquote>In the learner's words: “{item.quote}”</blockquote>}
            </div>
          )) : <p className="score-empty">Nothing is on record yet to praise. A finished essay or a finished build will show up here.</p>}
        </section>
        <section>
          <h3>Where to improve</h3>
          {learner.gaps?.length ? learner.gaps.map((gap) => (
            <div key={`${gap.outcome}-${gap.name}`} className="score-point">
              <p><b>{gap.name}</b> · {gap.percent}%</p>
              {gap.detail && <p>{gap.detail}</p>}
              {gap.quote && <blockquote>“{gap.quote}”</blockquote>}
              <p className="score-task"><span className="otag">{gap.outcome}</span> {gap.task}</p>
              {gap.link && onCatchUp && (
                <p className="no-print">
                  <button type="button" className="btn small" onClick={() => onCatchUp(learner, gap.link)}>
                    {gap.link.label}
                  </button>
                </p>
              )}
            </div>
          )) : <p className="score-empty">Nothing is below the pass line. Keep this standard in the exam.</p>}
        </section>
      </div>

      {learner.reasons?.length > 0 && (
        <section className="score-reasons">
          <h3>The Planner's reasons</h3>
          <ul>
            {learner.reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </section>
      )}

      <footer className="score-moderation">
        <h3>Moderation note</h3>
        <p>{learner.moderation}</p>
        <p className="score-sign">LabLess. Prepared for the teacher, for use in school.</p>
      </footer>
    </article>
  );
}

function ClassSummary({ risk }) {
  const learners = risk.learners || [];
  return (
    <article className="score-sheet">
      <header className="score-banner">
        <div>
          <p className="score-brand">LabLess</p>
          <p className="score-programme">Grade 12 CAT · class score report</p>
        </div>
        <p className="score-stamp is-class">Teacher</p>
      </header>
      <div className="score-who">
        <div>
          <h2>Class summary</h2>
          <p>Grade 12 CAT · sorted by rescue risk</p>
        </div>
        <div className="score-overall">
          <p className="score-out-of"><span className="num">{risk.average}</span><small> avg</small></p>
          <p>Pass line {risk.config?.pass_line}</p>
        </div>
      </div>
      <p className="score-riskline">{risk.narrative}</p>
      {risk.weakest_area && (
        <p className="score-riskline">Weakest skill area across the class: {risk.weakest_area.name} ({risk.weakest_area.percent}%).</p>
      )}
      <table className="score-class">
        <thead>
          <tr>
            <th>Learner</th>
            <th>Score</th>
            <th>Result</th>
            <th>Risk</th>
            <th>Band</th>
          </tr>
        </thead>
        <tbody>
          {learners.map((row) => (
            <tr key={row.id}>
              <td>{row.learner}</td>
              <td className="num">{row.overall}</td>
              <td>{row.result}</td>
              <td className="num">{row.risk}</td>
              <td>{row.band}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="score-moderation">
        <p className="score-sign">
          {risk.passed} at the pass line, {risk.not_yet} not yet.
          Theory is weighted {Math.round((risk.config?.weights?.theory || 0) * 100)}% and practical work {Math.round((risk.config?.weights?.practical || 0) * 100)}%.
          LabLess.
        </p>
      </footer>
    </article>
  );
}

/** The Messenger's score report: one learner, or the class, and printable from the browser. */
export default function ScoreReport({ risk, week2, focusId, onCatchUp, initialMode = "learner", initialWeek = "before" }) {
  const [which, setWhich] = useState(initialWeek);
  const shown = which === "after" && week2?.after?.ok ? week2.after : risk;
  const learners = shown?.learners || [];
  const [mode, setMode] = useState(initialMode);
  const [id, setId] = useState(focusId || learners[0]?.id || "");

  useEffect(() => {
    if (focusId) {
      setId(focusId);
      setMode("learner");
    }
  }, [focusId]);

  const learner = learners.find((row) => row.id === id) || learners[0];

  if (!shown?.ok || !learners.length) {
    return <p className="empty-note">The score report appears once the Planner has scored the class.</p>;
  }

  return (
    <section className="score-view">
      <div className="score-tools no-print">
        <div className="seg" role="group" aria-label="Which report">
          <button type="button" className={mode === "learner" ? "on" : ""} aria-pressed={mode === "learner"} onClick={() => setMode("learner")}>
            Learner
          </button>
          <button type="button" className={mode === "class" ? "on" : ""} aria-pressed={mode === "class"} onClick={() => setMode("class")}>
            Class summary
          </button>
        </div>
        {week2?.after?.ok && (
          <div className="seg" role="group" aria-label="Before or after the rescue week">
            <button type="button" className={which === "before" ? "on" : ""} aria-pressed={which === "before"} onClick={() => setWhich("before")}>
              Week 1
            </button>
            <button type="button" className={which === "after" ? "on" : ""} aria-pressed={which === "after"} onClick={() => setWhich("after")}>
              Week 2
            </button>
          </div>
        )}
        {mode === "learner" && (
          <label className="score-pick">
            <span className="sr-only">Learner</span>
            <select className="select" value={learner?.id || ""} onChange={(event) => setId(event.target.value)}>
              {learners.map((row) => (
                <option key={row.id} value={row.id}>{row.learner} · {row.band} risk</option>
              ))}
            </select>
          </label>
        )}
        <button type="button" className="btn small primary" onClick={() => window.print()}>
          Print or save as PDF
        </button>
      </div>
      <p className="score-hint no-print">In the print window, choose “Save as PDF” to keep a copy. The marking desk is left off the page.</p>

      {mode === "class" ? <ClassSummary risk={shown} /> : learner && <Sheet learner={learner} passLine={shown.config?.pass_line} onCatchUp={onCatchUp} />}

      {mode === "class" && (
        <div className="print-learners">
          {learners.map((row) => <Sheet key={row.id} learner={row} passLine={shown.config?.pass_line} />)}
        </div>
      )}
    </section>
  );
}
