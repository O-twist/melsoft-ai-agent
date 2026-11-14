import { useMemo, useState } from "react";
import Icon from "./Icon.jsx";
import { Disc, Pill } from "./Badge.jsx";
import { AGENTS, KINDS, clock, plural } from "../format.js";

/* What each kind of log line means, in plain words, for the reasoning trail. */
const SAID = {
  INFO: "Noted", PLAN: "Planned", DECIDE: "Decided", ACT: "Started", MARK: "Marked", CHECK: "Checked",
  WAIT: "Asking the model", FLAG: "Flagged", GUARD: "Code check", TEST: "Planted fault", REJECT: "Sent back",
  FIX: "Corrected", APPROVE: "Approved", ESCALATE: "Held for you", DROP: "Dropped", HUMAN: "Teacher",
  SEND: "Delivered", DONE: "Done", ERROR: "Problem",
};
const SAID_BY = { CL: { REJECT: "Failed a check", FIX: "Read again" } };
const STATE = { working: "Working", done: "Done", waiting: "Waiting", off: "Not needed" };
const ORDER = ["PL", "CL", "MK", "RV", "MS", "CO", "DS"];
const ROLE = {
  PL: "plans the run", CL: "reads handwritten scripts", MK: "first marker", RV: "second marker, marking blind",
  MS: "writes feedback", CO: "catch-up plans", DS: "lesson plans",
};

const pctOf = (x) => `${Math.round((x || 0) * 100)}%`;

/** The reasoning trail: every line this agent wrote to the log, oldest first. */
function Trail({ agent, lines, onOpen }) {
  if (!lines.length) return <p className="empty-note">Nothing from this colleague yet.</p>;
  return (
    <ol className="trail">
      {lines.map((e, i) => {
        const kind = KINDS[e.kind] || {};
        return (
          <li key={i} className={`trail-line ${kind.quiet ? "quiet" : ""}`}>
            <span className="trail-time num">{clock(e.t)}</span>
            <span className="trail-kind">{kind.icon ? <Disc tone={kind.tone} icon={kind.icon} /> : <i className="trail-dot" />}{SAID_BY[agent]?.[e.kind] || SAID[e.kind] || e.kind}</span>
            <span className="trail-msg">
              {e.sid && <button type="button" className="idlink" onClick={() => onOpen(e.sid)}>{e.sid}</button>}
              {e.msg}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** The Clerk's feedback on the photographed scripts: what it read, how sure it was, and why it held any. */
function ClerkFeedback({ scripts, subs, events, onOpen }) {
  if (!scripts) return <p className="empty-note">No photographed scripts came with this run, so the Clerk was not needed.</p>;
  const pages = Object.fromEntries((scripts.pages || []).map((p) => [p.id, p]));
  // Test mode: the page whose transcript was cut on purpose, so its re-read is shown as planted, not as a real misreading.
  const planted = new Set((events || []).filter((e) => e.kind === "TEST").flatMap((e) => e.msg.match(/\bp\d+\b/g) || []));
  return (
    <div className="stack">
      {scripts.summary && <p className="callout"><b>The Clerk's summary.</b> {scripts.summary}</p>}
      {(scripts.scripts || []).map((rec) => {
        const sub = subs.find((s) => s.script === rec.id) || subs.find((s) => s.id === rec.learner);
        const held = rec.status === "held";
        return (
          <section key={rec.id} className={`clerk-script ${held ? "is-held" : ""}`}>
            <header>
              <b>Script {rec.id}</b>
              <span className="h-note">
                name read as “{rec.name || "none"}”
                {rec.learner ? <> → matched to <b>{rec.learner_name}</b> ({rec.learner})</> : " → not on the class list"}
              </span>
              <span className="clerk-status">
                {rec.status === "accepted" && <Pill tone="good" icon="check">{rec.decided === "teacher" ? "Accepted by you" : "Accepted"}</Pill>}
                {held && <Pill tone="serious" icon="alert">Held for you</Pill>}
                {rec.status === "set_aside" && <Pill tone="idle" icon="x">Set aside</Pill>}
              </span>
            </header>
            <ul className="clerk-pages">
              {rec.pages.map((pid) => {
                const p = pages[pid];
                const r = p?.read || {};
                return (
                  <li key={pid}>
                    <span className="mono">{pid}</span>
                    <span>page {r.page || "?"}{r.of ? ` of ${r.of}` : ""}</span>
                    <span>{plural(r.lines || 0, "line")}, {plural(r.words || 0, "word")}</span>
                    <span className={`conf ${r.confidence < 0.75 ? "low" : ""}`} title="How sure the Clerk was of its reading">{pctOf(r.confidence)} sure</span>
                    {planted.has(pid) && <Pill tone="warn" icon="zap">Planted fault</Pill>}
                    {p?.reads > 1 && (
                      <span className="clerk-note">
                        Read twice: {(p.first_problems || []).join("; ") || "a check failed"}.
                        {p.first?.name && p.first.name !== r.name && <> First read the name as “{p.first.name}”.</>}
                      </span>
                    )}
                    {r.problem && <span className="clerk-note">The Clerk said: {r.problem}</span>}
                  </li>
                );
              })}
            </ul>
            <p className="clerk-verdict">
              {held
                ? <>Why it was held: {(rec.problems || []).join("; ")}. Nothing has been marked from it.</>
                : <>Every check passed: {plural(rec.words, "word")}, pages in order{rec.reordered ? " (they were photographed out of order and put back)" : ""}.</>}
              {sub && <> <button type="button" className="linkish" onClick={() => onOpen(sub.id)}><b>Open {sub.learner}</b></button></>}
            </p>
          </section>
        );
      })}
    </div>
  );
}

/** What an agent decided and the reasons it gave, from the structured answers it returned. */
function Reasons({ agent, state, onOpen }) {
  const { plan, subs = [], rubric, support, lesson } = state;
  const crit = rubric?.criteria || [];

  if (agent === "PL") {
    if (!plan) return <p className="empty-note">The Planner has not planned yet.</p>;
    const brought = [plan.deliver?.support && "the Coach", plan.deliver?.lesson && "the Designer"].filter(Boolean);
    return (
      <div className="stack">
        <p className="said">“{plan.understanding}”</p>
        <dl className="facts">
          <dt>Marking at a time</dt><dd className="num">{plan.batch_size}</dd>
          <dt>Messages to learners</dt><dd>{plan.deliver?.feedback ? "Yes" : "No, as asked"}</dd>
          <dt>Also brought in</dt><dd>{brought.length ? brought.join(" and ") : "Nobody else"}</dd>
        </dl>
        <ol className="plan-steps">{(plan.steps || []).map((s, i) => <li key={i}><span className="num">{i + 1}</span>{s}</li>)}</ol>
        {(plan.exclude || []).length > 0 && (
          <div>
            <h4>Left out, and why</h4>
            <ul className="said-list">{plan.exclude.map((x) => <li key={x.id}><button type="button" className="idlink" onClick={() => onOpen(x.id)}>{x.id}</button>{x.reason}</li>)}</ul>
          </div>
        )}
      </div>
    );
  }

  if (agent === "MK" || agent === "RV") {
    const key = agent === "MK" ? "marker" : "reviewer";
    const marked = subs.filter((s) => s[key]);
    if (!marked.length) return <p className="empty-note">No marks yet.</p>;
    return (
      <div className="stack">
        {agent === "RV" && <p className="h-note">The Reviewer marks without seeing the Marker's mark. Code then compares the two.</p>}
        {marked.map((s) => {
          const mark = s[key];
          const verdicts = s.history.filter((h) => h.who === (agent === "MK" ? "Marker" : "Reviewer"));
          return (
            <details key={s.id} className="said-card">
              <summary>
                <b>{s.learner}</b>
                <span className="num">{mark.total}/{rubric.total}</span>
                {agent === "RV" && s.marker && <span className="h-note">Marker gave {s.marker.total}</span>}
                <Icon name="chevron" size={14} />
              </summary>
              <ul className="said-list">
                {crit.map((c) => {
                  const row = mark.scores?.[c.id];
                  if (!row) return null;
                  return (
                    <li key={c.id}>
                      <b>{c.name} · {row.score}/{c.max}.</b> {row.reason || "No reason given."}
                      {row.evidence && <q>{row.evidence}</q>}
                    </li>
                  );
                })}
              </ul>
              {verdicts.length > 0 && <ul className="said-list verdicts">{verdicts.map((h, i) => <li key={i}>{h.what}</li>)}</ul>}
              <button type="button" className="btn small" onClick={() => onOpen(s.id)}>Open {s.learner}</button>
            </details>
          );
        })}
      </div>
    );
  }

  if (agent === "MS") {
    const written = subs.filter((s) => s.feedback);
    if (!written.length) return <p className="empty-note">No messages yet. The Messenger starts once marks are settled.</p>;
    return (
      <ul className="said-list">
        {written.map((s) => (
          <li key={s.id}>
            <button type="button" className="idlink" onClick={() => onOpen(s.id)}>{s.id}</button>
            <b>{s.learner}:</b> {s.feedback.subject}
            {s.history.some((h) => /redo|rewr|again/i.test(h.what) && h.who === "Messenger") && <span className="h-note"> (rewritten after a check)</span>}
          </li>
        ))}
      </ul>
    );
  }

  if (agent === "CO") {
    const rows = support?.learners || [];
    if (!rows.length) return <p className="empty-note">{state.plan?.deliver?.support ? "Nobody has been flagged yet." : "The goal did not ask who is falling behind."}</p>;
    return (
      <ul className="said-list">
        {rows.map((e) => (
          <li key={e.id}>
            <button type="button" className="idlink" onClick={() => onOpen(e.id)}>{e.id}</button>
            <b>{e.learner}:</b> {e.plan?.why || "No plan yet."}
            {e.plan?.evidence && <q>{e.plan.evidence}</q>}
          </li>
        ))}
      </ul>
    );
  }

  if (agent === "DS") {
    if (!lesson) return <p className="empty-note">{state.plan?.deliver?.lesson ? "The lesson is still being drafted." : "The goal did not ask for a lesson."}</p>;
    return (
      <div className="stack">
        <p className="said"><b>{lesson.title}.</b> {lesson.why}</p>
        <p className="h-note">{plural(lesson.exercises?.length || 0, "exercise")}, each tried blind by the Reviewer before it was kept. The Designer never sees learners' names.</p>
      </div>
    );
  }
  return null;
}

/**
 * What each colleague is thinking: the decisions it made, the reasons it gave with its answers, and
 * every line it wrote to the log. These are the reasons the models returned and the checks code ran;
 * a model's private working is not shown, because the app never receives it.
 */
export default function TeamThinking({ state, events, onOpen, initialAgent = null }) {
  const team = ORDER.filter((key) => key !== "CL" || state.scripts || state.agents?.CL);
  const busy = team.find((key) => state.agents?.[key] === "working");
  const [picked, setPicked] = useState(initialAgent);
  const agent = picked || busy || "PL";
  const byAgent = useMemo(() => {
    const out = {};
    for (const e of events) (out[e.agent] ||= []).push(e);
    return out;
  }, [events]);
  const last = (key) => [...(byAgent[key] || [])].reverse().find((e) => e.kind !== "WAIT") || byAgent[key]?.[byAgent[key].length - 1];

  return (
    <div className="cols narrow-wide">
      <section className="card">
        <header className="card-head"><h3>The team</h3><p className="h-note">Pick a colleague</p></header>
        <ul className="rows rows-pick">
          {team.map((key) => {
            const st = state.agents?.[key] || "waiting";
            const latest = last(key);
            return (
              <li key={key}>
                <button type="button" className={`row row-btn ${agent === key ? "on" : ""}`} onClick={() => setPicked(key)}>
                  <span className={`agent-badge a-${key}`}>{key}</span>
                  <span className="row-text">
                    <b>{AGENTS[key]?.name} <span className="h-note">· {ROLE[key]}</span></b>
                    <p>{latest ? latest.msg : st === "off" ? "Not asked for in this run" : "Nothing yet"}</p>
                  </span>
                  <span className={`chip chip-state is-${st}`}>{st === "working" && <span className="live-dot" />}{STATE[st] || st}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      <div className="stack">
        <section className="card">
          <header className="card-head">
            <div>
              <h3>{agent === "CL" ? "The Clerk's feedback" : `What the ${AGENTS[agent]?.name} decided, and why`}</h3>
              <p className="h-note">The reasons it gave with its answers, and the checks code ran on them.</p>
            </div>
          </header>
          {agent === "CL"
            ? <ClerkFeedback scripts={state.scripts} subs={state.subs} events={events} onOpen={onOpen} />
            : <Reasons agent={agent} state={state} onOpen={onOpen} />}
        </section>

        <section className="card">
          <header className="card-head">
            <h3>Its reasoning trail</h3>
            <p className="h-note">{plural((byAgent[agent] || []).length, "step")}, oldest first</p>
          </header>
          <Trail agent={agent} lines={byAgent[agent] || []} onOpen={onOpen} />
        </section>
      </div>
    </div>
  );
}
