import { useRef } from "react";
import { advanceLoop, loopStatus } from "../loop.js";

const STATE_LABEL = {
  waiting: "Waiting",
  working: "In progress",
  done: "Done",
  clear: "Nothing to correct",
};

/** The Plan, Do, Check, Correct, Deliver loop. `compact` is the row of dots on the navy home card. */
export default function LoopStatus({ state, compact = false }) {
  const memory = useRef({ id: undefined, frontier: -1 });
  const id = state?.id || "idle";
  if (memory.current.id !== id) memory.current = { id, frontier: -1 };
  memory.current.frontier = advanceLoop(memory.current.frontier, state);
  const phases = loopStatus(memory.current.frontier, state);

  return (
    <ol className={compact ? "loop compact" : "loop"} aria-label="Agent loop">
      {phases.map((phase, index) => (
        <li key={phase.id} className={`loop-step is-${phase.state}`}>
          <span className="loop-mark" aria-hidden="true" />
          <span className="loop-name">{phase.label}</span>
          {!compact && <span className="loop-state">{STATE_LABEL[phase.state]}</span>}
          {compact && index < phases.length - 1 && <span className="loop-line" aria-hidden="true" />}
        </li>
      ))}
    </ol>
  );
}
