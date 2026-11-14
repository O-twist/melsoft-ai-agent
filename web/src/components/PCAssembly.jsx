import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import { clock } from "../format.js";
import { listLiveAttempts, saveAttempt } from "../api.js";
import {
  CASE_RATIO, ORDER, PARTS, expectedPart, isDone, newAttempt, onSlot, stop, takeHint, toRecord, tryPart,
} from "../assembly.js";

const IMG = (file) => `/pc-assembly/${file}`;
const BY_ID = Object.fromEntries(PARTS.map((p) => [p.id, p]));

/** A part's picture filling a box. RAM is drawn upright, so its picture is turned a quarter. */
function PartPicture({ part }) {
  if (!part.rotate) return <img className="part-img" src={IMG(part.img)} alt="" draggable={false} />;
  // Turned a quarter, the picture's width runs along the slot's height: size it from the slot's proportions.
  const across = (part.slot.width * CASE_RATIO) / part.slot.height; // slot width / slot height, in pixels
  const turned = { width: `${100 / across}%`, height: `${100 * across}%`, inset: "auto", left: "50%", top: "50%",
                   transform: "translate(-50%, -50%) rotate(90deg)", objectFit: "fill" };
  return <img className="part-img" style={turned} src={IMG(part.img)} alt="" draggable={false} />;
}

/** One part in the open case: drawn once installed, glowing while it is the next one, otherwise hidden. */
function Slot({ part, state }) {
  if (state === "locked") return null;
  const s = part.slot;
  const box = { left: `${100 * s.left}%`, top: `${100 * s.top}%`, width: `${100 * s.width}%`, height: `${100 * s.height}%` };
  return state === "filled"
    ? <div className="slot filled" style={box}><PartPicture part={part} /></div>
    : <div className="slot active" style={box} aria-hidden="true" />;
}

/**
 * PC Assembly Challenge, ported from CompuClass screens/PCAssemblyScreen.js.
 * Pointer events stand in for PanResponder. Expo, Haptics and progress storage are not used.
 * The same six parts, slot positions, order, hints and feedback text are kept.
 * Every try is still recorded (assembly.js) so a saved attempt can be marked.
 */
export default function PCAssembly({ subs, focus, onViewModel }) {
  const [learner, setLearner] = useState(focus?.learnerId || "");
  const [attempt, setAttempt] = useState(() => newAttempt(focus?.learnerId || "", Date.now()));
  const [now, setNow] = useState(Date.now());
  const [drag, setDrag] = useState(null); // { id, x, y } in page coordinates while a part is being dragged
  const [feedback, setFeedback] = useState(null);
  const [flash, setFlash] = useState(0); // bumps on every wrong try, to replay the shake
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");
  const [live, setLive] = useState([]);
  const caseRef = useRef(null);

  const running = Boolean(attempt) && !isDone(attempt) && attempt.stoppedAt == null;
  const finished = Boolean(attempt) && !running;
  const expected = attempt ? expectedPart(attempt) : null;
  const names = useMemo(() => Object.fromEntries(subs.map((s) => [s.id, s.learner])), [subs]);

  useEffect(() => {
    listLiveAttempts().then(setLive).catch(() => {});
  }, []);
  useEffect(() => {
    if (focus?.learnerId) setLearner(focus.learnerId);
  }, [focus?.learnerId, focus?.step, focus?.nonce]);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [running]);

  function begin() {
    setAttempt(newAttempt(learner, Date.now()));
    setNow(Date.now());
    setFeedback(null);
    setSaved(null);
    setError("");
  }

  function attemptPart(partId, slotHit) {
    const [next, what] = tryPart(attempt, partId, slotHit, Date.now());
    if (what === "ignored") return;
    setAttempt(next);
    const name = BY_ID[partId].name;
    if (what === "installed") {
      setFeedback({ kind: "ok", text: `Correct! ${name} installed.` });
    } else {
      setFlash((n) => n + 1);
      setFeedback({ kind: "error", text: what === "wrong_part" ? `Incorrect — the ${name} doesn't go in next.` : `Incorrect — the ${name} goes in the glowing spot.` });
    }
  }

  // Dragging, with pointer events: the card keeps the pointer until it is let go, so a drag that leaves the card still ends here.
  const startDrag = (e, id) => {
    if (!running) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    setDrag({ id, x: e.clientX, y: e.clientY });
  };
  const moveDrag = (e) => drag && setDrag({ ...drag, x: e.clientX, y: e.clientY });
  const endDrag = (e) => {
    if (!drag) return;
    const id = drag.id;
    setDrag(null);
    const r = caseRef.current.getBoundingClientRect();
    const px = e.clientX - r.left, py = e.clientY - r.top;
    if (px < 0 || py < 0 || px > r.width || py > r.height) return; // dropped outside the case: back to the tray, no mistake
    attemptPart(id, Boolean(expected) && onSlot(BY_ID[expected], px, py, r.width, r.height));
  };

  async function save() {
    setError("");
    if (!learner) {
      setError("Choose a learner from the class, then save the build for marking.");
      return;
    }
    try {
      const out = await saveAttempt(toRecord({ ...attempt, learnerId: learner }, Date.now()));
      setSaved(out);
      setLive(await listLiveAttempts());
    } catch (e) {
      setError(e.message);
    }
  }

  const record = attempt ? toRecord(attempt, now) : null;
  const download = useMemo(
    () => (finished ? URL.createObjectURL(new Blob([JSON.stringify(toRecord(attempt, Date.now()), null, 1)], { type: "application/json" })) : null),
    [attempt, finished],
  );
  useEffect(() => () => download && URL.revokeObjectURL(download), [download]);
  const remaining = PARTS.filter((p) => !attempt?.installed.includes(p.id));
  const state = (id) => (attempt?.installed.includes(id) ? "filled" : expected === id && running ? "active" : "locked");
  const dragging = drag && BY_ID[drag.id];

  return (
    <section className="card lab">
      <header className="card-head">
        <div className="challenge-head">
          <div>
            <h2>PC Assembly Challenge</h2>
            <p>Drag the next part into the glowing spot, or use Place.</p>
          </div>
          <span className="progress-pill" aria-label={`${attempt.installed.length} of ${ORDER.length} parts installed`}>
            {attempt.installed.length}/{ORDER.length}
          </span>
        </div>
        <div className="ingest-actions">
          <label>
            <span className="sr-only">Learner</span>
            <select className="select" value={learner} onChange={(e) => setLearner(e.target.value)}>
              <option value="">Choose a learner…</option>
              {subs.map((s) => <option key={s.id} value={s.id}>{s.id} {s.learner}</option>)}
            </select>
          </label>
          <button type="button" className="btn small" onClick={begin}>
            New Build
          </button>
        </div>
      </header>

      {focus?.step && (
        <p className="rescue-note" role="status">
          Catch-up step: <b>{PARTS.find((part) => part.id.toLowerCase() === String(focus.step).toLowerCase())?.name || focus.step}</b>.
          {focus.learnerId ? ` ${names[focus.learnerId] || focus.learnerId} is selected.` : ""}
          {" "}Earlier parts have to go in first. This part is highlighted in the tray.
        </p>
      )}

      {live.length > 0 && (
        <p className="lab-live">
          Recorded live, and used in the next practical run:{" "}
          {live.map((a) => <span key={a.learner_id} className="otag" title={names[a.learner_id]}>{a.learner_id}</span>)}
        </p>
      )}

      {attempt && (
        <>
          <div className="progress-track" aria-hidden="true">
            <span style={{ width: `${(100 * attempt.installed.length) / ORDER.length}%` }} />
          </div>
          <div className="lab-bar">
            {learner && <b>{learner} {names[learner]}</b>}
            <span className="mono"><Icon name="clock" size={13} /> {clock(record.duration_seconds)}</span>
            <span>{record.mistakes} mistake{record.mistakes === 1 ? "" : "s"} · {record.hints} hint{record.hints === 1 ? "" : "s"}</span>
          </div>

          <div className="lab-work">
            <div className="lab-stage">
              <div ref={caseRef} key={flash} className={`case ${flash ? "shake" : ""}`} style={{ aspectRatio: CASE_RATIO }}>
                <img className="case-img" src={IMG("case-open.png")} alt="An open PC case, waiting for parts" draggable={false} />
                {PARTS.map((p) => <Slot key={p.id} part={p} state={state(p.id)} />)}
                {flash > 0 && feedback?.kind === "error" && <div className="case-wrong" aria-hidden="true"><Icon name="x" size={16} />Incorrect</div>}
              </div>

              {running ? (
                <div className={`lab-info ${attempt.hinted ? "hinted" : ""}`}>
                  {attempt.hinted && <img src={IMG(BY_ID[expected].img)} alt="" />}
                  <div>
                    <b>Step {attempt.installed.length + 1} of {ORDER.length}{attempt.hinted ? `: ${BY_ID[expected].name}` : ""}</b>
                    <p>{attempt.hinted ? BY_ID[expected].tip : "Which component goes into the glowing spot?"}</p>
                    {feedback && <p className={`lab-feedback ${feedback.kind}`} role="status">{feedback.text}</p>}
                  </div>
                  <div className="lab-info-actions">
                    {!attempt.hinted && (
                      <button type="button" className="btn small" onClick={() => setAttempt(takeHint(attempt))}>
                        <Icon name="zap" size={14} />Hint
                      </button>
                    )}
                    <button type="button" className="btn small" onClick={() => setAttempt(stop(attempt, Date.now()))}>
                      <Icon name="x" size={14} />Stop and hand in
                    </button>
                  </div>
                </div>
              ) : (
                <div className="lab-info done">
                  <Disc tone={isDone(attempt) ? "good" : "warn"} icon={isDone(attempt) ? "check" : "flag"} />
                  <div>
                    <b>{isDone(attempt) ? "Build complete!" : `Stopped with ${attempt.installed.length} of ${ORDER.length} parts in.`}</b>
                    <p>
                      {isDone(attempt)
                        ? (record.mistakes === 0 ? "Perfect build — no mistakes!" : `Finished with ${record.mistakes} mistake${record.mistakes === 1 ? "" : "s"}.`)
                        : `${record.mistakes} mistake${record.mistakes === 1 ? "" : "s"} in ${clock(record.duration_seconds)}.`}
                    </p>
                  </div>
                  <div className="lab-info-actions">
                    <button type="button" className="btn small primary" onClick={begin}>New Build</button>
                    <button type="button" className="btn small" disabled={Boolean(saved)} onClick={save}>
                      <Icon name="check" size={14} />{saved ? "Saved for marking" : "Save for marking"}
                    </button>
                    <a className="btn small" href={download} download={`${attempt.learnerId}.json`}>
                      <Icon name="download" size={14} />JSON
                    </a>
                  </div>
                </div>
              )}
            </div>

            <div className="lab-tray">
              <h3>Drag and drop components</h3>
              <ul className="tray-grid">
                {remaining.map((p) => (
                  <li key={p.id} className="tray-item">
                    <div
                      className={`part-card ${drag?.id === p.id ? "lifted" : ""} ${running ? "" : "idle"} ${focus?.step && p.id.toLowerCase() === String(focus.step).toLowerCase() ? "is-focus" : ""}`}
                      onPointerDown={(e) => startDrag(e, p.id)}
                      onPointerMove={moveDrag}
                      onPointerUp={endDrag}
                      onPointerCancel={() => setDrag(null)}
                    >
                      <img src={IMG(p.img)} alt="" draggable={false} />
                      <span>{p.name}</span>
                    </div>
                    <button type="button" className="btn small" disabled={!running} onClick={() => attemptPart(p.id, true)} aria-label={`Place ${p.name}`}>
                      Place
                    </button>
                    {onViewModel && (
                      <button type="button" className="btn small" onClick={() => onViewModel(p.id)}>
                        View model
                      </button>
                    )}
                  </li>
                ))}
                {remaining.length === 0 && <li className="empty-note">All parts installed</li>}
              </ul>
            </div>
          </div>

          {saved && (
            <details className="lab-log">
              <summary className="h-note">What the Marker will read</summary>
              <p className="worksheet">{saved.log}</p>
            </details>
          )}
        </>
      )}
      {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}

      {dragging && (
        <div className="drag-ghost" style={{ left: drag.x, top: drag.y }} aria-hidden="true">
          <img src={IMG(dragging.img)} alt="" />
        </div>
      )}
    </section>
  );
}
