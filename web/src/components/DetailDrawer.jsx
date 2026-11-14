import { useEffect, useRef, useState } from "react";
import { resolveEssay, resolveScript } from "../api.js";
import Icon from "./Icon.jsx";
import { Disc, StatusPill } from "./Badge.jsx";
import { visibleFlags } from "./SubmissionsTable.jsx";
import { CatchUpPlan } from "./SupportCard.jsx";
import { FLAGS, WHO, capital, levelOf, pct, wasCorrected, workNoun } from "../format.js";

/**
 * Where each quoted piece of evidence sits in the essay, as [start, end) character ranges.
 * Like the server's check, this ignores case, spacing and punctuation between words.
 */
function evidenceRanges(text, quotes) {
  const found = [];
  for (const quote of quotes) {
    for (const part of String(quote || "").split(/\.\.\.|…/)) {
      const words = part
        .split(/\s+/)
        .map((w) => w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ""))
        .filter(Boolean);
      if (words.join(" ").length < 8) continue;
      const pattern = words
        .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/['’‘`]/g, "['’‘`]?"))
        .join("[^\\p{L}\\p{N}]+");
      let match = null;
      try {
        match = new RegExp(pattern, "iu").exec(text);
      } catch {
        // An odd character in a quote must never break the page; that quote just goes unhighlighted.
      }
      if (match) found.push([match.index, match.index + match[0].length]);
    }
  }
  found.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const range of found) {
    const last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([...range]);
  }
  return merged;
}

function Essay({ text, quotes }) {
  const pieces = [];
  let at = 0;
  evidenceRanges(text, quotes).forEach(([start, end], i) => {
    if (start > at) pieces.push(text.slice(at, start));
    pieces.push(<mark key={i}>{text.slice(start, end)}</mark>);
    at = end;
  });
  pieces.push(text.slice(at));
  return <div className="essay">{pieces}</div>;
}

function ScoreBar({ agent, label, score, max }) {
  return (
    <div className={`score a-${agent}`}>
      <span className="score-who">{label}</span>
      <span className="score-track"><span style={{ width: `${pct(score, max)}%` }} /></span>
      <span className="score-fig">{score}</span>
    </div>
  );
}

export default function DetailDrawer({ sub, rubric, support, outcomes, onClose, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const closeButton = useRef(null);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // A different essay: start at the top with keyboard focus inside the panel.
  useEffect(() => {
    setError("");
    closeButton.current?.focus();
  }, [sub.id]);

  async function decide(choice) {
    setBusy(true);
    setError("");
    try {
      // A script the Clerk held is settled by script; a disputed mark by choosing a marker.
      await (sub.script_hold ? resolveScript(sub.script, choice) : resolveEssay(sub.id, choice));
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const shown = sub.final || sub.marker; // the mark whose reasons are worth reading
  const finalPct = sub.final ? pct(sub.final.total, rubric.total) : null;
  const level = finalPct == null ? null : levelOf(finalPct);
  const quotes = shown ? rubric.criteria.map((c) => shown.scores[c.id].evidence) : [];
  const flags = visibleFlags(sub);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`${capital(workNoun(rubric))} ${sub.id}, ${sub.learner}`}>
        <header className="drawer-head">
          <div>
            <div className="drawer-kicker"><span className="mono">{sub.id}</span><StatusPill sub={sub} /></div>
            <h2>{sub.learner}</h2>
            {flags.length > 0 && (
              <div className="drawer-flags">
                {flags.map((f) => <span className="flag" key={f}><Icon name="flag" size={11} />{FLAGS[f] || f}</span>)}
              </div>
            )}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close" ref={closeButton}>
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="drawer-body">
          {sub.status === "escalated" && (
            <section className="decide">
              <h3><Disc tone="serious" icon="alert" />Your decision is needed</h3>
              <p>{sub.issue || "The agents could not settle this essay on their own."}</p>
              <div className="decide-actions">
                {sub.marker && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => decide("marker")}>
                    Use the Marker's mark · {sub.marker.total}
                  </button>
                )}
                {sub.reviewer && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => decide("reviewer")}>
                    Use the Reviewer's mark · {sub.reviewer.total}
                  </button>
                )}
                {sub.script_hold && sub.words > 0 && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => decide("accept")}>
                    Mark the transcript as it stands
                  </button>
                )}
                {sub.script_hold && (
                  <button type="button" className="btn small" disabled={busy} onClick={() => decide("set_aside")}>
                    Set it aside and ask for it again
                  </button>
                )}
              </div>
              {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}
            </section>
          )}

          <section>
            <div className="mark-head">
              {sub.final ? (
                <>
                  <div className="mark-big">{sub.final.total}<span>/ {rubric.total}</span></div>
                  <div className="mark-text">
                    <b>Final mark</b>
                    <span>{finalPct}% · Level {level.n}, {level.name}</span>
                  </div>
                </>
              ) : (
                <div className="mark-text">
                  <b>No final mark yet</b>
                  <span>{sub.marker ? "The marks below are still being checked." : `This ${workNoun(rubric)} has not been marked.`}</span>
                </div>
              )}
            </div>

            {shown && (
              <>
                <ul className="legend" aria-hidden="true">
                  <li className="a-MK"><i className="swatch" />Marker</li>
                  {sub.reviewer && <li className="a-RV"><i className="swatch" />Reviewer, marking blind</li>}
                </ul>
                {wasCorrected(sub) && (
                  <p className="note">
                    The Marker's first total was {sub.rejected.total}. The Reviewer sent it back and it was corrected to {sub.marker.total}.
                  </p>
                )}
                {rubric.criteria.map((c) => {
                  const mine = shown.scores[c.id];
                  return (
                    <div className="crit" key={c.id}>
                      <div className="crit-head"><b>{c.name}</b><span>out of {c.max}</span></div>
                      {sub.marker && <ScoreBar agent="MK" label="Marker" score={sub.marker.scores[c.id].score} max={c.max} />}
                      {sub.reviewer && <ScoreBar agent="RV" label="Reviewer" score={sub.reviewer.scores[c.id].score} max={c.max} />}
                      {mine.reason && <p className="crit-reason">{mine.reason}</p>}
                      {mine.evidence && <blockquote>“{mine.evidence}”</blockquote>}
                    </div>
                  );
                })}
              </>
            )}
          </section>

          <section>
            <h3>What happened</h3>
            {sub.history.length === 0 ? (
              <p className="empty-note">Nothing yet.</p>
            ) : (
              <ol className="trail">
                {sub.history.map((h, i) => {
                  const who = WHO[h.who] || { tone: "idle" };
                  return (
                    <li key={i} className={who.agent ? `a-${who.agent}` : `tone-${who.tone}`}>
                      <i className="trail-dot" />
                      <b>{h.who}</b>
                      <span>{h.what}</span>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>

          {support && (
            <section>
              <h3>
                <Disc tone="warn" icon="flag" />Falling behind
                <span className="h-note">{support.signs.map((sign) => sign.text).join(" · ")}</span>
              </h3>
              <CatchUpPlan entry={support} outcomes={outcomes} />
            </section>
          )}

          {sub.feedback && (
            <section>
              <h3>Message to the learner</h3>
              <div className="letter">
                <div className="letter-head">
                  <Icon name="mail" size={15} />
                  <div>
                    <b>{sub.feedback.subject}</b>
                    <span>To {sub.learner}{sub.email && <> · {sub.email}</>}</span>
                  </div>
                </div>
                <p>{sub.feedback.body}</p>
              </div>
            </section>
          )}

          <section>
            <h3>
              {rubric.kind === "practical" ? "The attempt log" : rubric.kind === "test" ? "The answer script" : "The essay"}{" "}
              <span className="h-note">
                {sub.words} words{sub.source === "script" && ` · transcribed by the Clerk from handwritten script ${sub.script}`}
                {quotes.some(Boolean) && " · quoted evidence highlighted"}
              </span>
            </h3>
            {sub.text ? <Essay text={sub.text} quotes={quotes} /> : <p className="empty-note">Nothing was submitted.</p>}
          </section>
        </div>
      </aside>
    </>
  );
}
