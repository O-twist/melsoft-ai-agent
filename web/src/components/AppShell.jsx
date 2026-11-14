import { useEffect, useState } from "react";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";

/* The one navigation list, used by the desktop sidebar and the phone panel alike. */
const NAV = [
  { page: "today", label: "Today", icon: "home" },
  { page: "new", label: "New run", icon: "plus" },
  { page: "runs", label: "Runs", icon: "clock" },
  { page: "learners", label: "Learners", icon: "people" },
  { page: "classes", label: "Classes", icon: "book" },
  { page: "lab", label: "Lab", icon: "chip" },
  { page: "messages", label: "Messages", icon: "mail" },
];
const WORKSPACE = [{ page: "settings", label: "Settings & test mode", icon: "cog" }];

export const PAGE_TITLE = {
  today: "Today", new: "New run", runs: "Runs", run: "Run", learners: "Learners",
  classes: "Classes", lab: "Lab", messages: "Messages", settings: "Settings & test mode",
};

function Nav({ page, go, counts, onPick }) {
  const item = (row) => (
    <li key={row.page}>
      <button
        type="button"
        className={`nav-item ${page === row.page || (page === "run" && row.page === "runs") ? "on" : ""}`}
        aria-current={page === row.page ? "page" : undefined}
        onClick={() => {
          go(row.page);
          onPick?.();
        }}
      >
        <Icon name={row.icon} size={16} />
        {row.label}
        {counts[row.page] > 0 && <span className="nav-count">{counts[row.page]}</span>}
      </button>
    </li>
  );
  return (
    <nav className="nav" aria-label="Sections">
      <ul>{NAV.map(item)}</ul>
      <p className="nav-section">Workspace</p>
      <ul>{WORKSPACE.map(item)}</ul>
    </nav>
  );
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark"><Icon name="logo" size={17} strokeWidth="2.8" /></span>
      <span className="brand-text">
        <strong>Colleague Zero</strong>
        <small>Teaching colleague</small>
      </span>
    </div>
  );
}

function ClassPick({ className, learners }) {
  return (
    <div className="classpick">
      <b>{className}</b>
      <span>{learners} learners</span>
    </div>
  );
}

function Footer({ llm, offline }) {
  const mock = llm?.name === "mock";
  const where = mock ? "Offline demo mode" : `AI marking on · ${llm?.name === "gemini" ? "Gemini" : llm?.name === "openrouter" ? "OpenRouter" : llm?.name}`;
  return (
    <div className="shell-foot">
      <span className={`live-dot ${offline ? "is-off" : mock ? "is-mock" : ""}`} />
      {offline ? "Reconnecting to the server…" : where}
    </div>
  );
}

/**
 * The frame every page sits in: a fixed sidebar on a laptop, and on a phone a top bar with a menu
 * button that slides the same list in over the page. Each page gets its own scroll area, so the
 * frame itself never scrolls away.
 */
export default function AppShell({ page, go, state, offline, counts, testMode, children }) {
  const [open, setOpen] = useState(false);
  const className = state?.rubric?.subject || state?.rubric?.title?.replace(/\s*\(.*\)$/, "") || "Sample class";
  const learners = state?.subs?.length ?? 0;

  // The panel is a phone thing: close it on Escape, and whenever the window grows to a laptop.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    const wide = window.matchMedia("(min-width: 900px)");
    const onWide = () => wide.matches && setOpen(false);
    window.addEventListener("keydown", onKey);
    wide.addEventListener("change", onWide);
    return () => {
      window.removeEventListener("keydown", onKey);
      wide.removeEventListener("change", onWide);
    };
  }, [open]);

  return (
    <div className="shell">
      <aside className="side no-print">
        <Brand />
        <ClassPick className={className} learners={learners} />
        <Nav page={page} go={go} counts={counts} />
        <Footer llm={state?.llm} offline={offline} />
      </aside>

      {open && (
        <>
          <div className="shell-scrim no-print" onClick={() => setOpen(false)} />
          <aside className="side side-panel no-print" role="dialog" aria-modal="true" aria-label="Sections">
            <div className="panel-head">
              <Brand />
              <button type="button" className="icon-btn" onClick={() => setOpen(false)} aria-label="Close the menu">
                <Icon name="x" size={18} />
              </button>
            </div>
            <ClassPick className={className} learners={learners} />
            <Nav page={page} go={go} counts={counts} onPick={() => setOpen(false)} />
            <Footer llm={state?.llm} offline={offline} />
          </aside>
        </>
      )}

      <div className="main">
        <header className="page-top no-print">
          <button type="button" className="icon-btn menu-btn" onClick={() => setOpen(true)} aria-label="Open the menu">
            <Icon name="menu" size={18} />
          </button>
          <h1 className="page-title">{PAGE_TITLE[page]}</h1>
          <div className="page-top-right">
            {testMode && (
              <span className="chip chip-test" title="A fault is planted on purpose. Planted items are always labelled.">
                <Disc tone="warn" icon="flag" />Test mode on
              </span>
            )}
            <span className="chip chip-class">{className}</span>
          </div>
        </header>
        <div className="page-body">{children}</div>
      </div>
    </div>
  );
}
