import { useState } from "react";
import { fileUrl, pageUrl, resolveScript } from "../api.js";
import Icon from "./Icon.jsx";
import { Disc, Pill } from "./Badge.jsx";
import { plural } from "../format.js";

const SCRIPT_STATE = {
  accepted: { tone: "good", icon: "check", label: "Accepted" },
  held: { tone: "serious", icon: "alert", label: "Held for you" },
  set_aside: { tone: "idle", icon: "x", label: "Set aside" },
};
const SURE = 0.75; // the Clerk's checks want at least this much confidence

function lines(text) {
  return String(text || "").split("\n").filter((l) => l.trim()).length;
}

function sentence(items) {
  const text = items.join("; ");
  return text ? `${text[0].toUpperCase()}${text.slice(1)}.` : "";
}

/** One photographed page: the photo, what the Clerk read on it, and whether it had to be read twice. */
function PageCard({ batch, page }) {
  const r = page.read;
  if (!r) return null;
  const where = r.page ? `page ${r.page}${r.of ? ` of ${r.of}` : ""}` : "no page number";
  const sure = Math.round(100 * r.confidence);
  return (
    <div className="page-card a-CL">
      <a href={pageUrl(batch, page.id)} target="_blank" rel="noreferrer" title="Open the photo">
        <img src={pageUrl(batch, page.id)} alt={`Photo ${page.id}, ${page.original}`} loading="lazy" />
      </a>
      <dl>
        <dt><span className="mono">{page.id}</span> {r.name ? `“${r.name}”` : "no name"}, {where}</dt>
        <dd>{lines(r.text)} of {r.lines} lines transcribed · {r.words} words</dd>
        <dd className={`sure ${r.confidence < SURE ? "low" : ""}`}>
          <i><span style={{ width: `${sure}%` }} /></i>{sure}% sure
        </dd>
        {page.reads > 1 && (
          <dd className="reread">
            <b>Read twice.</b> {sentence(page.first_problems)}
            {page.first && page.first.name !== r.name && <> First read the name as “{page.first.name}”.</>}
          </dd>
        )}
        {page.problems.length > 0 && <dd><Disc tone="serious" icon="alert" /> {sentence(page.problems)}</dd>}
      </dl>
    </div>
  );
}

/** The teacher's decision on a held script. A script with no known learner needs to be given to someone. */
function Decide({ script, subs, onChanged }) {
  const free = subs.filter((s) => s.status === "resubmit" && !s.final && !s.script);
  const suggested = script.suggest.find((c) => free.some((s) => s.id === c.id))?.id;
  const [learner, setLearner] = useState(suggested || free[0]?.id || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function decide(choice) {
    setBusy(true);
    setError("");
    try {
      await resolveScript(script.id, choice, script.learner ? null : learner);
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decide">
      <h3><Disc tone="serious" icon="alert" />Your decision is needed</h3>
      <p>{sentence(script.problems)} Nothing has been marked from this script.</p>
      <div className="decide-actions">
        {!script.learner && script.words > 0 && free.length > 0 && (
          <label>
            <span className="sr-only">Whose script is this?</span>
            <select value={learner} disabled={busy} onChange={(e) => setLearner(e.target.value)}>
              {free.map((s) => <option key={s.id} value={s.id}>{s.id} {s.learner}{s.id === suggested ? " (closest name)" : ""}</option>)}
            </select>
          </label>
        )}
        {script.words > 0 && (script.learner || free.length > 0) && (
          <button type="button" className="btn small" disabled={busy || (!script.learner && !learner)} onClick={() => decide("accept")}>
            <Icon name="check" size={14} />
            {script.learner ? "Mark the transcript as it stands" : "This is their script: mark it"}
          </button>
        )}
        <button type="button" className="btn small" disabled={busy} onClick={() => decide("set_aside")}>
          <Icon name="x" size={14} />{script.learner ? "Set it aside and ask for it again" : "Set it aside"}
        </button>
      </div>
      {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}
    </div>
  );
}

/** What the Clerk made of the photographed scripts: every page, every check, and what waits for the teacher. */
export default function IngestReview({ scripts, subs, status, files, onOpen, onChanged }) {
  const reading = scripts.status !== "done";
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>The Clerk's reading</h2>
          <p>
            {reading
              ? `Transcribing ${plural(scripts.pages.length, "photographed page")} and checking every reading…`
              : scripts.summary}
          </p>
        </div>
        <div className="downloads">
          {files.includes("scripts/clerk_report.md") && (
            <a className="btn small" href={fileUrl("scripts/clerk_report.md")} download="clerk_report.md">
              <Icon name="download" size={14} />Clerk's report
            </a>
          )}
          {files.includes("scripts/all_pages.pdf") && (
            <a className="btn small" href={fileUrl("scripts/all_pages.pdf")} download="all_pages.pdf">
              <Icon name="download" size={14} />All pages (PDF)
            </a>
          )}
        </div>
      </header>

      {reading && (
        <div className="pages">
          {scripts.pages.map((p) => <PageCard key={p.id} batch={scripts.batch} page={p} />)}
        </div>
      )}

      {!reading && (
        <div className="scripts">
          {scripts.scripts.map((sc) => {
            const state = sc.decided === "teacher" && sc.status === "accepted"
              ? { tone: "accent", icon: "user", label: "Accepted by you" }
              : SCRIPT_STATE[sc.status] || SCRIPT_STATE.held;
            const sub = subs.find((s) => s.id === sc.learner);
            return (
              <article className="script" key={sc.id}>
                <div className="script-head">
                  <div>
                    <b><span className="mono">{sc.id}</span>{sc.learner ? `${sc.learner} ${sc.learner_name}` : `Unknown learner, name read as “${sc.name || "nothing"}”`}</b>
                    <div className="h-note">
                      {plural(sc.pages.length, "page")} · {plural(sc.words, "word")}
                      {sc.reread && " · read again after a check failed"}
                      {sc.reordered && " · pages put back in order"}
                    </div>
                  </div>
                  <div className="ingest-actions">
                    <Pill tone={state.tone} icon={state.icon}>{state.label}</Pill>
                    {sub && (
                      <button type="button" className="btn small" onClick={() => onOpen(sub.id)}>Open {sub.id}</button>
                    )}
                    {sc.file && files.includes(sc.file) && (
                      <a className="btn small" href={fileUrl(sc.file)} download={sc.file.split("/").pop()}>
                        <Icon name="download" size={14} />PDF
                      </a>
                    )}
                  </div>
                </div>
                <div className="pages">
                  {sc.pages.map((pid) => (
                    <PageCard key={pid} batch={scripts.batch} page={scripts.pages.find((p) => p.id === pid)} />
                  ))}
                </div>
                {sc.status === "held" && status !== "running" && <Decide script={sc} subs={subs} onChanged={onChanged} />}
                {sc.status === "held" && status === "running" && (
                  <p className="held-note"><b>Held for you.</b> {sentence(sc.problems)} You can decide once the run has finished.</p>
                )}
                {sc.text && (
                  <details>
                    <summary className="h-note">Transcript</summary>
                    <p className="worksheet">{sc.text}</p>
                  </details>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
