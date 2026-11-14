import { useState } from "react";
import PCAssembly from "../components/PCAssembly.jsx";
import ModelViewer from "../components/ModelViewer.jsx";
import { plural } from "../format.js";

/** Practical work learners do in the browser. Attempts feed straight into the next practical run. */
export default function Lab({ state, go }) {
  const [tab, setTab] = useState("pc");
  const attempts = (state.subs || []).filter((s) => s.attempt);
  const available = Boolean(state.features?.practical);

  if (!available) {
    return (
      <section className="card">
        <div className="card-body empty-state">
          <h3>The lab is switched off</h3>
          <p>The PC assembly practical needs <span className="mono">data/practical_rubric.json</span> on disk, and <span className="mono">PRACTICAL_LAB</span> not set to 0.</p>
        </div>
      </section>
    );
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Lab</h2>
          <p className="lede">Practical work learners do in the browser. Attempts feed straight into marking and the Learners page.</p>
        </div>
      </header>

      <nav className="tabs" aria-label="Lab">
        {[["pc", "PC assembly", 0], ["parts", "3D parts", 0], ["attempts", "Attempts", attempts.length]].map(([key, label, n]) => (
          <button key={key} type="button" className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}{n > 0 && <span className="tab-count">{n}</span>}
          </button>
        ))}
      </nav>

      {tab === "pc" && <PCAssembly subs={state.subs} />}

      {tab === "parts" && (
        <section className="card">
          <header className="card-head">
            <h3>The parts, in 3D</h3>
            <p className="h-note">Turn and zoom to see where each part sits</p>
          </header>
          <div className="card-body"><ModelViewer /></div>
        </section>
      )}

      {tab === "attempts" && (
        <section className="card">
          <header className="card-head"><h3>Attempts on record</h3></header>
          {attempts.length === 0 ? (
            <p className="empty-note">No attempts yet. One done here is marked in the next practical run.</p>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>Learner</th><th>Parts placed</th><th>Out of order</th><th>Hints</th><th>Time</th><th>Finished</th></tr>
                </thead>
                <tbody>
                  {attempts.map((s) => (
                    <tr key={s.id}>
                      <td><b>{s.learner}</b> <small className="mono">{s.id}</small></td>
                      <td className="num">{s.attempt.installed} of {s.attempt.parts}</td>
                      <td className="num">{s.attempt.wrong}</td>
                      <td className="num">{s.attempt.hints}</td>
                      <td className="num">{s.attempt.seconds}s</td>
                      <td>{s.attempt.completed ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="card-foot h-note">
            {plural(attempts.length, "attempt")} will be marked by the Marker and checked by the Reviewer, exactly like an essay.{" "}
            <button type="button" className="linkish" onClick={() => go("new")}>Start a practical run</button>
          </p>
        </section>
      )}
    </>
  );
}
