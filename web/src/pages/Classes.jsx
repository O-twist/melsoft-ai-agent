import { useState } from "react";
import ClassUpload from "../components/ClassUpload.jsx";
import { Av, Confirm, Head, Ico } from "./ui.jsx";

/** Class lists, essays and rubrics. */
export default function Classes({ state, mine, onMine, uploads, onLoadSample }) {
  const [show, setShow] = useState(null);
  const subs = state?.subs || [];
  const marks = Object.fromEntries((state?.risk?.learners || []).map((l) => [l.id, l.theory]));
  const rubric = state?.rubric;
  return (
    <div className="l-page">
      <Head title="Classes" sub="Your class lists, essays and rubrics. Everything else in LabLess works from the class chosen here." />
      <div className="l-row">
        <div className="l-col" style={{ width: 320, flex: "none" }}>
          <section className="l-card" style={{ boxShadow: mine ? "none" : "0 0 0 1px var(--navy)" }}>
            <div className="bd"><b>Grade 12 CAT</b> <span className="l-chip bl">Sample class</span><div className="l-small l-muted" style={{ marginTop: 3 }}>12 learners · essays and practical</div>
              {onLoadSample && <button type="button" className="l-btn sm p" style={{ marginTop: 10 }} onClick={onLoadSample}>Load the sample Grade 12 CAT class</button>}</div>
          </section>
          {mine && (
            <section className="l-card" style={{ boxShadow: "0 0 0 1px var(--navy)" }}>
              <div className="bd"><b>{mine.name || "Your class"}</b> <span className="l-chip ok">Your upload</span><div className="l-small l-muted" style={{ marginTop: 3 }}>Essays · used when you choose it in New run</div></div>
            </section>
          )}
          {uploads ? (
            <div className="l-embed"><ClassUpload mine={mine} onMine={onMine} running={state?.status === "running"} /></div>
          ) : (
            <div className="l-callout">Uploading your own class needs LabLess running on a computer (python run.py). This online version uses the sample class.</div>
          )}
          <div className="l-callout"><b>Class list format</b><div className="l-mono" style={{ marginTop: 4 }}>id, name, email, previous</div>
            <div className="l-small" style={{ marginTop: 4 }}>One .txt essay per learner, named by id, for example <span className="l-mono">E01.txt</span>. A rubric and outcomes (JSON) are optional. Files are checked before the class is kept.</div></div>
        </div>
        <section className="l-card" style={{ flex: 1 }}>
          <div className="hd"><h2>Grade 12 CAT · learners</h2>
            <span className="r"><button type="button" className="l-btn sm" onClick={() => setShow("rubric")}>Rubric ({rubric?.total} marks)</button><button type="button" className="l-btn sm" onClick={() => setShow("outcomes")}>Learning outcomes</button></span></div>
          <table className="l-table l-stack">
            <thead><tr><th>Learner</th><th>ID</th><th>Work on file</th><th>Essay mark</th></tr></thead>
            <tbody>{subs.map((s) => {
              const t = marks[s.id];
              const pct = t?.marked ? t.percent : null;
              return (
                <tr key={s.id}><td><div className="l-who"><Av name={s.learner} /><b>{s.learner}</b></div></td><td className="l-mono">{s.id}</td>
                  <td>{s.source === "script" ? "Handwritten script" : s.words ? `Typed essay · ${s.words} words` : "Nothing handed in"}</td>
                  <td>{pct == null ? <span className="l-chip hi">{s.words ? "Too short" : "Missing"}</span> : <span className={`l-chip ${pct >= 70 ? "ok" : pct >= 50 ? "bl" : "md"}`}>{t.score}/{t.max}</span>}</td></tr>
              );
            })}</tbody>
          </table>
        </section>
      </div>
      {show && (
        <Confirm title={show === "rubric" ? rubric?.title || "Rubric" : "Learning outcomes"} yes="Done" no="Close" onYes={() => setShow(null)} onNo={() => setShow(null)}>
          <div style={{ maxHeight: "55vh", overflow: "auto", display: "grid", gap: 10, color: "var(--ink)" }}>
            {show === "rubric" ? (rubric?.criteria || []).map((c) => (
              <div key={c.id}><b>{c.name}</b> <span className="l-muted">(0–{c.max})</span>
                <ul className="l-small" style={{ paddingLeft: 18 }}>{c.bands.map((b) => <li key={b.range.join("-")}>{b.range[0]}–{b.range[1]}: {b.text}</li>)}</ul></div>
            )) : (state?.outcomes || []).map((o) => <div key={o.id} className="l-small"><b>{o.id}</b> {o.text}</div>)}
          </div>
        </Confirm>
      )}
    </div>
  );
}
