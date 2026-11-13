import Icon from "./Icon.jsx";
import { Pill } from "./Badge.jsx";
import { AGENTS, clock, plural } from "../format.js";

const OUTCOME = {
  fixed: { tone: "good", icon: "check", label: "Fixed" },
  held: { tone: "serious", icon: "alert", label: "Held for the teacher" },
  dropped: { tone: "serious", icon: "x", label: "Dropped" },
  teacher: { tone: "accent", icon: "user", label: "Decided by the teacher" },
  prevented: { tone: "warn", icon: "shield", label: "Stopped by code" },
  open: { tone: "idle", icon: "clock", label: "Still open" },
};

/**
 * How we corrected ourselves: every time a check stopped work in this run, as one story from the problem to
 * how it ended. Built by the server from the run's log (app/story.py), so it is what really happened.
 */
export default function CorrectionsPanel({ corrections, status, subs, onOpen }) {
  const stories = corrections?.stories || [];
  if (!stories.length) return null;
  const counts = corrections.counts;
  const tally = Object.entries(counts).map(([k, n]) => `${n} ${OUTCOME[k].label.toLowerCase()}`).join(", ");
  const known = new Set(subs.map((s) => s.id));

  return (
    <section className="card" id="corrections">
      <header className="card-head">
        <div>
          <h2>How we corrected ourselves</h2>
          <p>
            {plural(stories.length, "time")} a check stopped work in this run: {tally}.
            {corrections.planted > 0 && ` ${corrections.planted} began with a fault planted on purpose.`}
            {status === "running" && " Still running, so more may follow."} Built from the run's log.
          </p>
        </div>
        <a className="btn small" href="/api/corrections.md" download="corrections.md">
          <Icon name="download" size={14} />Corrections
        </a>
      </header>
      <ul className="folds">
        {stories.map((s, i) => {
          const outcome = OUTCOME[s.outcome] || OUTCOME.open;
          return (
            <li key={i}>
              <details open={i === 0}>
                <summary>
                  <span className="fold-main">
                    <b><span className="mono">{i + 1}</span>{s.subject}</b>
                    <span>Caught by the {s.caught_by}, by {s.how.join(" and ")}{s.fixed_by && s.outcome === "fixed" ? `. Fixed by the ${s.fixed_by}.` : "."}</span>
                  </span>
                  <span className="fold-meta">
                    {s.planted && <Pill tone="warn" icon="zap">Planted fault</Pill>}
                    <Pill tone={outcome.tone} icon={outcome.icon}>{outcome.label}</Pill>
                  </span>
                  <Icon name="chevron" size={16} className="chev" />
                </summary>
                <div className="fold-body">
                  <ol className="trail">
                    {s.steps.map((st, j) => (
                      <li key={j} className={`a-${st.agent}`}>
                        <i className="trail-dot" />
                        <b>{AGENTS[st.agent]?.name || st.agent} <span className="h-note mono">{clock(st.t)}</span></b>
                        <span>{st.msg}</span>
                      </li>
                    ))}
                  </ol>
                  {s.sid && known.has(s.sid) && (
                    <button type="button" className="btn small" onClick={() => onOpen(s.sid)}>
                      Open {s.sid}<Icon name="arrow" size={14} />
                    </button>
                  )}
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
