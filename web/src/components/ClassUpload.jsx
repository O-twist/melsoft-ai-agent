import { useRef, useState } from "react";
import { uploadClass } from "../api.js";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import { plural } from "../format.js";

/**
 * The teacher's own class instead of the sample one: a class list (CSV: id, name, and optionally email and
 * previous) and one .txt essay per learner, named by the learner's id. A rubric, a marking memo and learning
 * outcomes are optional; without them the sample ones are used. The server checks everything before keeping it.
 *
 * mine: the summary of the class in use ({ class, learners, essays, missing, unmatched, preview, ... }), or null.
 */
export default function ClassUpload({ mine, onMine, running }) {
  const [files, setFiles] = useState({ classList: null, essays: [], rubric: null, memo: null, outcomes: null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(false);
  const form = useRef(null);

  async function check() {
    setBusy(true);
    setError(null);
    try {
      onMine(await uploadClass(files));
      setOpen(false);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  const pick = (key, many = false) => (e) => setFiles({ ...files, [key]: many ? [...e.target.files] : e.target.files[0] || null });

  return (
    <section className="card">
      <div className="ingest-head">
        <header className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h2>Class <span className="h-note">{mine ? "your own" : "the sample Grade 12 CAT class"}</span></h2>
            <p>
              {mine
                ? `${plural(mine.learners, "learner")}, ${plural(mine.essays, "essay")} matched, marked against ${mine.own_rubric ? "your rubric" : "the sample rubric"}: ${mine.rubric}, ${mine.own_memo ? "with your memo" : mine.memo ? "with the sample memo" : "with no memo"}.`
                : "Marking the sample class. Upload your own class list and essays to mark your class instead."}
            </p>
          </div>
        </header>
        <div className="ingest-actions">
          {mine && (
            <button type="button" className="btn small" disabled={running} onClick={() => onMine(null)}>
              <Icon name="undo" size={14} />Back to the sample class
            </button>
          )}
          <button type="button" className="btn small" disabled={running} onClick={() => setOpen(!open)} aria-expanded={open}>
            <Icon name="user" size={14} />{mine ? "Upload another class" : "Upload your own class"}
          </button>
        </div>
      </div>

      {mine && (mine.missing.length > 0 || mine.unmatched.length > 0) && (
        <p className="note class-note">
          {mine.missing.length > 0 && <>No essay for {mine.missing.join(", ")}: they will be asked to resubmit. </>}
          {mine.unmatched.length > 0 && <>Not used: {mine.unmatched.join("; ")}.</>}
        </p>
      )}

      {open && (
        <form ref={form} className="class-form" onSubmit={(e) => { e.preventDefault(); check(); }}>
          <label>
            <b>Class list</b> <span className="h-note">CSV with columns id, name, and optionally email and previous (the last mark, %)</span>
            <input type="file" accept=".csv,text/csv" onChange={pick("classList")} />
          </label>
          <label>
            <b>Essays</b> <span className="h-note">one .txt file per learner, named by the learner's id, such as E01.txt or E01_Thandi.txt</span>
            <input type="file" accept=".txt,text/plain" multiple onChange={pick("essays", true)} />
          </label>
          <label>
            <b>Rubric</b> <span className="h-note">optional, rubric.json in the same shape as the sample's</span>
            <input type="file" accept=".json,application/json" onChange={pick("rubric")} />
          </label>
          <label>
            <b>Marking memo</b> <span className="h-note">optional, a .md or .txt file the Marker and Reviewer both mark with. Without your own rubric the sample memo is used; with your own rubric and no memo, the rubric alone is used</span>
            <input type="file" accept=".md,.txt,text/plain,text/markdown" onChange={pick("memo")} />
          </label>
          <label>
            <b>Learning outcomes</b> <span className="h-note">optional, outcomes.json</span>
            <input type="file" accept=".json,application/json" onChange={pick("outcomes")} />
          </label>
          <div className="ingest-actions">
            <button type="submit" className="btn small primary" disabled={busy || running || !files.classList}>
              <Icon name="check" size={14} />{busy ? "Checking…" : "Check and use this class"}
            </button>
            <span className="h-note">Handwritten scripts are matched to this class list too.</span>
          </div>
        </form>
      )}
      {error && (
        <div className="form-error class-error" role="alert">
          <Disc tone="critical" icon="alert" />
          <div>
            <b>{error.problems?.length ? "The class was not kept. Put these right and upload again:" : error.message}</b>
            {error.problems?.length > 0 && <ul>{error.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          </div>
        </div>
      )}
    </section>
  );
}
