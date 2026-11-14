import Icon from "../components/Icon.jsx";
import { Disc } from "../components/Badge.jsx";
import { AGENTS } from "../format.js";

const ROLE = {
  PL: "Reads your brief and decides which colleagues join the run.",
  CL: "Transcribes photographed handwritten pages, matches each name to the class list and checks the page numbers.",
  MK: "Marks each script against the rubric and the memo, quoting evidence for every criterion.",
  RV: "Second-marks every script without seeing the first mark, and sends disagreements back.",
  MS: "Writes each learner's feedback and the class report.",
  CO: "Works out why a learner is falling behind and plans their catch-up week.",
  DS: "Drafts the next lesson on the class's weakest area, with exercises tried blind.",
};

function Switch({ on, onChange, disabled, title, note }) {
  return (
    <label className="switch switch-row">
      <input type="checkbox" checked={on} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track" />
      <span className="switch-text">
        {title}
        <small>{note}</small>
      </span>
    </label>
  );
}

/** How the colleague works, and the switches that show it catching its own mistakes. */
export default function Settings({ state, theme, onToggleTheme, injectFault, onInjectFault, injectOcrFault, onInjectOcrFault, running }) {
  const llm = state.llm || {};
  const mock = llm.name === "mock";

  return (
    <>
      <header className="page-head">
        <div>
          <h2 className="h-page">Settings &amp; test mode</h2>
          <p className="lede">How your colleague works, and the tools for showing that it checks itself.</p>
        </div>
      </header>

      <div className="cols wide-narrow">
        <div className="stack">
          <section className="card">
            <header className="card-head">
              <Icon name="shield" size={16} />
              <h3>Show how it checks itself</h3>
              <span className="chip chip-count">For demos and training</span>
            </header>
            <div className="card-body stack">
              <Switch
                on={injectFault}
                onChange={onInjectFault}
                disabled={running}
                title="Plant a wrong mark"
                note="Spoils one mark, and one lesson exercise, on purpose after the Marker finishes. The Reviewer should catch and fix them."
              />
              <Switch
                on={injectOcrFault}
                onChange={onInjectOcrFault}
                disabled={running}
                title="Plant a bad handwriting reading"
                note="Deletes half of one transcript. The Clerk's line count should notice and read the page again. Only applies when photos are added."
              />
              <p className="callout">
                While either switch is on, the top bar shows <b>Test mode on</b> and every planted item is labelled in Self-checks.
                Nothing planted is sent to a learner.
              </p>
            </div>
          </section>

          <section className="card">
            <header className="card-head"><h3>About the agents</h3></header>
            <dl className="glossary">
              {Object.entries(AGENTS).map(([key, agent]) => (
                <div key={key}>
                  <dt><span className={`agent-dot a-${key}`} aria-hidden="true" />{agent.name}</dt>
                  <dd>{ROLE[key] || agent.job}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <header className="card-head"><h3>AI marking</h3></header>
            <dl className="facts card-body">
              <dt>Status</dt>
              <dd>{mock ? <><Disc tone="warn" icon="flag" />Offline demo mode</> : <><span className="live-dot" />On</>}</dd>
              <dt>Model</dt>
              <dd>{mock ? "Simple text heuristics" : llm.model}</dd>
              {llm.served && llm.served !== llm.model && (<><dt>Last served by</dt><dd>{llm.served}</dd></>)}
              {llm.backup && (<><dt>Backup</dt><dd>{llm.backup}</dd></>)}
              <dt>Calls in this run</dt>
              <dd className="num">{llm.calls ?? 0}</dd>
            </dl>
            {mock && (
              <p className="card-foot h-note">
                No API key was found, so marks come from simple text heuristics. Put a <span className="mono">GEMINI_API_KEY</span> or{" "}
                <span className="mono">OPENROUTER_API_KEY</span> in <span className="mono">.env</span> for real marking.
              </p>
            )}
          </section>

          <section className="card">
            <header className="card-head"><h3>Appearance</h3></header>
            <div className="card-body">
              <div className="seg" role="group" aria-label="Theme">
                {[["light", "Light", "sun"], ["dark", "Dark", "moon"]].map(([key, label, icon]) => (
                  <button key={key} type="button" className={theme === key ? "on" : ""} aria-pressed={theme === key} onClick={() => theme !== key && onToggleTheme()}>
                    <Icon name={icon} size={14} />{label}
                  </button>
                ))}
              </div>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
