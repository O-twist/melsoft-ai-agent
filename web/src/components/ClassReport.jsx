import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";

function Column({ title, tone, icon, items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="report-col">
      <h3><Disc tone={tone} icon={icon} />{title}</h3>
      <ul>
        {items.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    </div>
  );
}

/** What the Messenger tells the teacher: how the class did, and what to teach next. */
export default function ClassReport({ report, noun, onOpen }) {
  return (
    <section className="card report">
      <header className="card-head">
        <div>
          <h2>Class report for the teacher</h2>
          <p>Written by the Messenger from the final marks of {report.marked} {noun || "essay"}s.</p>
        </div>
      </header>

      {report.summary && <p className="report-summary">{report.summary}</p>}

      <div className="report-cols">
        <Column title="Strengths" tone="good" icon="check" items={report.strengths} />
        <Column title="Gaps" tone="warn" icon="alert" items={report.gaps} />
        <Column title="Teach next" tone="accent" icon="arrow" items={report.next_lesson} />
      </div>

      {report.consistency && (
        <p className={report.consistency_status === "held" ? "held-note" : "lesson-why"}>{report.consistency}</p>
      )}

      {report.attention.length > 0 && (
        <div className="attention">
          <h3>Needs your attention</h3>
          <ul>
            {report.attention.map((a) => (
              <li key={a.id}>
                <button type="button" className="attention-row" onClick={() => onOpen(a.id)}>
                  <span className="mono">{a.id}</span>
                  <b>{a.learner}</b>
                  <span className="attention-why">{a.why}</span>
                  <Icon name="arrow" size={14} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
