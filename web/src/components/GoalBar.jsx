import { useLayoutEffect, useRef } from "react";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";

export const DEFAULT_GOAL = "Mark the Grade 12 CAT theory papers against the rubric and send every learner personalised feedback.";
export const PRACTICAL_GOAL = "Mark the PC assembly practical against the rubric and send every learner personalised feedback.";

/* The same kinds of goal for the PC assembly practical, marked from the virtual lab's attempt logs. */
export const PRACTICAL_EXAMPLES = [
  { label: "Mark the practical", goal: PRACTICAL_GOAL },
  {
    label: "Who is falling behind?",
    goal: `${PRACTICAL_GOAL} Then tell me who is falling behind, work out why, and prepare a catch-up plan for each of them.`,
  },
  {
    label: "The whole job",
    goal: `${PRACTICAL_GOAL} Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.`,
  },
];

/* Goals that lead to visibly different plans, and bring different agents into the team. */
const EXAMPLES = [
  { label: "Mark and send feedback", goal: DEFAULT_GOAL },
  {
    label: "Marks only, no messages",
    goal: "Mark the Grade 12 CAT theory papers against the rubric. Do not send feedback to learners: I only want the mark sheet and the class report.",
  },
  {
    label: "Who is falling behind?",
    goal: `${DEFAULT_GOAL} Then tell me who is falling behind, work out why, and prepare a catch-up plan for each of them.`,
  },
  {
    label: "Plan the next lesson",
    goal: `${DEFAULT_GOAL} Then draft a 45-minute lesson on the class's weakest area, with exercises checked against the learning outcomes.`,
  },
  {
    label: "Handwritten scripts too",
    goal: `Read the photographed handwritten scripts first, then ${DEFAULT_GOAL[0].toLowerCase()}${DEFAULT_GOAL.slice(1)}`,
  },
  {
    label: "The whole job",
    goal: `${DEFAULT_GOAL} Tell me who is falling behind, with a catch-up plan for each, and draft a 45-minute lesson on the class's weakest area with exercises.`,
  },
];

export default function GoalBar({
  goal, onGoal, injectFault, onInjectFault, running, hasRun, onStart, error,
  assessment = "essay", onAssessment, practicalAvailable = false,
}) {
  const examples = assessment === "practical" ? PRACTICAL_EXAMPLES : EXAMPLES;
  const ready = !running && goal.trim().length > 0;
  const box = useRef(null);

  // The box is always as tall as the goal typed into it, at any window width.
  useLayoutEffect(() => {
    const fit = () => {
      const el = box.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight + 2}px`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [goal]);

  function onKeyDown(e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && ready) onStart();
  }

  return (
    <section className="card goal">
      <div className="goal-top">
        <label className="goal-label" htmlFor="goal">What should your colleague do?</label>
        {practicalAvailable && (
          <div className="seg" role="group" aria-label="What is being marked">
            {[["essay", "Essays"], ["practical", "PC assembly practical"]].map(([key, label]) => (
              <button
                key={key}
                type="button"
                className={assessment === key ? "on" : ""}
                aria-pressed={assessment === key}
                disabled={running}
                onClick={() => onAssessment(key)}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      <textarea
        id="goal"
        ref={box}
        rows={2}
        value={goal}
        disabled={running}
        onChange={(e) => onGoal(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="For example: mark these essays against the rubric and send every learner feedback."
      />
      <div className="goal-row">
        <div className="examples">
          <span>Try</span>
          {examples.map((ex) => (
            <button
              key={ex.label}
              type="button"
              className={`chip-btn ${goal === ex.goal ? "on" : ""}`}
              aria-pressed={goal === ex.goal}
              disabled={running}
              onClick={() => onGoal(ex.goal)}
            >
              {ex.label}
            </button>
          ))}
        </div>
        <div className="goal-actions">
          <label className="switch">
            <input type="checkbox" checked={injectFault} disabled={running} onChange={(e) => onInjectFault(e.target.checked)} />
            <span className="switch-track" />
            <span className="switch-text">
              Inject a fault
              <small>Proves the Reviewer catches it unprompted</small>
            </span>
          </label>
          <button type="button" className="btn primary" disabled={!ready} onClick={onStart}>
            {running ? (
              <><span className="spinner" />Working…</>
            ) : (
              <><Icon name="play" size={15} />{hasRun ? "Run again" : "Start work"}</>
            )}
          </button>
        </div>
      </div>
      {error && (
        <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>
      )}
    </section>
  );
}
