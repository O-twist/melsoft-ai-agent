import Icon from "./Icon.jsx";
import { Pill } from "./Badge.jsx";
import { fileUrl } from "../api.js";
import { plural } from "../format.js";

const PLAN_STATE = {
  working: { tone: "idle", icon: "clock", label: "Writing the plan" },
  ready: { tone: "good", icon: "check", label: "Plan ready" },
  held: { tone: "serious", icon: "alert", label: "Needs you" },
};

/** One learner's catch-up plan: why they are behind, three steps for the week, and what to look for afterwards. */
export function CatchUpPlan({ entry, outcomes }) {
  if (entry.status === "held") {
    return (
      <p className="held-note">
        <b>No plan is offered.</b> The Coach's draft failed its checks twice (it {entry.problems.join("; ")}), so it
        was held back. The warning signs still stand: this learner needs you.
      </p>
    );
  }
  const plan = entry.plan;
  if (!plan) return <p className="empty-note">The Coach is working out why, and planning a week of catch-up…</p>;

  const outcomeText = Object.fromEntries(outcomes.map((o) => [o.id, o.text]));
  return (
    <dl className="facts">
      <div>
        <dt>Why</dt>
        <dd>
          {plan.why}
          {plan.evidence && <blockquote>“{plan.evidence}”</blockquote>}
        </dd>
      </div>
      {plan.strength && (
        <div>
          <dt>Build on</dt>
          <dd>{plan.strength}</dd>
        </div>
      )}
      <div>
        <dt>This week</dt>
        <dd>
          <ol className="steps">
            {plan.steps.map((step, i) => (
              <li key={i}>
                <span className="step-n">{i + 1}</span>
                <div>
                  {step.activity}
                  <small>
                    <span className="otag">{step.outcome}</span>
                    <span className="num">{step.minutes} min</span> · {outcomeText[step.outcome]}
                  </small>
                </div>
              </li>
            ))}
          </ol>
        </dd>
      </div>
      {plan.check && (
        <div>
          <dt>Check in a week</dt>
          <dd>{plan.check}</dd>
        </div>
      )}
    </dl>
  );
}

/** The rules that flag a learner, in words. They are fixed thresholds applied by code, so they can be stated exactly. */
function rulesText(rules) {
  return (
    `A learner is flagged for a mark below ${rules.below_pct}%, a fall of ${rules.drop_points} points or more since ` +
    `the last essay, under ${rules.criterion_below_pct}% on any part of the rubric, or nothing to mark.`
  );
}

/** Who is falling behind, why, and what each of them should do this week. Asked for in the goal. */
export default function SupportCard({ support, outcomes, status, files, onOpen, noun = "essay" }) {
  const learners = support?.learners || [];
  const ready = learners.filter((e) => e.status === "ready").length;

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>Learners who need support</h2>
          <p>
            {support
              ? `${plural(support.checked, "learner")} checked · ${learners.length} flagged · ${plural(ready, "catch-up plan")} ready`
              : "Spotted from the marks by fixed rules, then diagnosed by the Coach."}
          </p>
        </div>
        {files.includes("support_plans.md") && (
          <a className="btn small" href={fileUrl("support_plans.md")} download="support_plans.md">
            <Icon name="download" size={14} />Catch-up plans
          </a>
        )}
      </header>

      {!support ? (
        <p className="empty-note">
          {status === "running"
            ? "The Coach starts once every mark is settled."
            : "The run stopped before the Coach started."}
        </p>
      ) : (
        <>
          {learners.length === 0 ? (
            <p className="empty-note">No learner shows a warning sign in this set of marks.</p>
          ) : (
            <ul className="folds">
              {learners.map((e, i) => {
                const state = PLAN_STATE[e.status] || PLAN_STATE.working;
                return (
                  <li key={e.id}>
                    <details open={i === 0}>
                      <summary>
                        <span className="fold-main">
                          <b><span className="mono">{e.id}</span>{e.learner}</b>
                          <span>{e.signs.map((sign) => sign.text).join(" · ")}</span>
                        </span>
                        <span className="fold-meta">
                          {e.now != null && (
                            <span className="then-now">
                              <b>{e.now}%</b>
                              {e.previous != null && <small>last essay {Math.round(e.previous)}%</small>}
                            </span>
                          )}
                          <Pill tone={state.tone} icon={state.icon}>{state.label}</Pill>
                        </span>
                        <Icon name="chevron" size={16} className="chev" />
                      </summary>
                      <div className="fold-body">
                        <CatchUpPlan entry={e} outcomes={outcomes} />
                        <button type="button" className="btn small" onClick={() => onOpen(e.id)}>
                          Open the {noun === "essay" ? "essay" : "attempt log"}<Icon name="arrow" size={14} />
                        </button>
                      </div>
                    </details>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="foot-note">
            {rulesText(support.rules)}
            {support.waiting > 0 && (
              <> {plural(support.waiting, "essay")} still {support.waiting === 1 ? "needs" : "need"} your decision, so {support.waiting === 1 ? "that learner has" : "those learners have"} not been checked yet.</>
            )}
          </p>
        </>
      )}
    </section>
  );
}
