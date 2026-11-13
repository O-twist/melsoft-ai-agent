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
export default function RiskBoard({ state, onReport, onRescue, notice, error }) {
  const risk = state.risk;
  const learners = risk?.learners || [];
  const counts = risk?.counts || {};
  const passLine = risk?.config?.pass_line;

  return (
    <section className="rescue">
      <header className="rescue-head">
        <div>
          <p className="eyebrow">Colleague Zero · Matric Rescue</p>
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

      <LoopStatus state={state} />

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
                      <td className="risk-why">{row.reason}</td>
                      <td className="risk-actions">
                        <button type="button" className="btn small primary" onClick={() => onRescue(row)}>
                          Build rescue plan
                        </button>
                        <button type="button" className="btn small" onClick={() => onReport(row.id)}>
                          Score report
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
