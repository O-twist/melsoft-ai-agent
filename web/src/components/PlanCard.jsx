import { Disc } from "./Badge.jsx";

function Deliverable({ on, yes, no }) {
  return (
    <li>
      <Disc tone={on ? "good" : "idle"} icon={on ? "check" : "x"} />
      {on ? yes : no}
    </li>
  );
}

/** What the Planner decided to do with the goal. A different goal gives a different plan. */
export default function PlanCard({ plan, status }) {
  return (
    <section className="card plan">
      <header className="card-head">
        <div>
          <h2>The plan</h2>
          <p>Written by the Planner from your goal.</p>
        </div>
      </header>

      {!plan ? (
        <p className="empty-note">
          {status === "running"
            ? "The Planner is reading the goal and the submissions…"
            : "Once you start, the Planner decides the batches, what to set aside and what to deliver."}
        </p>
      ) : (
        <>
          <p className="plan-understanding">{plan.understanding}</p>
          <ol className="plan-steps">
            {plan.steps.map((step, i) => (
              <li key={i}><span className="step-n">{i + 1}</span><span>{step}</span></li>
            ))}
          </ol>
          <ul className="plan-facts">
            <li><Disc tone="accent" icon="dot" />Batches of {plan.batch_size}</li>
            <Deliverable on={plan.deliver.feedback} yes="Feedback to learners" no="No feedback messages" />
            <Deliverable on={plan.deliver.csv} yes="Mark sheet" no="No mark sheet" />
            <Deliverable on={plan.deliver.report} yes="Class report" no="No class report" />
            {/* The Coach and the Designer only work when the goal asks, so these are listed only then. */}
            {plan.deliver.support && <Deliverable on yes="Catch-up plans" />}
            {plan.deliver.lesson && <Deliverable on yes={`${plan.lesson_minutes}-minute lesson with exercises`} />}
          </ul>
          {plan.exclude.length > 0 && (
            <p className="plan-aside">
              <b>Set aside:</b>{" "}
              {plan.exclude.map((e) => `${e.id} (${String(e.reason).replace(/\.$/, "")})`).join("; ")}
            </p>
          )}
        </>
      )}
    </section>
  );
}
