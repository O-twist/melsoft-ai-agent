import { useEffect, useState } from "react";
import { submitWindows, windowsTasks } from "../api.js";

/**
 * Windows practice beside the simulator.
 * The iframe is the same win11.blueedge.me screen CompuClass embeds
 * (screens/Windows11SimulatorScreen.js). Supabase session tracking is left out:
 * the simulator sends nothing back, so the checklist records the proof and the
 * Reviewer checks it on the server.
 */
export default function WindowsStation({ subs, focus, onSaved }) {
  const [tasks, setTasks] = useState([]);
  const [learner, setLearner] = useState("");
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    windowsTasks().then((data) => setTasks(data.tasks || [])).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (focus?.learnerId) setLearner(focus.learnerId);
    if (focus?.target) {
      document.getElementById(`win-task-${focus.target}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [focus?.learnerId, focus?.target, focus?.nonce]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const out = await submitWindows(learner, answers);
      setResult(out);
      onSaved?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card lab" id="windows-station">
      <header className="card-head">
        <div>
          <h2>Windows simulator</h2>
          <p>
            Practise the four Windows tasks in the simulator, then answer the proof question for each one.
            The simulator does not send results back. The Reviewer checks the answers you type.
          </p>
        </div>
      </header>

      <div className="win-layout">
        <div>
          <iframe
            className="win-frame"
            title="Windows 11 simulator from win11.blueedge.me"
            src="https://win11.blueedge.me/"
          />
          <p className="win-credit">
            Windows 11 simulator by <a href="https://win11.blueedge.me/" target="_blank" rel="noreferrer">win11.blueedge.me</a>.
            It runs in the page and does not share what the learner clicked.
          </p>
        </div>

        <form className="win-tasks" onSubmit={submit}>
          <label>
            <span className="sr-only">Learner</span>
            <select className="select" value={learner} onChange={(event) => { setLearner(event.target.value); setResult(null); }}>
              <option value="">Choose a learner…</option>
              {subs.map((sub) => <option key={sub.id} value={sub.id}>{sub.id} {sub.learner}</option>)}
            </select>
          </label>
          <ol className="win-list">
            {tasks.map((task) => {
              const marked = result?.outcomes?.[task.id];
              const on = focus?.target === task.id;
              return (
                <li key={task.id} id={`win-task-${task.id}`} className={on ? "is-focus" : ""}>
                  <p><span className="otag">{task.id}</span> <b>{task.name}</b></p>
                  <p>{task.instruction}</p>
                  <label>
                    {task.proof}
                    <input
                      className="input"
                      value={answers[task.id] || ""}
                      onChange={(event) => setAnswers((prev) => ({ ...prev, [task.id]: event.target.value }))}
                    />
                  </label>
                  {marked && <p className={`lab-feedback ${marked.verdict === "agreed" ? "ok" : "error"}`}>{marked.note}</p>}
                </li>
              );
            })}
          </ol>
          <button type="submit" className="btn small primary" disabled={!learner || busy}>
            {busy ? "Checking…" : "Hand in the proofs"}
          </button>
          {result && <p className="rescue-note" role="status">{result.summary}</p>}
          {error && <p className="form-error" role="alert">{error}</p>}
        </form>
      </div>
    </section>
  );
}
