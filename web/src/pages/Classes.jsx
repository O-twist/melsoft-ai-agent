import ClassUpload from "../components/ClassUpload.jsx";
import MaterialsPanel from "../components/MaterialsPanel.jsx";
import { Pill } from "../components/Badge.jsx";
import { pct, workNoun } from "../format.js";

const initials = (name) => name.split(" ").map((w) => w[0]).slice(0, 2).join("");

function mark(sub, rubric) {
  if (sub.final) {
    const share = pct(sub.final.total, rubric.total);
    const tone = share >= 50 ? "good" : share >= 40 ? "warn" : "critical";
    return <Pill tone={tone}>{sub.final.total}/{rubric.total}</Pill>;
  }
  if (sub.flags?.includes("missing")) return <Pill tone="critical">Nothing handed in</Pill>;
  if (sub.flags?.includes("too_short")) return <Pill tone="critical">Too short</Pill>;
  return <span className="h-note">Not marked yet</span>;
}

/** The class the whole app works from: who is on it, what each learner handed in, and the marking materials. */
export default function Classes({ state, mine, onMine, running, assessment, refresh }) {
  const subs = state.subs || [];
  const rubric = state.rubric;
  const noun = workNoun(rubric);

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Classes</h2>
          <p className="lede">Your class list, the work on file and the marking materials. Everything else works from the class chosen here.</p>
        </div>
      </header>

      <div className="cols narrow-wide">
        <div className="stack">
          <section className="card card-picked">
            <div className="card-body">
              <b>{rubric?.title}</b>
              <p className="h-note">{subs.length} learners · {rubric?.total} marks · {rubric?.criteria?.length} criteria</p>
            </div>
          </section>
          <ClassUpload mine={mine} onMine={onMine} running={running} />
        </div>

        <section className="card">
          <header className="card-head">
            <h3>{rubric?.title} · learners</h3>
          </header>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr><th>Learner</th><th>ID</th><th>Work on file</th><th>Last mark</th></tr>
              </thead>
              <tbody>
                {subs.map((sub) => (
                  <tr key={sub.id}>
                    <td>
                      <span className="who">
                        <span className="avatar">{initials(sub.learner)}</span>
                        <b>{sub.learner}</b>
                      </span>
                    </td>
                    <td className="mono">{sub.id}</td>
                    <td>
                      {sub.source === "script" ? "Handwritten, transcribed" : sub.source ? `Typed ${noun}` : "Nothing on file"}
                      {sub.words > 0 && <small className="h-note">{sub.words} words</small>}
                    </td>
                    <td>{mark(sub, rubric)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <MaterialsPanel state={state} assessment={assessment} classId={assessment === "essay" ? mine?.class : null} scripts={null} onChanged={refresh} />
    </>
  );
}
