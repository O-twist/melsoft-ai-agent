import { useState } from "react";
import { CatchUpPlan } from "../components/SupportCard.jsx";
import { runTitle } from "../plain.js";
import { href } from "../router.js";
import { Av, Empty, Head, Tabs } from "./ui.jsx";

/** Every message the Messenger wrote, the ones held back, and the Coach's catch-up plans. */
export default function Messages({ state }) {
  const [tab, setTab] = useState("sent");
  const [pick, setPick] = useState(null);
  const [q, setQ] = useState("");
  const [copied, setCopied] = useState(false);
  const subs = state?.subs || [];
  const sent = subs.filter((s) => s.feedback);
  const held = subs.filter((s) => !s.feedback && (s.status === "escalated" || s.status === "agreed"));
  const plans = (state?.support?.learners || []).filter((e) => e.plan);
  const list = (tab === "sent" ? sent : tab === "held" ? held : plans).filter((x) => !q || (x.learner || "").toLowerCase().includes(q.toLowerCase()));
  const chosen = list.find((x) => x.id === pick) || list[0];
  const rubricTotal = state?.rubric?.total;

  return (
    <div className="l-page">
      <Head title="Messages" sub="Feedback your colleague wrote to learners. Email sending is off, so messages are kept here for you to copy or send." />
      <Tabs label="Messages" value={tab} onChange={(t) => { setTab(t); setPick(null); }} tabs={[["sent", "Written", sent.length], ["held", "Held for you", held.length], ["plans", "Catch-up plans", plans.length]]} />
      {!state?.id ? (
        <Empty title="No messages yet" action={<a className="l-btn p" href={href("new")}>Start a run</a>}>When a run marks the class, the Messenger writes one message per learner. They appear here.</Empty>
      ) : (
        <div className="l-row">
          <section className="l-card" style={{ width: 400, flex: "none" }}>
            <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--line2)" }}>
              <input className="l-field" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by learner" aria-label="Filter by learner" />
              <div className="l-small l-muted" style={{ marginTop: 6 }}>From: {runTitle(state.goal)}</div>
            </div>
            <div className="l-list" style={{ maxHeight: "60vh", overflow: "auto" }}>
              {list.length === 0 && <div className="it l-muted">{tab === "held" ? "Nothing is held back." : "Nothing here for this run."}</div>}
              {list.map((x) => (
                <div key={x.id} className={`it click ${chosen?.id === x.id ? "on" : ""}`} onClick={() => setPick(x.id)}>
                  <Av name={x.learner} />
                  <div className="grow"><div className="t">{x.learner}</div>
                    <div className="d" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {tab === "plans" ? x.plan?.why : tab === "held" ? (x.issue || "Waiting for a settled mark") : `${x.final ? `${x.final.total}/${rubricTotal} · ` : ""}${x.feedback.subject}`}</div></div>
                  <span className="r l-small l-muted">{tab === "sent" ? (x.status === "delivered" ? "In outbox" : "Draft") : tab === "held" ? "Held" : "Plan"}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="l-card" style={{ flex: 1 }}>
            {!chosen ? <div className="bd l-muted">Choose a message.</div> : tab === "plans" ? (
              <><div className="hd"><Av name={chosen.learner} /><div><b>Catch-up plan for {chosen.learner}</b><div className="l-small l-muted">Written by the Coach, checked by the Reviewer</div></div></div>
                <div className="bd l-embed"><CatchUpPlan entry={chosen} outcomes={state.outcomes} /></div></>
            ) : tab === "held" ? (
              <><div className="hd"><Av name={chosen.learner} /><div><b>{chosen.learner}</b><div className="l-small l-muted">No message was written</div></div></div>
                <div className="bd l-muted">{chosen.issue || "This learner's mark is not settled yet, so nothing was sent."} Open the learner to decide. <a className="l-link" href={href("learners", chosen.id)}>Open {chosen.learner}</a></div></>
            ) : (
              <><div className="hd"><Av name={chosen.learner} /><div style={{ minWidth: 0 }}><b>To {chosen.learner}</b><div className="l-small l-muted">{chosen.final ? `${chosen.final.total}/${rubricTotal} · ` : ""}written by the Messenger, checked by the Reviewer</div></div>
                <span className="r"><button type="button" className="l-btn sm" onClick={() => { navigator.clipboard?.writeText(`${chosen.feedback.subject}\n\n${chosen.feedback.body}`); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy"}</button></span></div>
                <div className="bd"><div style={{ fontWeight: 600, marginBottom: 8 }}>{chosen.feedback.subject}</div><div className="l-msg">{chosen.feedback.body}</div></div></>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
