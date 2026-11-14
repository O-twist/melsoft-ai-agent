import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { CatchUpPlan } from "../components/SupportCard.jsx";
import { pct } from "../format.js";

const initials = (name) => name.split(" ").map((w) => w[0]).slice(0, 2).join("");

/** Every message the Messenger wrote, kept here for the teacher to read, copy or send on. */
export default function Messages({ state, onOpen }) {
  const [tab, setTab] = useState("sent");
  const [pickedId, setPicked] = useState(null);
  const subs = state.subs || [];
  const sent = subs.filter((s) => s.feedback && s.status === "delivered");
  const drafts = subs.filter((s) => s.feedback && s.status !== "delivered");
  const waiting = subs.filter((s) => !s.feedback && (s.status === "escalated" || s.script_hold));
  const plans = state.support?.learners || [];
  const list = tab === "sent" ? sent : tab === "drafts" ? [...drafts, ...waiting] : [];
  const picked = list.find((s) => s.id === pickedId) || list[0];

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Messages</h2>
          <p className="lede">
            Feedback your colleague wrote to learners.
            {state.where ? <> Each one is saved in <span className="mono">{state.where}/outbox</span> for you to copy or send.</> : " Email delivery is off unless SMTP is set up."}
          </p>
        </div>
      </header>

      <nav className="tabs" aria-label="Messages">
        {[["sent", "Sent", sent.length], ["drafts", "Waiting", drafts.length + waiting.length], ["plans", "Catch-up plans", plans.length]].map(([key, label, n]) => (
          <button key={key} type="button" className={tab === key ? "on" : ""} onClick={() => { setTab(key); setPicked(null); }}>
            {label}{n > 0 && <span className="tab-count">{n}</span>}
          </button>
        ))}
      </nav>

      {tab === "plans" ? (
        plans.length === 0 ? (
          <p className="empty-note">No catch-up plans yet. Ask for them in a run: “tell me who is falling behind, with a catch-up plan for each”.</p>
        ) : (
          <div className="stack">
            {plans.map((entry) => (
              <section key={entry.id} className="card">
                <header className="card-head">
                  <h3>{subs.find((s) => s.id === entry.id)?.learner || entry.id}</h3>
                  <button type="button" className="btn small" onClick={() => onOpen(entry.id)}>Open learner</button>
                </header>
                <div className="card-body"><CatchUpPlan entry={entry} outcomes={state.outcomes} /></div>
              </section>
            ))}
          </div>
        )
      ) : list.length === 0 ? (
        <p className="empty-note">{tab === "sent" ? "Nothing has been sent yet." : "Nothing is waiting."}</p>
      ) : (
        <div className="cols narrow-wide">
          <section className="card">
            <ul className="rows rows-pick">
              {list.map((s) => (
                <li key={s.id}>
                  <button type="button" className={`row row-btn ${picked?.id === s.id ? "on" : ""}`} onClick={() => setPicked(s.id)}>
                    <span className="avatar">{initials(s.learner)}</span>
                    <span className="row-text">
                      <b>{s.learner}</b>
                      <p>{s.final ? `${s.final.total}/${state.rubric.total} · ` : ""}{s.feedback?.subject || s.issue || "Waiting on your decision"}</p>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {picked && (
            <section className="card">
              <header className="card-head">
                <div>
                  <h3>To {picked.learner}</h3>
                  <p className="h-note">
                    {picked.final && <>{picked.final.total}/{state.rubric.total} ({pct(picked.final.total, state.rubric.total)}%) · </>}
                    written by the Messenger, checked in code before it was saved
                  </p>
                </div>
                {picked.feedback && (
                  <button type="button" className="btn small" onClick={() => navigator.clipboard?.writeText(picked.feedback.body)}>
                    <Icon name="send" size={14} />Copy
                  </button>
                )}
              </header>
              <div className="card-body">
                {picked.feedback ? (
                  <>
                    <p className="h-note"><b>Subject:</b> {picked.feedback.subject}</p>
                    <div className="letter">{picked.feedback.body}</div>
                  </>
                ) : (
                  <>
                    <p>{picked.issue || "This learner is waiting for your decision, so nothing has been written yet."}</p>
                    <div className="card-actions">
                      <button type="button" className="btn small primary" onClick={() => onOpen(picked.id)}>Decide</button>
                    </div>
                  </>
                )}
              </div>
            </section>
          )}
        </div>
      )}
    </>
  );
}
