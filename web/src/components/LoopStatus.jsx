import { useRef } from "react";
import { advanceLoop, loopStatus } from "../loop.js";

const STATE_LABEL = {
  waiting: "Waiting",
  working: "In progress",
  done: "Done",
  clear: "Nothing to correct",
};

/** The Plan, Do, Check, Correct, Deliver loop, kept at the furthest phase this run has reached. */
export default function LoopStatus({ state }) {
  const memory = useRef({ id: undefined, frontier: -1 });
  const id = state?.id || "idle";
  if (memory.current.id !== id) memory.current = { id, frontier: -1 };
  memory.current.frontier = advanceLoop(memory.current.frontier, state);
  const phases = loopStatus(memory.current.frontier, state);

  return (
    <ol className="loop" aria-label="Agent loop">
      {phases.map((phase) => (
        <li key={phase.id} className={`loop-step is-${phase.state}`}>
          <span className="loop-mark" aria-hidden="true" />
          <span className="loop-name">{phase.label}</span>
          <span className="loop-state">{STATE_LABEL[phase.state]}</span>
        </li>
      ))}
    </ol>
  );
}
