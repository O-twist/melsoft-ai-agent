import { useEffect } from "react";
import Icon from "../components/Icon.jsx";
import { href } from "../router.js";

const NAV = [
  ["today", "Today", "home"],
  ["new", "New run", "play"],
  ["runs", "Runs", "clock"],
  ["learners", "Learners", "user"],
  ["classes", "Classes", "flag"],
  ["lab", "Lab", "chip"],
  ["messages", "Messages", "mail"],
];

function aiLine(llm) {
  if (!llm) return { on: false, text: "Connecting…" };
  if (llm.name === "mock") return { on: false, text: llm.switched ? "Offline backup in use" : "Offline mode" };
  return { on: true, text: `AI marking on · ${llm.name === "gemini" ? "Gemini" : llm.name === "openrouter" ? "OpenRouter" : llm.name}` };
}

/** The frame around every page: the sidebar (a slide-out panel on a phone) and the top bar. */
export default function Shell({ page, crumb, badges = {}, llm, className, learners, testOn, menuOpen, onMenu, actions, children }) {
  useEffect(() => {
    if (!menuOpen) return undefined;
    const on = (e) => e.key === "Escape" && onMenu(false);
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [menuOpen, onMenu]);
  const ai = aiLine(llm);
  const nav = (key, label, icon) => (
    <a key={key} href={href(key)} className={page === key ? "on" : ""} aria-current={page === key ? "page" : undefined} onClick={() => onMenu(false)}>
      <Icon name={icon} size={16} />{label}
      {badges[key] ? <span className="ct" aria-label={`${badges[key]} need attention`}>{badges[key]}</span> : null}
    </a>
  );
  return (
    <div className={`l-app ${menuOpen ? "menu-open" : ""}`}>
      <div className="l-pscrim" onClick={() => onMenu(false)} />
      <aside className="l-side" aria-label="Main menu">
        <div className="l-ws">
          <span className="l-logo">L</span>
          <div><b>LabLess</b><small>Teaching colleague</small></div>
          <button type="button" className="l-btn ghost l-close l-hide-desk" style={{ marginLeft: "auto" }} onClick={() => onMenu(false)} aria-label="Close the menu">
            <Icon name="x" size={18} />
          </button>
        </div>
        <a className="l-class" href={href("classes")} onClick={() => onMenu(false)} style={{ textDecoration: "none" }}>
          <b>{className}</b><span>{learners} learners ▾</span>
        </a>
        <nav className="l-nav">
          {NAV.map(([k, l, i]) => nav(k, l, i))}
          <div className="sec">Workspace</div>
          {nav("settings", "Settings & test mode", "shield")}
        </nav>
        <div className="l-foot"><span className={`l-dot ${ai.on ? "" : "off"}`} />{ai.text}</div>
      </aside>
      <div className="l-main">
        <header className="l-top">
          <button type="button" className="l-menu" onClick={() => onMenu(true)} aria-label="Open the menu" aria-expanded={menuOpen}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
          </button>
          <div className="l-crumb">{crumb}</div>
          <div className="r">
            {testOn && <a className="l-testbadge" href={href("settings", { tab: "test" })} title="A planted fault will be added to the next run">Test mode on</a>}
            <span className="l-chip gr l-hide-desk">{className}</span>
            {actions}
          </div>
        </header>
        <main className="l-content" id="main">{children}</main>
      </div>
    </div>
  );
}
