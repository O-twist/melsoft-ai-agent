import { useState } from "react";
import { clock } from "../format.js";
import { runTitle } from "../plain.js";
import { go, href } from "../router.js";
import { Confirm, Empty, Head } from "./ui.jsx";

/** Every run this teacher has done, newest first. */
export default function Runs({ state, history }) {
  const [open, setOpen] = useState(null);
  const rows = [...history];
  if (state?.id && !rows.some((r) => r.id === state.id)) {
    rows.unshift({ id: state.id, goal: state.goal, status: state.status, elapsed: state.elapsed, marked: state.stats?.marked || 0, held: state.stats?.escalated || 0, fixed: state.stats?.fixed || 0, when: Date.now() });
  }
  return (
    <div className="l-page">
      <Head title="Runs" sub="Every run, newest first. The latest run opens in full; earlier ones show their summary.">
        <a className="l-btn p" href={href("new")}>New run</a>
      </Head>
      {rows.length === 0 ? (
        <Empty title="No runs yet" action={<a className="l-btn p" href={href("new")}>Start your first run</a>}>Each time you ask your colleague to do something, it is listed here.</Empty>
      ) : (
        <section className="l-card">
          <table className="l-table l-stack">
            <thead><tr><th>When</th><th>What</th><th>Took</th><th>Marked</th><th>Fixed by checks</th><th>Held for you</th><th>Status</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id} className="click" onClick={() => (r.id === state?.id ? go("run") : setOpen(r))}>
                <td className="l-small">{new Date(r.when).toLocaleString("en-ZA", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                <td className="full"><b>{runTitle(r.goal)}</b>{r.planted ? <span className="l-chip md" style={{ marginLeft: 6 }}>Test mode</span> : null}</td>
                <td>{clock(r.elapsed)}</td><td>{r.marked}</td><td>{r.fixed || 0}</td><td>{r.held}</td>
                <td><span className={`l-chip ${r.status === "running" ? "bl" : r.status === "done" ? (r.held ? "md" : "ok") : "hi"}`}>{r.status === "running" ? "Running" : r.status === "done" ? (r.held ? "Needs you" : "Done") : "Stopped"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </section>
      )}
      {open && (
        <Confirm title={runTitle(open.goal)} yes="Close" no="Start it again" onYes={() => setOpen(null)} onNo={() => { setOpen(null); go("new"); }}>
          <div className="l-small" style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 6, color: "var(--ink)" }}>
            <span className="l-muted">Took</span><b>{clock(open.elapsed)}</b>
            <span className="l-muted">Marked and second-marked</span><b>{open.marked}</b>
            <span className="l-muted">Sent back by the Reviewer</span><b>{open.sent_back || 0}</b>
            <span className="l-muted">Fixed by the checks</span><b>{open.fixed || 0}</b>
            <span className="l-muted">Held for you</span><b>{open.held}</b>
            <span className="l-muted">Messages ready</span><b>{open.delivered || 0}</b>
            <span className="l-muted">Catch-up plans</span><b>{open.plans || 0}</b>
          </div>
          <p className="l-small" style={{ marginTop: 10 }}>{open.goal}</p>
        </Confirm>
      )}
    </div>
  );
}
