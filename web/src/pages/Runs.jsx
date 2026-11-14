import Icon from "../components/Icon.jsx";
import { Disc } from "../components/Badge.jsx";
import { clock, plural } from "../format.js";

const STATUS = {
  running: { label: "Running", tone: "accent", icon: "dot" },
  done: { label: "Done", tone: "good", icon: "check" },
  failed: { label: "Stopped", tone: "critical", icon: "alert" },
};

/**
 * The runs this server knows about. It keeps the one it is working on (or last worked on) in
 * memory, so that is what this page lists; older runs stay on disk in the output folder.
 */
export default function Runs({ state, go }) {
  if (state.status === "idle") {
    return (
      <section className="card">
        <div className="card-body empty-state">
          <h3>No runs yet</h3>
          <p>Every run you start appears here with what it marked and what it held for you.</p>
          <button type="button" className="btn primary" onClick={() => go("new")}><Icon name="plus" size={15} />New run</button>
        </div>
      </section>
    );
  }
  const tone = STATUS[state.status] || STATUS.done;
  const held = state.subs.filter((s) => s.status === "escalated").length;

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Runs</h2>
          <p className="lede">What your colleague has worked on. Open a run to see its progress, its self-checks and its files.</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn primary" onClick={() => go("new")}><Icon name="plus" size={15} />New run</button>
        </div>
      </header>

      <section className="card">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>Goal</th><th>Class</th><th>Took</th><th>Marked</th><th>Held</th><th>Status</th></tr>
            </thead>
            <tbody>
              <tr className="clickable" onClick={() => go("run")}>
                <td>
                  <button type="button" className="linkish"><b>{state.goal}</b></button>
                  <small className="h-note">{plural(state.subs.length, "learner")}{state.scripts ? " · handwritten scripts" : ""}</small>
                </td>
                <td>{state.rubric?.title}</td>
                <td className="num">{clock(state.elapsed)}</td>
                <td className="num">{state.stats.marked}</td>
                <td className="num">{held || "—"}</td>
                <td><span className="chip"><Disc tone={tone.tone} icon={tone.icon} />{tone.label}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="card-foot h-note">
          The server keeps the current run in memory, so only this one is listed. Earlier runs are on disk in the
          output folder, each in its own dated folder.
        </p>
      </section>
    </>
  );
}
