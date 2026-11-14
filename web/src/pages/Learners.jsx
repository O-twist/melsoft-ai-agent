import { useEffect, useState } from "react";
import { resolveEssay, resolveScript } from "../api.js";
import { CatchUpPlan } from "../components/SupportCard.jsx";
import { BAND_WORDS, nextStep, outcomeName, plainReason } from "../plain.js";
import { go } from "../router.js";
import { Av, Band, Empty, Head, Ico, Seg, Skeleton, Tabs } from "./ui.jsx";

/** The learner list: who needs help, why in plain words, and one next step each. */
export default function Learners({ state, week2, weekView, onWeek, onOpen, onAction }) {
  const [tab, setTab] = useState("help");
  const [q, setQ] = useState("");
  const risk = state?.risk;
  if (!risk) return <Skeleton rows={7} />;
  const after = weekView === "2" && week2?.after?.ok ? week2.after : null;
  const board = after || risk;
  const change = Object.fromEntries((week2?.changes || []).map((c) => [c.id, c]));
  const subOf = (id) => (state.subs || []).find((s) => s.id === id);
  const plans = (state.support?.learners || []).filter((e) => e.status === "ready");
  // In Week 2, everyone who was on the rescue list stays in view, so the before and after can be read.
  const needs = board.learners.filter((l) => l.band !== "Low" || (after && change[l.id]));
  const shown = (tab === "help" ? needs : board.learners).filter((l) => !q.trim() || `${l.learner} ${l.id} ${l.reason}`.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div className="l-page">
      <Head title="Learners" sub={`Grade 12 CAT · pass line ${board.config?.pass_line ?? 50}% · combines essays, PC assembly and Windows tasks`}>
        <Seg label="Week" value={weekView} onChange={onWeek} options={[["1", "Week 1"], ["2", "Week 2 (after catch-up)"]]} />
        <button type="button" className="l-btn" onClick={() => go("report", { mode: "class", week: weekView })}><Ico name="download" size={14} />Class report</button>
      </Head>
      {weekView === "2" && week2?.ok && <div className="l-callout" style={{ marginBottom: 14 }}>{week2.summary} The same scoring rules, after a week of the catch-up plan. Week 1 is unchanged.</div>}
      <Tabs label="Learner lists" value={tab} onChange={setTab} tabs={[["help", "Needs help", needs.length], ["all", "All learners", board.learners.length], ["plans", "Catch-up plans", plans.length]]} />

      {tab === "plans" ? (
        plans.length === 0 ? (
          <Empty title="No catch-up plans yet" action={<button type="button" className="l-btn p" onClick={() => go("new")}>Start a run that asks who is falling behind</button>}>
            The Coach writes a plan for each learner who is behind when a run asks for it.
          </Empty>
        ) : (
          <section className="l-card"><div className="l-list">
            {plans.map((e) => (
              <div className="it click" key={e.id} onClick={() => onOpen(e.id, "overview")}>
                <Av name={e.learner} /><div className="grow"><div className="t">{e.learner}</div><div className="d">{e.plan?.why}</div></div>
                <span className="r"><span className="l-chip ok">Plan ready</span></span>
              </div>
            ))}
          </div></section>
        )
      ) : (
        <section className="l-card">
          <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--line2)" }}>
            <input className="l-field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search learners or reasons" aria-label="Search learners" />
          </div>
          <table className="l-table l-stack">
            <thead><tr><th>Learner</th><th>Needs help</th><th>Why, in plain words</th>{after && <th>Week 1 → 2</th>}<th>Next step</th></tr></thead>
            <tbody>
              {shown.map((row) => {
                const step = nextStep(row, subOf(row.id));
                const c = change[row.id];
                return (
                  <tr key={row.id} className="click" onClick={() => onOpen(row.id)}>
                    <td><div className="l-who"><Av name={row.learner} /><div><b>{row.learner}</b><div className="l-mono">{row.id}</div></div></div></td>
                    <td title={`Risk ${row.risk} of 100`}><Band band={row.band} /><div className="l-small l-muted">Risk {row.risk} of 100</div></td>
                    <td className="full" style={{ color: "var(--ink-2)", maxWidth: 440 }}>{plainReason(row)}</td>
                    {after && <td className="l-small">{c ? <>{c.band_before} → <b>{c.band_after}</b><div className="l-muted">{c.overall_before} → {c.overall_after}</div></> : <span className="l-muted">Not on the plan</span>}</td>}
                    <td className="full"><button type="button" className="l-btn sm" onClick={(e) => { e.stopPropagation(); onAction(row, step); }}>{step.label}</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {shown.length === 0 && <div className="l-muted" style={{ padding: 16 }}>{q ? "No learner matches that search." : "Everyone is on track."}</div>}
          {tab === "help" && !q && <div className="l-small l-muted" style={{ padding: "10px 16px", borderTop: "1px solid var(--line2)", textAlign: "center" }}>
            {board.learners.length - needs.length} more learners are on track · <button type="button" className="l-link" onClick={() => setTab("all")}>show all {board.learners.length}</button></div>}
        </section>
      )}
      <p className="l-small l-muted" style={{ marginTop: 10 }}>How “Needs help” is worked out: a fixed rule in code, not the AI. Below the pass line in any area, or no work on record, raises the risk score. High is {risk.config?.bands?.high ?? 45} or more out of 100.</p>
    </div>
  );
}

/** Everything about one learner: the decision waiting, marks, essay, practical work, messages. */
export function LearnerDrawer({ id, tab, onTab, state, week2, weekView, onClose, onChanged, onAction, onCatchUp, onWeek2 }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    const on = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);
  const board = weekView === "2" && week2?.after?.ok ? week2.after : state?.risk;
  const row = board?.learners?.find((l) => l.id === id);
  const sub = (state?.subs || []).find((s) => s.id === id);
  const plan = (state?.support?.learners || []).find((e) => e.id === id);
  const rubric = state?.rubric;
  if (!row && !sub) return null;
  const name = row?.learner || sub?.learner;

  async function decide(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const step = row ? nextStep(row, sub) : null;
  const shown = sub?.final || sub?.marker;
  return (
    <>
      <div className="l-scrim" onClick={onClose} />
      <aside className="l-drawer" role="dialog" aria-modal="true" aria-label={name}>
        <div className="dh">
          <Av name={name} style={{ width: 38, height: 38 }} />
          <div style={{ minWidth: 0 }}><b style={{ fontSize: 15.5 }}>{name}</b><div className="l-small l-muted">{id} · Grade 12 CAT</div></div>
          <span style={{ marginLeft: "auto" }}>{row && <Band band={row.band} />}</span>
          <button type="button" className="l-btn ghost" onClick={onClose} aria-label="Close"><Ico name="x" size={18} /></button>
        </div>
        <Tabs label="Learner" value={tab} onChange={onTab} tabs={[["overview", "Overview"], ["essay", "Essay"], ["practical", "Practical"], ["messages", "Messages"]]} />
        <div className="db">
          {sub?.status === "escalated" && (
            <div className="l-callout warn">
              <b>Your decision is needed.</b> {sub.script_hold ? String(sub.issue || "").replace(/^The handwritten script needs your check: /, "") : `The Marker gave ${sub.marker?.total}/${rubric?.total} and the Reviewer ${sub.reviewer?.total ?? "?"}/${rubric?.total}. ${sub.issue || ""}`}
              <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                {sub.script_hold ? <>
                  <button type="button" className="l-btn sm p" disabled={busy} onClick={() => decide(() => resolveScript(sub.script, "accept"))}>Mark it as it stands</button>
                  <button type="button" className="l-btn sm" disabled={busy} onClick={() => decide(() => resolveScript(sub.script, "set_aside"))}>Ask for it again</button>
                </> : <>
                  {sub.marker && <button type="button" className="l-btn sm p" disabled={busy} onClick={() => decide(() => resolveEssay(sub.id, "marker"))}>Use the Marker's {sub.marker.total}</button>}
                  {sub.reviewer && <button type="button" className="l-btn sm" disabled={busy} onClick={() => decide(() => resolveEssay(sub.id, "reviewer"))}>Use the Reviewer's {sub.reviewer.total}</button>}
                </>}
              </div>
              {error && <p className="l-error">{error}</p>}
            </div>
          )}

          {tab === "overview" && row && <>
            <div>
              <div style={{ fontWeight: 600 }}>{BAND_WORDS[row.band]}{weekView === "2" ? " · Week 2" : ""}</div>
              <div className="l-muted">{plainReason(row)}</div>
              <div className="l-small l-muted" style={{ marginTop: 4 }}>Risk {row.risk} of 100 · overall {row.overall}/100, {row.result === "Pass" ? "a pass" : "not yet a pass"}</div>
            </div>
            <div>
              <div className="l-small l-muted" style={{ marginBottom: 8 }}>By area · pass line {row.pass_line}%</div>
              <div className="l-areas">
                {(row.areas || []).map((a) => (
                  <span key={a.id} style={{ display: "contents" }}>
                    <span>{a.name}</span>
                    <div className="l-bar"><i className={a.percent < row.pass_line ? "hi" : ""} style={{ width: `${a.percent}%` }} /></div>
                    <b>{a.percent}%</b>
                  </span>
                ))}
              </div>
            </div>
            {(row.gaps || []).length > 0 && (
              <div>
                <div className="l-small l-muted" style={{ marginBottom: 6 }}>What to work on</div>
                <div className="l-list" style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
                  {row.gaps.slice(0, 5).map((g) => (
                    <div className="it" key={`${g.outcome}-${g.name}`} style={{ padding: "9px 12px" }}>
                      <div className="grow"><div className="t" style={{ fontWeight: 550 }} title={g.outcome}>{g.name.replace(/^([HS]\d) /, "")} <span className="l-muted" style={{ fontWeight: 400 }}>· {g.percent}%</span></div><div className="d">{g.task}</div></div>
                      {g.link && <span className="r"><button type="button" className="l-btn sm" onClick={() => onCatchUp(row, g.link)}>{g.link.kind === "windows" ? "Open task" : g.link.kind === "model" ? "Open 3D part" : "Open in Lab"}</button></span>}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {plan?.status === "ready" && <div className="l-embed"><div className="l-small l-muted" style={{ marginBottom: 6 }}>Catch-up plan from the Coach</div><CatchUpPlan entry={plan} outcomes={state.outcomes} /></div>}
            {plan?.status === "held" && <div className="l-callout warn">The Coach's plan failed its checks twice, so it is held for you instead of being shown: {(plan.problems || []).join("; ")}.</div>}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {step && step.key !== "open" && <button type="button" className="l-btn p" onClick={() => onAction(row, step)}>{step.label}</button>}
              <button type="button" className="l-btn" onClick={() => go("report", id, { week: weekView })}><Ico name="download" size={14} />Score report</button>
              <button type="button" className="l-btn" onClick={() => onWeek2(id)}>Score week 2</button>
            </div>
            {row.theory_pass_note && <div className="l-callout">{row.theory_pass_note}</div>}
          </>}

          {tab === "essay" && (
            sub?.text ? <>
              {shown && rubric && (
                <table className="l-table" style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
                  <thead><tr><th>Criterion</th><th>Marker</th><th>Reviewer</th><th>Final</th></tr></thead>
                  <tbody>{rubric.criteria.map((c) => (
                    <tr key={c.id}><td>{c.name}<div className="l-small l-muted">{shown.scores[c.id]?.reason}</div></td>
                      <td>{sub.marker?.scores[c.id]?.score ?? "–"}</td><td>{sub.reviewer?.scores[c.id]?.score ?? "–"}</td><td><b>{sub.final?.scores[c.id]?.score ?? "–"}</b>/{c.max}</td></tr>
                  ))}</tbody>
                </table>
              )}
              <div className="l-small l-muted">{rubric?.kind === "practical" ? "The attempt log the agents marked" : sub.source === "script" ? "Transcript of the handwritten script" : "The essay"} · {sub.words} words</div>
              <div className="l-essay">{sub.text}</div>
              {(sub.history || []).length > 0 && <div><div className="l-small l-muted" style={{ marginBottom: 6 }}>What happened</div>
                <ul className="l-small" style={{ paddingLeft: 18, display: "grid", gap: 4 }}>{sub.history.map((h, i) => <li key={i}><b>{h.who}:</b> {h.what}</li>)}</ul></div>}
            </> : <div className="l-muted">{sub ? "Nothing was handed in, so there is nothing to mark yet." : "Start a run to see this learner's marked work."}</div>
          )}

          {tab === "practical" && row && <>
            <div className="l-small l-muted">PC assembly · {row.practical?.marked ? `${row.practical.percent}% (${row.practical.score}/${row.practical.max})` : "no attempt on record"}</div>
            <div className="l-list" style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
              {(row.practical?.outcomes || []).map((o) => (
                <div className="it" key={o.id} style={{ padding: "8px 12px" }} title={o.id}>
                  <div className="grow"><div className="t" style={{ fontWeight: 550 }}>{outcomeName(o.id)}</div><div className="d">{o.detail}</div></div>
                  <span className="r"><span className={`l-chip ${o.percent >= 70 ? "ok" : o.percent >= 50 ? "bl" : "hi"}`}>{o.percent}%</span></span>
                </div>
              ))}
            </div>
            <div className="l-small l-muted">Windows tasks</div>
            <div className="l-list" style={{ border: "1px solid var(--line)", borderRadius: 8 }}>
              {(row.windows || []).map((o) => (
                <div className="it" key={o.id} style={{ padding: "8px 12px" }} title={o.id}>
                  <div className="grow"><div className="t" style={{ fontWeight: 550 }}>{o.name || outcomeName(o.id)}</div><div className="d">{o.detail}</div></div>
                  <span className="r"><span className={`l-chip ${o.percent >= 70 ? "ok" : o.percent >= 50 ? "bl" : "hi"}`}>{o.percent}%</span></span>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="l-btn" onClick={() => go("lab", { tab: "pc", learner: id })}>Open the PC lab</button>
              <button type="button" className="l-btn" onClick={() => go("lab", { tab: "windows", learner: id })}>Open Windows tasks</button>
            </div>
          </>}

          {tab === "messages" && (
            sub?.feedback ? <>
              <div><b>{sub.feedback.subject}</b><div className="l-small l-muted">Written by the Messenger, checked against the settled mark{sub.status === "delivered" ? " · ready to send" : ""}</div></div>
              <div className="l-msg">{sub.feedback.body}</div>
              <div><button type="button" className="l-btn sm" onClick={() => { navigator.clipboard?.writeText(sub.feedback.body); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy message"}</button></div>
            </> : <div className="l-muted">{sub?.status === "escalated" ? "No message: this learner's mark is waiting for your decision, so nothing was written." : "No message for this learner yet."}</div>
          )}
        </div>
      </aside>
    </>
  );
}
