import { useEffect, useRef, useState } from "react";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import { plural } from "../format.js";

/**
 * Take photos of handwritten pages with the device's camera, for a teacher who has no photos to upload.
 * Each shot becomes a JPEG page, handed to onPhotos as Files when the teacher is done. The camera is switched
 * off as soon as the dialog closes.
 *
 * Browsers only give a page the camera on localhost or https. Where the live camera is not available, the
 * dialog offers the device's own camera app instead (on a phone, a file input with capture opens it).
 */
export default function CameraCapture({ onPhotos, onClose }) {
  const video = useRef(null);
  const fallback = useRef(null);
  const [stream, setStream] = useState(null);
  const [shots, setShots] = useState([]); // [{ file, url }]
  const [problem, setProblem] = useState("");
  const [flash, setFlash] = useState(false);

  // Start the camera, the one facing away from the teacher where there is a choice.
  useEffect(() => {
    let live = null;
    let cancelled = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      setProblem("This browser cannot open the camera from the page. Use your device's camera app instead.");
      return undefined;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false })
      .then((s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        live = s;
        setStream(s);
      })
      .catch((e) => {
        setProblem(
          e?.name === "NotAllowedError"
            ? "Camera access was refused. Allow the camera for this site in the browser, or use your device's camera app."
            : "No camera could be opened. Use your device's camera app instead, or add photos from files.",
        );
      });
    return () => {
      cancelled = true;
      live?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (video.current && stream) video.current.srcObject = stream;
  }, [stream]);

  // Free the previews' memory when the dialog goes away.
  useEffect(() => () => shots.forEach((s) => URL.revokeObjectURL(s.url)), []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function snap() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d").drawImage(v, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const n = shots.length + 1;
        const file = new File([blob], `camera-page-${String(n).padStart(2, "0")}.jpg`, { type: "image/jpeg" });
        setShots((prev) => [...prev, { file, url: URL.createObjectURL(blob) }]);
        setFlash(true);
        setTimeout(() => setFlash(false), 150);
      },
      "image/jpeg",
      0.9,
    );
  }

  function drop(i) {
    URL.revokeObjectURL(shots[i].url);
    setShots((prev) => prev.filter((_, j) => j !== i));
  }

  function done() {
    if (shots.length) onPhotos(shots.map((s) => s.file));
    onClose();
  }

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="camera" role="dialog" aria-modal="true" aria-label="Take photos of handwritten pages">
        <header className="camera-head">
          <div>
            <h2>Take photos of the scripts</h2>
            <p>One page per photo, flat and well lit, with the learner's name and page number in view.</p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close the camera">
            <Icon name="x" size={16} />
          </button>
        </header>

        {problem ? (
          <div className="camera-problem">
            <p><Disc tone="serious" icon="alert" />{problem}</p>
            <button type="button" className="btn small" onClick={() => fallback.current?.click()}>
              <Icon name="camera" size={14} />Open the camera app
            </button>
            <input
              ref={fallback}
              type="file"
              accept="image/jpeg,image/png"
              capture="environment"
              hidden
              onChange={(e) => {
                const files = [...e.target.files];
                e.target.value = "";
                if (files.length) {
                  onPhotos(files);
                  onClose();
                }
              }}
            />
          </div>
        ) : (
          <div className={`camera-view ${flash ? "flash" : ""}`}>
            <video ref={video} autoPlay playsInline muted />
            {!stream && <span className="camera-wait">Starting the camera…</span>}
          </div>
        )}

        {shots.length > 0 && (
          <ol className="camera-shots" aria-label="Photos taken">
            {shots.map((s, i) => (
              <li key={s.url}>
                <img src={s.url} alt={`Photo ${i + 1}`} />
                <button type="button" className="icon-btn" onClick={() => drop(i)} aria-label={`Remove photo ${i + 1}`}>
                  <Icon name="x" size={13} />
                </button>
              </li>
            ))}
          </ol>
        )}

        <footer className="camera-foot">
          <span>{shots.length ? `${plural(shots.length, "page")} taken` : "No pages taken yet"}</span>
          <div className="camera-actions">
            {!problem && (
              <button type="button" className="btn" disabled={!stream} onClick={snap}>
                <Icon name="camera" size={15} />Take photo
              </button>
            )}
            <button type="button" className="btn primary" disabled={!shots.length} onClick={done}>
              <Icon name="check" size={15} />Use {shots.length ? plural(shots.length, "photo") : "photos"}
            </button>
          </div>
        </footer>
      </div>
    </>
  );
}
