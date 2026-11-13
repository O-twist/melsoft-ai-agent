import { Pill } from "./Badge.jsx";
import { AGENTS } from "../format.js";

const WHERE = {
  lesson: "This lesson",
  exercise: "An exercise",
  outcomes: "The outcomes list",
  none: "Nowhere",
};

function verdict(consistency) {
  const sentBack = consistency.opened.length > 0;
  if (consistency.status === "checking" && sentBack) return { tone: "warn", icon: "undo", label: "Sent back for a revision" };
  if (consistency.status === "checking") return { tone: "idle", icon: "clock", label: "Checking" };
  if (consistency.status === "held") return { tone: "serious", icon: "alert", label: "Held for you" };
  if (consistency.status === "skipped") return { tone: "idle", icon: "clock", label: "Not compared" };
  if (sentBack) return { tone: "accent", icon: "refresh", label: "Corrected after a send-back" };
  return { tone: "good", icon: "check", label: "They agree" };
}

/**
 * The Reviewer's check that the Coach and the Designer agree with each other.
 * Shown only when the goal asked for both, so a judge can see a mismatch caught and, when it can be, corrected.
 */
export default function ConsistencyCard({ consistency, status }) {
  const state = verdict(consistency || { status: "checking", opened: [] });
  const coverage = consistency?.coverage || [];
  const steps = consistency?.steps || [];

  return (
    <section className="card consistency">
      <header className="card-head">
        <div>
          <h2>Do the plans and the lesson agree?</h2>
          <p>Checked in code once the Coach and the Designer have both finished. A mismatch goes back to the colleague who owns it, once.</p>
        </div>
        {consistency && <Pill tone={state.tone} icon={state.icon}>{state.label}</Pill>}
      </header>

      {!consistency ? (
        <p className="empty-note">
          {status === "running"
            ? "The Reviewer starts this check after the catch-up plans and the lesson are both ready."
            : "The run stopped before the two could be compared."}
        </p>
      ) : (
        <>
          {consistency.summary && <p className="lesson-why">{consistency.summary}</p>}

          {consistency.opened.length > 0 && (
            <>
              <h3>Sent back once</h3>
              <ul className="outcomes">
                {consistency.opened.map((item, i) => (
                  <li key={i}>
                    <span className="otag">{AGENTS[item.agent]?.name || item.agent}</span>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {coverage.length > 0 && (
            <>
              <h3>Weaknesses the Coach diagnosed</h3>
              <ul className="outcomes">
                {coverage.map((item) => (
                  <li key={item.id}>
                    <span className="otag">{item.exercise || "—"}</span>
                    <span>
                      {item.name}
                      {item.exercise
                        ? <> is covered by {item.exercise}{item.outcome && <> ({item.outcome})</>}, for {item.learners.join(", ")}.</>
                        : <> is not covered by a support exercise. Diagnosed for {item.learners.join(", ")}.</>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {steps.length > 0 && (
            <>
              <h3>Where each catch-up step maps</h3>
              <table className="map">
                <caption className="sr-only">Where each catch-up step maps</caption>
                <thead>
                  <tr>
                    <th>Learner</th>
                    <th>Step</th>
                    <th>Outcome</th>
                    <th>Maps to</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((step) => (
                    <tr key={`${step.id}-${step.n}`}>
                      <td className="mono">{step.id}</td>
                      <td>{step.n}</td>
                      <td>{step.outcome || "—"}</td>
                      <td>{WHERE[step.where] || step.where}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </section>
  );
}
