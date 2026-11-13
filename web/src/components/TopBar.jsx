import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import { clock, plural } from "../format.js";

function RunState({ status, elapsed, offline }) {
  if (offline) {
    return <span className="chip"><Disc tone="serious" icon="alert" />Reconnecting…</span>;
  }
  if (status === "running") {
    return <span className="chip"><span className="live-dot" /><span className="chip-words">Working ·</span><span className="num">{clock(elapsed)}</span></span>;
  }
  if (status === "done") {
    return <span className="chip"><Disc tone="good" icon="check" /><span className="chip-words">Finished in</span><span className="num">{clock(elapsed)}</span></span>;
  }
  if (status === "failed") {
    return <span className="chip"><Disc tone="critical" icon="alert" />Stopped</span>;
  }
  return <span className="chip"><Disc tone="idle" icon="dot" />Ready</span>;
}

const SERVICE = { gemini: "Gemini", openrouter: "OpenRouter" };

/** Which model is answering. OpenRouter's router names the model it picked, which can differ from the one asked for. */
function llmTitle(llm) {
  if (llm.name === "mock") {
    return "No API key was found, so marks come from simple text heuristics. Add a Gemini or OpenRouter key to .env for real marking.";
  }
  const parts = ["The model the agents are using."];
  if (llm.served && llm.served !== llm.model) parts.push(`OpenRouter passed the last request to ${llm.served}.`);
  if (llm.backup) parts.push(`If Gemini is busy, OpenRouter (${llm.backup}) takes over.`);
  return parts.join(" ");
}

export default function TopBar({ llm, status, elapsed, offline, theme, onToggleTheme }) {
  const mock = llm.name === "mock";
  const other = theme === "dark" ? "light" : "dark";
  return (
    <header className="topbar">
      <div className="topbar-in">
        <div className="brand">
          <span className="brand-mark"><Icon name="logo" size={22} strokeWidth="2.8" /></span>
          <div className="brand-text">
            <strong>Colleague Zero</strong>
            <span>Matric Rescue · an AI teaching colleague</span>
          </div>
        </div>
        <div className="topbar-right">
          <span
            className="chip chip-llm"
            title={llmTitle(llm)}
          >
            <Icon name="chip" size={14} />
            {mock ? "Offline demo mode" : (
              <>{SERVICE[llm.name] || llm.name} · {llm.model}{llm.calls > 0 && <> · <span className="num">{plural(llm.calls, "call")}</span></>}</>
            )}
          </span>
          <RunState status={status} elapsed={elapsed} offline={offline} />
          <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label={`Switch to ${other} theme`} title={`Switch to ${other} theme`}>
            <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
          </button>
        </div>
      </div>
    </header>
  );
}
