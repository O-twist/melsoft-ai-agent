import Icon from "./Icon.jsx";
import { Disc, Pill } from "./Badge.jsx";
import { fileUrl } from "../api.js";
import { plural } from "../format.js";
import ModelViewer from "./ModelViewer.jsx";

const EXERCISE_STATE = {
  unchecked: { tone: "idle", icon: "clock", label: "Waiting to be tried" },
  ok: { tone: "good", icon: "check", label: "Passed the blind trial" },
  fixed: { tone: "accent", icon: "refresh", label: "Reworked, then passed" },
  dropped: { tone: "serious", icon: "x", label: "Dropped" },
};
const LEVEL = { support: "Support", core: "Core", extension: "Extension" };

/** A list of problems as the server words them ("it has no model answer"), as one sentence. */
function sentence(problems) {
  const text = problems.join("; ");
  return text ? `${text[0].toUpperCase()}${text.slice(1)}.` : "";
}

function Exercise({ exercise, open }) {
  const state = EXERCISE_STATE[exercise.status] || EXERCISE_STATE.unchecked;
  const trial = exercise.check;
  return (
    <li>
      <details open={open}>
        <summary>
          <span className="fold-main">
            <b><span className="mono">{exercise.id}</span>{LEVEL[exercise.level] || "No level given"}</b>
            <span>Labelled as practising {exercise.outcome || "no outcome"}</span>
          </span>
          <span className="fold-meta"><Pill tone={state.tone} icon={state.icon}>{state.label}</Pill></span>
          <Icon name="chevron" size={16} className="chev" />
        </summary>
        <div className="fold-body">
          <p className="worksheet">{exercise.task}</p>
          <dl className="facts">
            {exercise.answer && (
              <div>
                <dt>Model answer</dt>
                <dd>{exercise.answer}</dd>
              </div>
            )}
            {trial && (
              <div>
                <dt>Blind trial</dt>
                <dd>
                  Shown only the task, the Reviewer{" "}
                  {trial.outcome
                    ? <>read it as practising {trial.outcome}{trial.outcome === exercise.outcome && ", as labelled"}.</>
                    : "could not say which outcome it practises."}
                  {trial.problem && <> It could not do the exercise as written: {trial.problem}</>}
                  {trial.answer && <blockquote>{trial.answer}</blockquote>}
                </dd>
              </div>
            )}
            {exercise.problems.length > 0 && (
              <div>
                <dt>{exercise.status === "dropped" ? "Dropped because" : "First sent back"}</dt>
                <dd>{sentence(exercise.problems)}</dd>
              </div>
            )}
          </dl>
        </div>
      </details>
    </li>
  );
}

/** How the checks on the exercises came out, in one pill. */
function Verdict({ lesson }) {
  const count = (status) => lesson.exercises.filter((ex) => ex.status === status).length;
  if (lesson.status !== "ready") return <Pill tone="idle" icon="clock">Exercises being tried blind</Pill>;
  const notes = [count("fixed") > 0 && `${count("fixed")} after a rework`, count("dropped") > 0 && `${count("dropped")} dropped`].filter(Boolean);
  return (
    <Pill tone="good" icon="check">
      {plural(count("ok") + count("fixed"), "exercise")} passed the blind trial{notes.length > 0 && ` (${notes.join(", ")})`}
    </Pill>
  );
}

/** The lesson the Designer drafted for the class's weakest area, with what the checks made of each exercise. */
export default function LessonCard({ lesson, outcomes, status, files, practical = false }) {
  const outcomeText = Object.fromEntries(outcomes.map((o) => [o.id, o.text]));
  const shown = lesson && (lesson.status === "checking" || lesson.status === "ready");

  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2>The next lesson</h2>
          <p>Drafted by the Designer for the class's weakest area. The Reviewer tried every exercise without seeing its label or its answer.</p>
        </div>
        {files.includes("lesson_plan.md") && (
          <a className="btn small" href={fileUrl("lesson_plan.md")} download="lesson_plan.md">
            <Icon name="download" size={14} />Lesson plan
          </a>
        )}
      </header>

      {!lesson && (
        <p className="empty-note">
          {status === "running" ? "The Designer starts once every mark is settled." : "The run stopped before the Designer started."}
        </p>
      )}
      {lesson?.status === "drafting" && (
        <p className="empty-note">
          The Designer is drafting a {lesson.minutes}-minute lesson
          {lesson.target && <> on {lesson.target.name.toLowerCase()}, the class's weakest area at {lesson.target.pct}%</>}…
        </p>
      )}
      {lesson?.status === "held" && (
        <p className="held-note">
          <b>No lesson is offered.</b> The draft failed its checks (it {lesson.problems.join("; ")}), so it was held back
          and no lesson plan was written.
        </p>
      )}

      {shown && (
        <>
          <h3 className="lesson-title">{lesson.title}</h3>
          <ul className="lesson-facts">
            <li><Disc tone="accent" icon="clock" />{lesson.minutes} minutes</li>
            <li><Disc tone="accent" icon="dot" />Targets {lesson.target.name.toLowerCase()}, the class's weakest area at {lesson.target.pct}%</li>
            <li><Verdict lesson={lesson} /></li>
          </ul>
          {lesson.why && <p className="lesson-why">{lesson.why}</p>}

          <div className="lesson-cols">
            <div className="lesson-col">
              <h3>Learning outcomes</h3>
              <ul className="outcomes">
                {lesson.outcomes.map((id) => (
                  <li key={id}><span className="otag">{id}</span><span>{outcomeText[id]}</span></li>
                ))}
              </ul>

              <h3>How the {lesson.minutes} minutes run</h3>
              <ol className="phases">
                {lesson.phases.map((phase, i) => (
                  <li key={i}>
                    <span className="phase-min">{phase.minutes}<small>min</small></span>
                    <div>
                      <b>{phase.name}</b>
                      {phase.teacher && <p><span className="role">Teacher</span>{phase.teacher}</p>}
                      {phase.learners && <p><span className="role">Learners</span>{phase.learners}</p>}
                    </div>
                  </li>
                ))}
              </ol>

              {practical && (
                <>
                  <h3>Look inside a PC</h3>
                  <ModelViewer />
                </>
              )}

              {lesson.exit_ticket && (
                <>
                  <h3>Exit ticket</h3>
                  <p className="worksheet">{lesson.exit_ticket}</p>
                </>
              )}
            </div>

            <div className="lesson-col">
              <h3>Exercises</h3>
              <ul className="folds">
                {lesson.exercises.map((exercise, i) => <Exercise key={exercise.id} exercise={exercise} open={i === 0} />)}
              </ul>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
