import { useEffect, useState } from "react";
import { fetchMaterials, pageUrl, reviewRun } from "../api.js";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import { FLAGS, plural } from "../format.js";

/** The memo is plain text or light Markdown: headings, bullet lists (nested by indent) and paragraphs. */
export function MemoText({ text }) {
  const blocks = [];
  let list = null;
  let para = [];
  const flush = () => {
    if (para.length) blocks.push(<p key={blocks.length}>{para.join(" ")}</p>);
    para = [];
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, "");
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    const item = /^(\s*)[-*]\s+(.*)$/.exec(line);
    if (item) {
      flush();
      if (!list) {
        list = [];
        blocks.push({ list });
      }
      list.push({ depth: Math.min(2, Math.floor(item[1].length / 2)), text: item[2] });
      continue;
    }
    list = null;
    if (heading) {
      flush();
      const Tag = heading[1].length === 1 ? "h3" : "h4";
      blocks.push(<Tag key={blocks.length}>{heading[2]}</Tag>);
    } else if (!line.trim()) {
      flush();
    } else {
      para.push(line.trim());
    }
  }
  flush();
  return (
    <div className="mat-memo">
      {blocks.map((b, i) =>
        b.list ? (
          <ul key={i}>
            {b.list.map((it, j) => <li key={j} style={{ marginLeft: `${it.depth * 18}px` }}>{it.text}</li>)}
          </ul>
        ) : b,
      )}
    </div>
  );
}

export function Rubric({ rubric }) {
  return (
    <div className="mat-rubric">
      <p className="mat-task"><b>Task set:</b> {rubric.task}</p>
      {rubric.criteria.map((c) => (
        <div key={c.id} className="mat-crit">
          <h4>{c.name} <span className="h-note num">out of {c.max}</span></h4>
          <dl>
            {c.bands.map((b) => (
              <div key={b.range.join("-")}>
                <dt className="num">{b.range[0] === b.range[1] ? b.range[0] : `${b.range[0]}–${b.range[1]}`}</dt>
                <dd>{b.text}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
      <p className="note">Total {rubric.total} marks. Code adds the totals and range-checks every mark; a model's sums are never used.</p>
    </div>
  );
}

export function Scripts({ learners, noun }) {
  const [at, setAt] = useState(0);
  const i = Math.min(at, learners.length - 1);
  const one = learners[i];
  if (!one) return <p className="empty-note">No learners on the class list.</p>;
  return (
    <div className="mat-scripts">
      <ul className="mat-list" aria-label="Learners">
        {learners.map((l, n) => (
          <li key={l.id}>
            <button type="button" className={n === i ? "on" : ""} aria-current={n === i ? "true" : undefined} onClick={() => setAt(n)}>
              <span className="learner">{l.learner}</span>
              <span className="h-note num">{l.id} · {l.text ? plural(l.words, "word") : "nothing handed in"}</span>
              {l.flags.filter((f) => f !== "missing").map((f) => (
                <span key={f} className="flag"><Disc tone="serious" icon="flag" />{FLAGS[f] || f}</span>
              ))}
            </button>
          </li>
        ))}
      </ul>
      <div className="mat-read">
        <div className="mat-nav">
          <b>{one.learner}</b> <span className="h-note">{one.id}{one.source === "live" ? " · recorded live in the lab" : ""}</span>
          <span className="mat-step">
            <button type="button" className="btn small" disabled={i === 0} onClick={() => setAt(i - 1)} aria-label="Previous learner">‹</button>
            <span className="num h-note">{i + 1} of {learners.length}</span>
            <button type="button" className="btn small" disabled={i === learners.length - 1} onClick={() => setAt(i + 1)} aria-label="Next learner">›</button>
          </span>
        </div>
        {one.text
          ? <div className="essay">{one.text}</div>
          : <p className="empty-note">No {noun} from {one.learner}. The Planner will ask for a resubmission rather than mark nothing.</p>}
      </div>
    </div>
  );
}

export function Photos({ batch, pages }) {
  return (
    <div className="mat-photos">
      {pages.map((p) => (
        <figure key={p.id}>
          <a href={pageUrl(batch, p.id)} target="_blank" rel="noreferrer">
            <img src={pageUrl(batch, p.id)} alt={`Photographed page ${p.original}`} loading="lazy" />
          </a>
          <figcaption className="h-note">{p.original}</figcaption>
        </figure>
      ))}
    </div>
  );
}

/**
 * What the team will work from: the marking memo, the rubric and every learner's script (and any photographed
 * pages). Before a run it can be browsed. When a run was started with "Check the materials first", the Planner
 * waits here: nothing is planned until the teacher says go, and a note typed here goes to the Planner with the goal.
 */
export default function MaterialsPanel({ state, assessment, classId, scripts, onChanged }) {
  const waiting = Boolean(state.review?.waiting);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState("memo");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const shown = open || waiting;
  const key = waiting ? `run:${state.id}` : `disk:${assessment}:${classId || ""}`;

  useEffect(() => {
    if (!shown) return undefined;
    let live = true;
    setError("");
    fetchMaterials(waiting ? { fromRun: true } : { assessment, classId })
      .then((m) => live && setData({ key, ...m }))
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [key, shown]);

  useEffect(() => {
    if (waiting) {
      setTab("memo");
      setNote("");
    }
  }, [waiting, state.id]);

  async function answer(go) {
    setBusy(true);
    setError("");
    try {
      await reviewRun(go, note);
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const m = data?.key === key ? data : null;
  const photoBatch = m?.pages?.length ? m.batch : scripts?.batch;
  const photos = m?.pages?.length ? m.pages : (!waiting && assessment === "essay" && scripts?.pages) || [];
  const noun = m?.work || (assessment === "practical" ? "practical attempt" : assessment === "essay" ? "essay" : "answer script");
  const tabs = [
    ["memo", "Memo"],
    ["rubric", "Rubric"],
    ["scripts", `${noun === "essay" ? "Scripts" : "Attempt logs"}${m ? ` (${m.learners.length})` : ""}`],
    ...(photos.length ? [["photos", `Photos (${photos.length})`]] : []),
  ];

  return (
    <section className={`card materials ${waiting ? "materials-gate" : ""}`} id="materials">
      <div className="ingest-head">
        <header className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h2>
              Memo, rubric and scripts{" "}
              <span className="h-note">{waiting ? "check them before the Planner plans" : "what the team will work from"}</span>
            </h2>
            <p>
              {waiting
                ? "The Planner has loaded everything and is waiting for you. Nothing has been planned or marked yet."
                : "Read the memo, the rubric and every learner's script before you start. The Marker and the Reviewer both mark with the memo."}
            </p>
          </div>
        </header>
        {!waiting && (
          <div className="ingest-actions">
            <button type="button" className="btn small" onClick={() => setOpen(!open)} aria-expanded={open}>
              <Icon name="chevron" size={14} />{open ? "Hide" : "View memo, rubric and scripts"}
            </button>
          </div>
        )}
      </div>

      {shown && (
        <>
          {waiting && (
            <div className="decide decide-go">
              <h3>Does this look right?</h3>
              <p>Go ahead and the Planner reads your goal and plans the work from these materials. Stop if the memo, rubric or a script is wrong, fix it, and start again.</p>
              <label className="go-note">
                <span className="h-note">Anything the team should know? Optional. It goes to the Planner with your goal.</span>
                <textarea rows={2} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)}
                  placeholder="For example: be strict on language this term." />
              </label>
              <div className="decide-actions">
                <button type="button" className="btn small primary" disabled={busy} onClick={() => answer(true)}>
                  <Icon name="check" size={14} />Looks right, plan the work
                </button>
                <button type="button" className="btn small" disabled={busy} onClick={() => answer(false)}>
                  <Icon name="x" size={14} />Stop, I need to change something
                </button>
              </div>
            </div>
          )}

          <div className="seg materials-tabs" role="tablist" aria-label="Materials">
            {tabs.map(([k, label]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                {label}
              </button>
            ))}
          </div>

          {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}
          {!m && !error && <p className="empty-note">Loading…</p>}
          {m && tab === "memo" && (m.memo
            ? <><p className="note">From <span className="mono">{m.memo.file}</span>. The rubric sets the bands; the memo says how to apply them to this task.</p><MemoText text={m.memo.text} /></>
            : <p className="empty-note">No marking memo for this class, so the markers use the rubric alone. Upload one with your class to add it.</p>)}
          {m && tab === "rubric" && <Rubric rubric={m.rubric} />}
          {m && tab === "scripts" && <Scripts key={key} learners={m.learners} noun={noun} />}
          {tab === "photos" && photos.length > 0 && (
            <>
              <p className="note">{waiting ? "The Clerk transcribes these after you say go." : "The Clerk transcribes these when the run starts."}</p>
              <Photos batch={photoBatch} pages={photos} />
            </>
          )}
        </>
      )}
    </section>
  );
}
