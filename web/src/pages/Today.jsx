import { useState } from "react";
import { fileUrl, resolveScript } from "../api.js";
import { clock } from "../format.js";
import { nextStep, plainReason, runTitle } from "../plain.js";
import { SEEN_KEY, usePref } from "../prefs.js";
import { go, href } from "../router.js";
import { Av, Band, Empty, Ico, Kpi, Skeleton } from "./ui.jsx";

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

/** What needs the teacher: held scripts, disputed marks and flagged essays, from the run that is on screen. */
export function attentionItems(state, seen = []) {
  const items = [];
  for (const s of state?.subs || []) {
    if (s.status === "escalated" && s.script_hold) {
      items.push({ key: `script-${s.id}`, id: s.id, kind: "script", tone: "hi", icon: "mail", title: `${s.learner} · handwritten script`,
        text: String(s.issue || "The Clerk held this script for you.").replace(/^The handwritten script needs your check: /, "").replace(/ Nothing has been marked from it\.$/, "") + ". Mark it as it stands, or ask for it again?", sub: s });
    } else if (s.status === "escalated") {
      items.push({ key: `mark-${s.id}`, id: s.id, kind: "mark", tone: "hi", icon: "alert", title: `${s.learner} · two marks disagree`,
        text: `The Marker gave ${s.marker?.total ?? "?"} and the Reviewer ${s.reviewer?.total ?? "?"}. Nothing was sent; choose the mark.`, sub: s });
    } else if ((s.flags || []).includes("instruction_to_marker") && !seen.includes(`flag-${s.id}`)) {
      items.push({ key: `flag-${s.id}`, id: s.id, kind: "flag", tone: "md", icon: "flag", title: `${s.learner} · essay flagged`,
        text: `The essay contains text that tries to instruct the marker. It was marked normally${s.final ? ` (${s.final.total}/${state.rubric?.total})` : ""} and reported to you.`, sub: s });
    }
  }
  for (const rec of state?.scripts?.scripts || []) {
    if (rec.status === "held" && !rec.learner) {
      items.push({ key: `unknown-${rec.id}`, kind: "unknown", tone: "hi", icon: "mail", title: `Script ${rec.id} · name not on the class list`,
        text: `The name was read as “${rec.name || "nothing"}”. Open the run to say whose it is.`, rec });
    }
  }
  return items;
}

export default function Today({ state, history, teacher, onOpenLearner, onAction, onChanged, onboarding }) {
  const [seen, setSeen] = usePref(SEEN_KEY, []);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const risk = state?.risk;
  if (!state) return <Skeleton rows={6} />;
  if (onboarding) return onboarding;

  const learners = risk?.learners || [];
  const total = learners.length;
  const essays = learners.filter((l) => l.theory?.marked).length;
  const high = risk?.counts?.High || 0;
  const items = attentionItems(state, seen);
  const help = learners.filter((l) => l.band !== "Low").slice(0, 4);
  const subOf = (id) => (state.subs || []).find((s) => s.id === id);
  const latest = state.id ? state : null;
  const stats = state.stats || {};
  const recent = history.filter((r) => r.id !== state.id).slice(0, 3);
  const date = new Date().toLocaleDateString("en-ZA", { weekday: "long", day: "numeric", month: "long" });

  async function script(sub, choice) {
    setBusy(sub.id);
    setError("");
    try {
      await resolveScript(sub.script, choice);
      onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="l-page">
      <div className="l-head">
        <div>
          <h1>{greeting()}{teacher ? `, ${teacher}` : ""}</h1>
          <div className="l-sub">{date} · Grade 12 CAT</div>
        </div>
        <div className="r">
          <a className="l-btn l-hide-phone" href={href("new", { scripts: 1 })}><Ico name="mail" />Add scripts</a>
          <a className="l-btn p" href={href("new")}><Ico name="play" size={14} />New run</a>
        </div>
      </div>

      <div className="l-kpis">
        <Kpi label="Essays marked" value={essays} of={total} bar={total ? (100 * essays) / total : 0} />
        <Kpi label="Class average" value={risk?.average != null ? `${risk.average}%` : "–"} note="Essays, PC assembly and Windows" />
        <Kpi label="At or above the 50% pass line" value={risk?.passed ?? 0} of={total} note={`${high} ${high === 1 ? "learner needs" : "learners need"} help now`} />
        <Kpi label="Feedback sent" value={latest ? stats.delivered || 0 : "–"} note={latest ? `${items.length} waiting on you` : "No run yet today"} />
      </div>

      <div className="l-row">
        <div className="l-col" style={{ flex: 1.45 }}>
          <section className="l-card">
            <div className="hd">
              <h2>Needs your attention</h2>
              {items.length > 0 && <span className="l-chip hi">{items.length}</span>}
              <span className="r l-small l-muted l-hide-phone">Nothing uncertain is sent or marked until you decide</span>
            </div>
            {items.length === 0 ? (
              <div className="bd l-muted">Nothing is waiting for you. Held scripts and disagreements show up here.</div>
            ) : (
              <div className="l-list">
                {items.map((it) => (
                  <div className="it" key={it.key}>
                    <span className="l-av" style={{ background: it.tone === "hi" ? "var(--hi-bg)" : "var(--md-bg)", color: it.tone === "hi" ? "var(--hi)" : "var(--md)" }}><Ico name={it.icon} size={15} /></span>
                    <div className="grow"><div className="t">{it.title}</div><div className="d">{it.text}</div></div>
                    <div className="r">
                      {it.kind === "script" && <>
                        <button type="button" className="l-btn sm" disabled={busy === it.id} onClick={() => script(it.sub, "set_aside")}>Ask again</button>
                        <button type="button" className="l-btn sm p" disabled={busy === it.id} onClick={() => script(it.sub, "accept")}>Mark as it stands</button>
                      </>}
                      {it.kind === "mark" && <button type="button" className="l-btn sm p" onClick={() => onOpenLearner(it.id, "essay")}>Choose the mark</button>}
                      {it.kind === "flag" && <>
                        <button type="button" className="l-btn sm" onClick={() => setSeen([...seen, it.key])}>Mark as seen</button>
                        <button type="button" className="l-btn sm p" onClick={() => onOpenLearner(it.id, "essay")}>Open essay</button>
                      </>}
                      {it.kind === "unknown" && <a className="l-btn sm p" href={href("run", { tab: "results" })}>Open run</a>}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {error && <p className="l-error" style={{ padding: "0 16px 12px" }}>{error}</p>}
          </section>

          <section className="l-card">
            <div className="hd"><h2>Who needs help this week</h2><span className="r"><a className="l-btn sm ghost" href={href("learners")}>View all learners <Ico name="arrow" size={14} /></a></span></div>
            {!risk ? <div className="bd l-muted">Scoring the class…</div> : help.length === 0 ? (
              <div className="bd l-muted">Everyone is on track this week.</div>
            ) : (
              <div className="l-list">
                {help.map((row) => {
                  const step = nextStep(row, subOf(row.id));
                  return (
                    <div className="it click" key={row.id} onClick={() => onOpenLearner(row.id)}>
                      <Av name={row.learner} />
                      <div className="grow"><div className="t">{row.learner} <Band band={row.band} /></div><div className="d">{plainReason(row)}</div></div>
                      <div className="r l-hide-phone">
                        <button type="button" className="l-btn sm" onClick={(e) => { e.stopPropagation(); onAction(row, step); }}>{step.label}</button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        <div className="l-col" style={{ flex: 1 }}>
          <section className="l-card">
            <div className="hd">
              <h2>Latest run</h2>
              {latest && <span className="r"><span className={`l-chip ${latest.status === "done" ? "ok" : latest.status === "failed" ? "hi" : "bl"}`}>
                {latest.status === "done" ? "Finished" : latest.status === "failed" ? "Stopped" : `Running · ${clock(latest.elapsed)}`}</span></span>}
            </div>
            {!latest ? (
              <div className="bd"><Empty title="No run yet" action={<a className="l-btn p" href={href("new")}>Start your first run</a>}>Your colleague marks, checks itself and tells you who needs help.</Empty></div>
            ) : (
              <div className="bd">
                <div style={{ fontWeight: 600 }}>{runTitle(latest.goal)}</div>
                <div className="l-small l-muted" style={{ margin: "2px 0 12px" }}>{latest.status === "running" ? "Running now" : `Took ${clock(latest.elapsed)}`} · {(latest.subs || []).length} learners{latest.inject_fault ? " · test mode" : ""}</div>
                <div className="l-small" style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 7 }}>
                  <span className="l-muted">Marked and second-marked</span><b>{stats.marked || 0}</b>
                  <span className="l-muted">Caught and fixed by the checks</span><b>{stats.fixed || 0}</b>
                  <span className="l-muted">Held for you</span><b>{stats.escalated || 0}</b>
                  <span className="l-muted">Messages ready for learners</span><b>{stats.delivered || 0}</b>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
                  <a className="l-btn sm" href={href("run")}>Open run</a>
                  {(latest.files || []).includes("marks.csv") && <a className="l-btn sm" href={fileUrl("marks.csv")} download="marks.csv"><Ico name="download" size={13} />Mark sheet</a>}
                </div>
              </div>
            )}
          </section>
          <section className="l-card l-hide-phone">
            <div className="hd"><h2>Recent runs</h2><span className="r"><a className="l-btn sm ghost" href={href("runs")}>All runs</a></span></div>
            {recent.length === 0 ? <div className="bd l-muted l-small">Earlier runs are listed here.</div> : (
              <div className="l-list">
                {recent.map((r) => (
                  <div className="it" key={r.id}>
                    <div className="grow"><div className="t" style={{ fontWeight: 550 }}>{runTitle(r.goal)}</div>
                      <div className="d">{new Date(r.when).toLocaleString("en-ZA", { weekday: "short", hour: "2-digit", minute: "2-digit" })} · {r.marked} marked{r.held ? ` · ${r.held} held` : ""}</div></div>
                    <span className="r"><span className={`l-chip ${r.status === "done" ? (r.held ? "md" : "ok") : "hi"}`}>{r.status === "done" ? (r.held ? "Needs you" : "Done") : "Stopped"}</span></span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
      <div className="l-hide-desk" style={{ marginTop: 16 }}><button type="button" className="l-btn p lg" style={{ width: "100%" }} onClick={() => go("new")}><Ico name="play" size={14} />New run</button></div>
    </div>
  );
}
