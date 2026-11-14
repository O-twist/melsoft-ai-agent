import { useState } from "react";
import Icon from "../components/Icon.jsx";
import { Pill } from "../components/Badge.jsx";
import ScoreReport from "../components/ScoreReport.jsx";
import { CatchUpPlan } from "../components/SupportCard.jsx";
import { plural } from "../format.js";

const BAND = { High: { tone: "critical", icon: "alert" }, Medium: { tone: "warn", icon: "flag" }, Low: { tone: "good", icon: "check" } };
const initials = (name) => name.split(" ").map((w) => w[0]).slice(0, 2).join("");

/** What to do about a learner next, in the teacher's words rather than the system's. */
function nextStep(row, sub) {
  if (sub?.script_hold) return "Decide on script";
  if (sub?.status === "escalated") return "Settle the marks";
  if (sub?.status === "resubmit") return "Ask to resubmit";
  return "Build catch-up plan";
}

/** The class, sorted by who needs help first, with a plain reason and one next step each. */
export default function Learners({ state, onOpen, onRescue, notice, error, focusId, onFocus }) {
  const [tab, setTab] = useState("needs");
  const [query, setQuery] = useState("");
  const risk = state.risk;
  const all = risk?.learners || [];
  const subs = state.subs || [];
  const plans = state.support?.learners || [];
  const passLine = risk?.config?.pass_line ?? 50;

  const match = (row) => {
    const q = query.trim().toLowerCase();
    return !q || row.learner.toLowerCase().includes(q) || row.id.toLowerCase().includes(q) || (row.reason || "").toLowerCase().includes(q);
  };
  const needs = all.filter((row) => row.band !== "Low").filter(match);
  const rows = (tab === "needs" ? needs : all.filter(match));
  const focus = focusId ? all.find((row) => row.id === focusId) : null;

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Learners</h2>
          <p className="lede">
            {state.rubric?.title} · pass line {passLine}%
            {risk?.config?.weights && <> · combines the marks and the practical outcomes</>}
          </p>
        </div>
      </header>

      {notice && <p className="banner" role="status"><Icon name="check" size={15} />{notice}</p>}
      {error && <p className="form-error" role="alert">{error}</p>}

      <nav className="tabs" aria-label="Learners">
        {[["needs", "Needs help", needs.length], ["all", "All learners", all.length], ["plans", "Catch-up plans", plans.length]].map(([key, label, n]) => (
          <button key={key} type="button" className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}{n > 0 && <span className="tab-count">{n}</span>}
          </button>
        ))}
      </nav>

      {tab === "plans" ? (
        plans.length === 0 ? (
          <p className="empty-note">No catch-up plans yet. Ask for them in a run: “tell me who is falling behind, with a catch-up plan for each”.</p>
        ) : (
          <div className="stack">
            {plans.map((entry) => {
              const sub = subs.find((s) => s.id === entry.id);
              return (
                <section key={entry.id} className="card">
                  <header className="card-head">
                    <h3>{sub?.learner || entry.id}</h3>
                    <button type="button" className="btn small" onClick={() => onOpen(entry.id)}>Open learner</button>
                  </header>
                  <div className="card-body"><CatchUpPlan entry={entry} outcomes={state.outcomes} /></div>
                </section>
              );
            })}
          </div>
        )
      ) : (
        <section className="card">
          <div className="card-tools">
            <label className="search">
              <Icon name="search" size={15} />
              <input value={query} placeholder="Search learners or reasons" onChange={(e) => setQuery(e.target.value)} />
              <span className="sr-only">Search learners or reasons</span>
            </label>
          </div>
          {!risk && <p className="empty-note">Scoring the class…</p>}
          {risk && !risk.ok && <p className="empty-note">Risk scores are not available. {risk.error}</p>}
          {rows.length === 0 && risk?.ok && <p className="empty-note">{query ? "Nobody matches that search." : "Every learner is on track."}</p>}
          {rows.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Learner</th><th>Needs help</th><th>Why, in plain words</th><th><span className="sr-only">Next step</span></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const band = BAND[row.band] || BAND.Low;
                    const sub = subs.find((s) => s.id === row.id);
                    return (
                      <tr key={row.id}>
                        <td>
                          <button type="button" className="who" onClick={() => onOpen(row.id)}>
                            <span className="avatar">{initials(row.learner)}</span>
                            <span>
                              <b>{row.learner}</b>
                              <small className="mono">{row.id}</small>
                            </span>
                          </button>
                        </td>
                        <td><Pill tone={band.tone} icon={band.icon}>{row.band}</Pill></td>
                        <td className="why">
                          {row.reason}
                          <small className="h-note">Score {row.risk} of 100</small>
                        </td>
                        <td className="row-actions">
                          <button type="button" className="btn small" onClick={() => onRescue(row)}>{nextStep(row, sub)}</button>
                          <button type="button" className="btn small ghost" onClick={() => onFocus(row.id)}>Score report</button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="card-foot h-note">
            How “Needs help” is worked out: below the pass line in any area, or no work on record.
            {all.length > rows.length && <> {plural(all.length - rows.length, "other learner")} {all.length - rows.length === 1 ? "is" : "are"} on track.</>}
          </p>
        </section>
      )}

      {focus && (
        <>
          <div className="scrim no-print" onClick={() => onFocus(null)} />
          <aside className="drawer drawer-wide" role="dialog" aria-modal="true" aria-label={`Score report for ${focus.learner}`}>
            <header className="drawer-head">
              <div>
                <h3>{focus.learner}</h3>
                <p className="h-note mono">{focus.id}</p>
              </div>
              <button type="button" className="icon-btn no-print" onClick={() => onFocus(null)} aria-label="Close"><Icon name="x" size={18} /></button>
            </header>
            <div className="drawer-body">
              <ScoreReport risk={state.risk} focusId={focus.id} />
            </div>
          </aside>
        </>
      )}
    </>
  );
}
