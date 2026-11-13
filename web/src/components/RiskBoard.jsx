import { Pill } from "./Badge.jsx";
import LoopStatus from "./LoopStatus.jsx";

const BAND = {
  High: { tone: "critical", icon: "alert" },
  Medium: { tone: "warn", icon: "flag" },
  Low: { tone: "good", icon: "check" },
};

function Count({ label, value, tone }) {
  return (
    <span className={`risk-count tone-${tone}`}>
      <b className="num">{value}</b>
      {label}
    </span>
  );
}

/** The landing view: the class sorted by the Planner's risk score. */
export default function RiskBoard({ state, onReport, onRescue, onWeek2, onWeekReset, notice, error }) {
  const risk = state.risk;
  const learners = risk?.learners || [];
  const counts = risk?.counts || {};
  const passLine = risk?.config?.pass_line;

  return (
    <section className="rescue">
      <header className="rescue-head">
        <div>
          <p className="eyebrow">LabLess</p>
          <h1>Learners at risk</h1>
          <p className="lede">
            The Planner combines each learner's theory mark and practical outcomes into a risk score from 0 to 100.
            {passLine != null && <> The pass line is {passLine}%.</>} A higher score needs a catch-up sooner.
          </p>
        </div>
        <div className="risk-counts" aria-label="Learners by band">
          <Count label="High" value={counts.High ?? 0} tone="critical" />
          <Count label="Medium" value={counts.Medium ?? 0} tone="warn" />
          <Count label="Low" value={counts.Low ?? 0} tone="good" />
        </div>
      </header>

      <div className="rescue-actions">
        <button type="button" className="btn small primary" onClick={() => onWeek2?.()}>
          Week 2
        </button>
        <p className="lede">Week 2 reruns the loop on the rescue plan and shows the risk score before and after. It is the same result every time in offline demo mode.</p>
      </div>

      <LoopStatus state={state} />

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
                <tr>
                  <th>Learner</th>
                  <th>Risk</th>
                  <th>Band</th>
                  <th>Score</th>
                  <th>Result</th>
                </tr>
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

      {notice && (
        <p className="rescue-note" role="status">{notice}</p>
      )}
      {error && (
        <p className="form-error" role="alert">{error}</p>
      )}

      {!risk && <p className="empty-note">Scoring the class…</p>}
      {risk && !risk.ok && (
        <p className="empty-note">Risk scores are not available yet. {risk.error}</p>
      )}

      {learners.length > 0 && (
        <div className="card risk-card">
          <div className="table-wrap">
            <table className="risk-table">
              <caption className="sr-only">Class sorted by rescue risk, highest first</caption>
              <thead>
                <tr>
                  <th>Learner</th>
                  <th>Risk</th>
                  <th>Band</th>
                  <th>Why</th>
                  <th><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {learners.map((row) => {
                  const band = BAND[row.band] || BAND.Low;
                  return (
                    <tr key={row.id}>
                      <td>
                        <button type="button" className="linkish" onClick={() => onReport(row.id)}>
                          <b>{row.learner}</b>
                        </button>
                        <small className="mono">{row.id}</small>
                      </td>
                      <td>
                        <span className="num risk-num">{row.risk}</span>
                        <span className="risk-meter" aria-hidden="true"><i style={{ width: `${row.risk}%` }} /></span>
                      </td>
                      <td><Pill tone={band.tone} icon={band.icon}>{row.band}</Pill></td>
                      <td className="risk-why">
                        {row.theory_pass_note && <p className="pass-note">{row.theory_pass_note}</p>}
                        {row.reason}
                      </td>
                      <td className="risk-actions">
                        <button type="button" className="btn small primary" onClick={() => onRescue(row)}>
                          Build rescue plan
                        </button>
                        <button type="button" className="btn small" onClick={() => onReport(row.id)}>
                          Score report
                        </button>
                        <button type="button" className="btn small" onClick={() => onWeek2?.(row.id)}>
                          Their week 2
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
