import { Tip, useTip } from "./Tip.jsx";
import { AGENTS, clock, plural } from "../format.js";

/** Round tick positions, in seconds, that keep the axis to about six labels. */
function ticksFor(end) {
  const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find((s) => end / s <= 6) || 1200;
  const ticks = [];
  for (let t = 0; t <= end + 0.001; t += step) ticks.push(t);
  return ticks;
}

const STATE_LABEL = { done: "Done", off: "Not needed", waiting: "Waiting" };

function SpanTip({ agent, span, stop }) {
  return (
    <>
      <div className="tip-title">{span.what}</div>
      <dl className="tip-rows">
        <div>
          <dt><i className="key" />{agent.name}</dt>
          <dd>{(stop - span.start).toFixed(1)}s</dd>
        </div>
      </dl>
      <div className="tip-note">{clock(span.start)} to {span.end == null ? "now" : clock(span.end)}</div>
    </>
  );
}

/**
 * The agents as lanes on one clock. A bar is one stretch of work, so hand-overs between
 * agents, and the Marker going back to re-mark, can be read straight off the picture.
 * An agent the goal did not call on is "off": its lane stays, dimmed, so the whole team is always in view.
 */
export default function TeamBoard({ agents, spans, now, status }) {
  const tip = useTip();
  const running = status === "running";
  const lastEnd = spans.reduce((latest, s) => Math.max(latest, s.end ?? s.start), 0);
  const end = Math.max(running ? now : 0, lastEnd, 5);
  const ticks = ticksFor(end);
  const at = (t) => `${(100 * Math.min(t, end)) / end}%`;
  // Only the agents on this run's team get a lane: the Clerk appears when there were photos to read.
  const team = Object.entries(AGENTS).filter(([key]) => key in agents);

  return (
    <section className="card team">
      <header className="card-head">
        <div>
          <h2>The team at work</h2>
          <p>Each bar is one piece of work by one agent, on the run's clock.</p>
        </div>
      </header>

      <div className="lanes" style={{ "--lanes": team.length }}>
        {team.map(([key, agent]) => {
          const state = agents[key] || "waiting";
          const mine = spans.filter((s) => s.agent === key);
          return (
            <div className={`lane a-${key} ${state === "off" ? "off" : ""}`} key={key}>
              <div className="lane-who">
                <span className="avatar">{key}</span>
                <div className="lane-name">
                  <div>
                    <b>{agent.name}</b>
                    <span className={`lane-state ${state}`}>
                      {state === "working" ? <><span className="live-dot" />Working</> : STATE_LABEL[state] || "Waiting"}
                    </span>
                  </div>
                  <small>{agent.job}</small>
                </div>
              </div>
              <div className="lane-track">
                {ticks.map((t) => <i key={t} className="lane-grid" style={{ left: at(t) }} />)}
                {mine.map((s, i) => {
                  const stop = s.end ?? Math.max(now, s.start);
                  return (
                    <span
                      key={i}
                      className={`span ${s.end == null ? "live" : ""}`}
                      style={{ left: at(s.start), width: `max(4px, calc(${(100 * (stop - s.start)) / end}% - 2px))` }}
                      {...tip.bind(<SpanTip agent={agent} span={s} stop={stop} />)}
                    />
                  );
                })}
              </div>
            </div>
          );
        })}
        <div className="lane lane-axis" aria-hidden="true">
          <div />
          <div className="lane-ticks">
            {ticks.map((t) => <span key={t} style={{ left: at(t) }}>{clock(t)}</span>)}
          </div>
        </div>
      </div>

      {spans.length === 0 && (
        <p className="empty-note">Nothing has run yet. A bar appears here each time an agent picks up work.</p>
      )}

      {/* The same information for screen readers, where a picture of bars says nothing. */}
      <ul className="sr-only">
        {team.map(([key, agent]) => {
          const mine = spans.filter((s) => s.agent === key && s.end != null);
          const seconds = mine.reduce((sum, s) => sum + (s.end - s.start), 0);
          return <li key={key}>{agent.name}: {plural(mine.length, "piece")} of work, {seconds.toFixed(1)} seconds in total.</li>;
        })}
      </ul>
      <Tip tip={tip.tip} />
    </section>
  );
}
