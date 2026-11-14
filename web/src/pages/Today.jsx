import Icon from "../components/Icon.jsx";
import { Disc, Pill } from "../components/Badge.jsx";
import { attention } from "../progress.js";
import { clock, pct, plural, workNoun } from "../format.js";

const BAND = { High: { tone: "critical", icon: "alert" }, Medium: { tone: "warn", icon: "flag" }, Low: { tone: "good", icon: "check" } };

function Tile({ label, value, of, note, bar }) {
  return (
    <section className="card tile">
      <p className="tile-label">{label}</p>
      <p className="tile-value">
        <span className="num">{value}</span>
        {of != null && <small> of {of}</small>}
      </p>
      {bar != null && <span className="meter" aria-hidden="true"><i style={{ width: `${bar}%` }} /></span>}
      {note && <p className="tile-note">{note}</p>}
    </section>
  );
}

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
};

/** The first page of the day: what needs the teacher, who needs help, and how the last run went. */
export default function Today({ state, go, onOpen, onAddScripts }) {
  const subs = state.subs || [];
  const rubric = state.rubric;
  const marked = subs.filter((s) => s.final);
  const sent = subs.filter((s) => s.feedback && s.status === "delivered").length;
  const total = subs.length;
  const average = marked.length ? Math.round(marked.reduce((sum, s) => sum + s.final.total, 0) / marked.length) : null;
  const risk = state.risk;
  const passLine = risk?.config?.pass_line ?? 50;
  const passing = marked.filter((s) => pct(s.final.total, rubric.total) >= passLine).length;
  const needs = attention(state);
  const behind = (risk?.learners || []).filter((row) => row.band !== "Low").slice(0, 4);
  const date = new Date().toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long" });
  const noun = workNoun(rubric);

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">{greeting()}</h2>
          <p className="lede">{date} · {state.rubric?.title || "No class loaded"}</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn" onClick={onAddScripts}><Icon name="camera" size={15} />Add scripts</button>
          <button type="button" className="btn primary" onClick={() => go("new")}><Icon name="plus" size={15} />New run</button>
        </div>
      </header>

      <div className="tiles">
        <Tile label={`${noun[0].toUpperCase()}${noun.slice(1)}s marked`} value={marked.length} of={total} bar={total ? (100 * marked.length) / total : 0} />
        <Tile label="Class average" value={average == null ? "—" : `${pct(average, rubric.total)}%`} note={average == null ? "Nothing marked yet" : `${average} of ${rubric.total} marks`} />
        <Tile label={`At or above the ${passLine}% pass line`} value={passing} of={marked.length || total} note={risk?.counts?.High ? `${risk.counts.High} learners need help` : "Nobody is in the high band"} />
        <Tile label="Feedback sent" value={sent} note={needs.length ? `${needs.length} waiting on you` : "Nothing waiting on you"} />
      </div>

      <div className="cols wide-narrow">
        <div className="stack">
          <section className="card">
            <header className="card-head">
              <h3>Needs your attention {needs.length > 0 && <span className="chip chip-count">{needs.length}</span>}</h3>
              <p className="h-note">Nothing is sent or marked until you decide</p>
            </header>
            {needs.length === 0 ? (
              <p className="empty-note">Nothing is waiting for you. Anything the colleague cannot settle on its own appears here.</p>
            ) : (
              <ul className="rows">
                {needs.map((item) => (
                  <li key={`${item.kind}-${item.id}`} className="row">
                    <span className={`row-mark tone-${item.kind === "flagged" ? "warn" : "serious"}`}>
                      <Icon name={item.kind === "script" ? "camera" : "alert"} size={15} />
                    </span>
                    <div className="row-text">
                      <b>{item.title}</b>
                      <p>{item.detail}</p>
                    </div>
                    <div className="row-actions">
                      {item.sid
                        ? <button type="button" className="btn small primary" onClick={() => onOpen(item.sid)}>Decide</button>
                        : <button type="button" className="btn small primary" onClick={() => go("run", { tab: "scripts" })}>Decide</button>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <header className="card-head">
              <h3>Who needs help this week</h3>
              <button type="button" className="btn small ghost" onClick={() => go("learners")}>View all learners <Icon name="arrow" size={14} /></button>
            </header>
            {behind.length === 0 ? (
              <p className="empty-note">{risk ? "Every learner is on track." : "Scoring the class…"}</p>
            ) : (
              <ul className="rows">
                {behind.map((row) => {
                  const band = BAND[row.band] || BAND.Low;
                  return (
                    <li key={row.id} className="row">
                      <span className="avatar">{row.learner.split(" ").map((w) => w[0]).slice(0, 2).join("")}</span>
                      <div className="row-text">
                        <b>{row.learner} <Pill tone={band.tone} icon={band.icon}>{row.band}</Pill></b>
                        <p>{row.reason}</p>
                      </div>
                      <div className="row-actions">
                        <button type="button" className="btn small" onClick={() => go("learners", { id: row.id })}>Open</button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <header className="card-head">
              <h3>Latest run</h3>
              {state.status === "done" && <span className="chip chip-ok"><Disc tone="good" icon="check" />Finished</span>}
              {state.status === "running" && <span className="chip"><span className="live-dot" />Running</span>}
              {state.status === "failed" && <span className="chip chip-bad"><Disc tone="critical" icon="alert" />Stopped</span>}
            </header>
            {state.status === "idle" ? (
              <div className="card-body empty-state">
                <p>No run yet today.</p>
                <button type="button" className="btn primary" onClick={() => go("new")}><Icon name="plus" size={15} />Start your first run</button>
              </div>
            ) : (
              <div className="card-body">
                <b>{state.goal}</b>
                <p className="h-note">Took {clock(state.elapsed)} · {plural(subs.length, "learner")}</p>
                <dl className="facts">
                  <dt>Marked and second-marked</dt><dd className="num">{state.stats.marked}</dd>
                  <dt>Caught and fixed by the checks</dt><dd className="num">{state.stats.fixed}</dd>
                  <dt>Held for you</dt><dd className="num">{state.stats.escalated}</dd>
                  <dt>Messages sent to learners</dt><dd className="num">{state.stats.delivered}</dd>
                </dl>
                <div className="card-actions">
                  <button type="button" className="btn small" onClick={() => go("run")}>Open run</button>
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
