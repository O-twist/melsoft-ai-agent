import Icon from "./Icon.jsx";
import { StatusPill } from "./Badge.jsx";
import { FLAGS, pct, plural, wasCorrected, workNoun } from "../format.js";

const NIL = <span className="nil">–</span>;

/** "Too short" says nothing extra when there is no essay at all. */
export const visibleFlags = (s) => s.flags.filter((f) => !(f === "too_short" && s.flags.includes("missing")));

export default function SubmissionsTable({ subs, rubric, behind = [], selectedId, onOpen }) {
  function onKey(e, id) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen(id);
    }
  }

  return (
    <section className="card subs-card">
      <header className="card-head">
        <div>
          <h2>Submissions</h2>
          <p>{plural(subs.length, workNoun(rubric))} · {rubric.title}. Select a row for the full story.</p>
        </div>
      </header>
      <div className="table-wrap">
        <table className="subs">
          <thead>
            <tr>
              <th scope="col" className="id-col">{rubric.kind === "practical" ? "Attempt" : rubric.kind === "test" ? "Script" : "Essay"}</th>
              <th scope="col">Learner</th>
              <th scope="col" className="n opt">Marker</th>
              <th scope="col" className="n opt">Reviewer</th>
              <th scope="col" className="n">Final <span className="th-note">/ {rubric.total}</span></th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr
                key={s.id}
                className={s.id === selectedId ? "on" : ""}
                tabIndex={0}
                onClick={() => onOpen(s.id)}
                onKeyDown={(e) => onKey(e, s.id)}
              >
                <td className="mono id-col">{s.id}</td>
                <td>
                  <span className="mono id-inline" aria-hidden="true">{s.id}</span>
                  <span className="learner">{s.learner}</span>
                  {visibleFlags(s).map((f) => (
                    <span className="flag" key={f}><Icon name="flag" size={11} />{FLAGS[f] || f}</span>
                  ))}
                  {behind.includes(s.id) && <span className="flag"><Icon name="flag" size={11} />Falling behind</span>}
                </td>
                <td className="n opt">
                  {s.marker ? (
                    <>
                      {wasCorrected(s) && <s className="was" title="The mark the Reviewer sent back">{s.rejected.total}</s>}
                      {s.marker.total}
                    </>
                  ) : NIL}
                </td>
                <td className="n opt">{s.reviewer ? s.reviewer.total : NIL}</td>
                <td className="n">
                  {s.final ? (
                    <span className="final">
                      <b>{s.final.total}</b>
                      <span className="meter" aria-hidden="true"><span style={{ width: `${pct(s.final.total, rubric.total)}%` }} /></span>
                    </span>
                  ) : NIL}
                </td>
                <td><StatusPill sub={s} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
