import { useEffect, useMemo, useRef, useState } from "react";
import { Disc } from "./Badge.jsx";
import { AGENTS, KINDS, clock } from "../format.js";

/* A few lines are not really the work of the agent they are filed under. */
const ACTOR = { HUMAN: "Teacher", TEST: "Test", GUARD: "Code check" };
const CORRECTION_KINDS = ["TEST", "REJECT", "FIX", "ESCALATE", "DROP", "HUMAN", "GUARD", "ERROR"];

function Line({ e, onOpen }) {
  const kind = KINDS[e.kind] || {};
  const actor = ACTOR[e.kind];
  return (
    <div className={`ev ${actor ? "" : `a-${e.agent}`} ${kind.wash ? `wash-${kind.tone}` : ""} ${kind.quiet ? "quiet" : ""}`}>
      <span className="ev-time">{clock(e.t)}</span>
      <span className="ev-who"><i />{actor || AGENTS[e.agent]?.name || e.agent}</span>
      <span className="ev-icon">{kind.icon && <Disc tone={kind.tone} icon={kind.icon} />}</span>
      <span className="ev-msg">
        {e.sid && <button type="button" className="idlink" onClick={() => onOpen(e.sid)}>{e.sid}</button>}
        {e.msg}
      </span>
    </div>
  );
}

export default function LiveLog({ events, onOpen }) {
  const [view, setView] = useState("all");
  const box = useRef(null);
  const pinned = useRef(true);

  // "Corrections" tells the whole story of every essay that was challenged, from first mark to outcome.
  const challenged = useMemo(
    () => new Set(events.filter((e) => e.sid && ["TEST", "REJECT", "ESCALATE"].includes(e.kind)).map((e) => e.sid)),
    [events],
  );
  const inStory = (e) => CORRECTION_KINDS.includes(e.kind) || (challenged.has(e.sid) && ["MARK", "APPROVE"].includes(e.kind));
  const shown = view === "all" ? events : events.filter(inStory);
  const sentBack = events.filter((e) => e.kind === "REJECT").length;

  // Follow new lines unless the reader has scrolled up to look at something.
  useEffect(() => {
    if (pinned.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [shown.length, view]);

  function onScroll() {
    const el = box.current;
    pinned.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
  }

  return (
    <section className="card log-card">
      <header className="card-head">
        <div>
          <h2>Live log</h2>
          <p>Every step each agent takes, as it happens.</p>
        </div>
        <div className="seg" role="group" aria-label="Which log lines to show">
          <button type="button" className={view === "all" ? "on" : ""} aria-pressed={view === "all"} onClick={() => setView("all")}>
            Everything
          </button>
          <button type="button" className={view === "fixes" ? "on" : ""} aria-pressed={view === "fixes"} onClick={() => setView("fixes")}>
            Corrections{sentBack > 0 && <span className="seg-count">{sentBack}</span>}
          </button>
        </div>
      </header>
      <div className="log" ref={box} onScroll={onScroll} tabIndex={0} role="log" aria-label="Run log">
        {shown.length === 0 && (
          <p className="empty-note">
            {events.length === 0
              ? "Nothing yet. Give the colleague a goal and press Start work."
              : "Nothing has been challenged in this run so far."}
          </p>
        )}
        {shown.map((e, i) => <Line key={i} e={e} onOpen={onOpen} />)}
      </div>
    </section>
  );
}
