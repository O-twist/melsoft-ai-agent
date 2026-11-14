import { useEffect } from "react";
import Icon from "../components/Icon.jsx";
import { BAND_TONE } from "../plain.js";

export const initials = (name) => {
  const parts = String(name || "?").trim().split(/\s+/);
  return (parts.length > 1 ? parts.slice(0, 2).map((p) => p[0] || "").join("") : parts[0].slice(0, 2)).toUpperCase();
};

export function Av({ name, style }) {
  return <span className="l-av" aria-hidden="true" style={style}>{initials(name)}</span>;
}

export function Band({ band }) {
  return <span className={`l-chip ${BAND_TONE[band] || "gr"}`}>{band === "Low" ? "On track" : band}</span>;
}

export function Tabs({ tabs, value, onChange, label }) {
  return (
    <div className="l-tabs" role="tablist" aria-label={label}>
      {tabs.map(([key, text, n]) => (
        <button key={key} type="button" role="tab" aria-selected={value === key} className={value === key ? "on" : ""} onClick={() => onChange(key)}>
          {text}{n != null && n !== "" && <span className="n">{n}</span>}
        </button>
      ))}
    </div>
  );
}

export function Seg({ options, value, onChange, label }) {
  return (
    <div className="l-seg" role="group" aria-label={label}>
      {options.map(([key, text]) => (
        <button key={key} type="button" className={value === key ? "on" : ""} aria-pressed={value === key} onClick={() => onChange(key)}>{text}</button>
      ))}
    </div>
  );
}

export function Switch({ checked, onChange, label, disabled }) {
  return (
    <span className="l-switch">
      <input type="checkbox" role="switch" aria-label={label} checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <i />
    </span>
  );
}

export function Kpi({ label, value, of, note, bar }) {
  return (
    <div className="l-card l-kpi">
      <div className="l">{label}</div>
      <div className="v">{value}{of != null && <small> of {of}</small>}</div>
      {bar != null && <div className="l-bar" style={{ marginTop: 8 }}><i style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} /></div>}
      {note && <div className="m">{note}</div>}
    </div>
  );
}

export function Head({ title, sub, children }) {
  return (
    <div className="l-head">
      <div>
        <h1>{title}</h1>
        {sub && <div className="l-sub">{sub}</div>}
      </div>
      {children && <div className="r">{children}</div>}
    </div>
  );
}

export function Empty({ title, children, action }) {
  return (
    <div className="l-empty">
      <b>{title}</b>
      {children && <div className="l-small" style={{ marginBottom: action ? 12 : 0 }}>{children}</div>}
      {action}
    </div>
  );
}

export function Skeleton({ rows = 4 }) {
  return (
    <div className="l-card" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} style={{ padding: "14px 16px", borderTop: i ? "1px solid var(--line2)" : 0, display: "flex", gap: 12, alignItems: "center" }}>
          <span className="l-skel" style={{ width: 32, height: 32, borderRadius: "50%" }} />
          <span className="l-skel" style={{ height: 12, flex: 1 }} />
        </div>
      ))}
    </div>
  );
}

/** A small confirm box. Escape or the backdrop cancels. */
export function Confirm({ title, children, yes = "Start", no = "Cancel", onYes, onNo, busy }) {
  useEffect(() => {
    const on = (e) => e.key === "Escape" && onNo();
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onNo]);
  return (
    <>
      <div className="l-scrim top" onClick={onNo} />
      <div className="l-dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        <div className="l-muted">{children}</div>
        <div className="acts">
          <button type="button" className="l-btn" onClick={onNo}>{no}</button>
          <button type="button" className="l-btn p" disabled={busy} onClick={onYes} autoFocus>{busy ? "Starting…" : yes}</button>
        </div>
      </div>
    </>
  );
}

export function Ico({ name, size = 16 }) {
  return <Icon name={name} size={size} />;
}

export const AGENT_ROLES = {
  PL: ["Planner", "plans the run", "Reads your brief and decides which colleagues are needed."],
  CL: ["Clerk", "reads scripts", "Transcribes photographed handwritten pages and matches them to the class list."],
  MK: ["Marker", "first marker", "Marks every essay or practical attempt against the rubric, quoting evidence."],
  RV: ["Reviewer", "second marker", "Marks again without seeing the first mark, and checks every quote and plan."],
  MS: ["Messenger", "writes feedback", "Writes each learner's feedback and the score reports."],
  CO: ["Coach", "catch-up plans", "Works out why a learner is behind and writes a one-week catch-up plan."],
  DS: ["Designer", "lesson plans", "Drafts the next lesson on the class's weakest area. Never sees a learner's name."],
};
