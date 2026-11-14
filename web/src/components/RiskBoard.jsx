import { useState } from "react";
import { Pill } from "./Badge.jsx";
import Icon from "./Icon.jsx";
import LoopStatus from "./LoopStatus.jsx";

const BAND = {
  High: { tone: "critical", icon: "alert" },
  Medium: { tone: "warn", icon: "flag" },
  Low: { tone: "good", icon: "check" },
};

/** The landing view: the class sorted by the Planner's risk score. */
export default function RiskBoard({ state, onReport, onRescue, onWeek2, onWeekReset, onDesk, notice, error }) {
  const risk = state.risk;
  const learners = risk?.learners || [];
  const counts = risk?.counts || {};
  const passLine = risk?.config?.pass_line;
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const shown = learners.filter((row) => !q || `${row.learner} ${row.id} ${row.band} ${row.reason}`.toLowerCase().includes(q));
  const initials = (name) => name.split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();

  return (
    <section className="home-grid">
      <div>
        <p className="wordmark">LABLESS</p>
        <p className="greet">Good morning</p>
        <h1>Grade 12 CAT</h1>
        <article className="hero-navy">
          <p>Learners at risk</p>
          <strong className="num">{counts.High ?? 0}</strong>
          <LoopStatus state={state} compact />
        </article>
        <article className="ice-card">
          <div><b className="num">{risk?.average ?? "–"}%</b><span>Class average</span></div>
          <div><b className="num">{risk?.passed ?? 0}/{learners.length || 0}</b><span>At the pass line</span></div>
          <div><b className="num">{counts.High ?? 0}</b><span>High risk</span></div>
        </article>
        <div className="quick">
          <button type="button" onClick={() => onDesk?.("essay")}><i><Icon name="mail" size={18} /></i>Scripts</button>
          <button type="button" onClick={() => onDesk?.("essay")}><i><Icon name="check" size={18} /></i>Mark</button>
          <button type="button" onClick={() => onDesk?.("practical")}><i><Icon name="chip" size={18} /></i>Virtual lab</button>
          <button type="button" onClick={() => onReport?.()}><i><Icon name="flag" size={18} /></i>Reports</button>
        </div>
        <div className="rescue-actions">
          <button type="button" className="btn primary" onClick={() => onWeek2?.()}>Week 2</button>
        </div>
        {passLine != null && <p className="lede">Pass line {passLine}%. A higher risk score needs a catch-up sooner.</p>}
      </div>

      <div>
        {notice && <p className="rescue-note" role="status">{notice}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {!risk && <p className="empty-note">Scoring the class…</p>}
        {risk && !risk.ok && <p className="empty-note">Risk scores are not available yet. {risk.error}</p>}

        {state.week2?.ok && (
          <div className="card">
            <header className="card-head">
              <div>
                <h2>Week 2, after the rescue</h2>
                <p>{state.week2.summary}</p>
              </div>
              <button type="button" className="btn small" onClick={() => onWeekReset?.()}>Back to week 1 only</button>
            </header>
            <ol className="loop" aria-label="Week 2 agent loop">
              {(state.week2.loop || []).map((phase) => (
                <li key={phase.id} className={`loop-step is-${phase.state}`}>
                  <span className="loop-mark" aria-hidden="true" />
                  <span className="loop-name">{phase.label}</span>
                  <span className="loop-state">{phase.detail}</span>
                </li>
              ))}
            </ol>
            <div className="table-wrap">
              <table className="risk-table">
                <caption className="sr-only">Risk before and after week 2</caption>
                <thead>
                  <tr><th>Learner</th><th>Risk</th><th>Band</th><th>Score</th><th>Result</th></tr>
                </thead>
                <tbody>
                  {state.week2.changes.map((row) => (
                    <tr key={row.id}>
                      <td><b>{row.learner}</b></td>
                      <td className="num">{row.risk_before} → {row.risk_after}</td>
                      <td>{row.band_before} → {row.band_after}</td>
                      <td className="num">{row.overall_before} → {row.overall_after}</td>
                      <td>{row.result_before} → {row.result_after}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {learners.length > 0 && (
          <div className="card list-card">
            <div className="list-hero">
              <h2>Who needs help this week</h2>
              <label className="search">
                <Icon name="search" size={18} />
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search learners, reasons…" aria-label="Search learners" />
              </label>
            </div>
            <ul>
              {shown.map((row) => {
                const band = BAND[row.band] || BAND.Low;
                return (
                  <li key={row.id} className="learner-row">
                    <span className="avatar" aria-hidden="true">{initials(row.learner)}</span>
                    <div>
                      <button type="button" className="linkish" onClick={() => onReport(row.id)}><b>{row.learner}</b></button>
                      {" "}<Pill tone={band.tone} icon={band.icon}>{row.band}</Pill>
                      <p>{row.theory_pass_note || row.reason}</p>
                      <div className="row-actions">
                        <button type="button" className="btn small primary" onClick={() => onRescue(row)}>Build rescue plan</button>
                        <button type="button" className="btn small" onClick={() => onWeek2?.(row.id)}>Their week 2</button>
                      </div>
                    </div>
                    <button type="button" className="arrow-btn" aria-label={`Score report for ${row.learner}`} onClick={() => onReport(row.id)}>
                      <Icon name="arrow" size={16} />
                    </button>
                  </li>
                );
              })}
            </ul>
            {shown.length === 0 && <p className="empty-note">No learner matches that search.</p>}
          </div>
        )}
      </div>
    </section>
  );
}
