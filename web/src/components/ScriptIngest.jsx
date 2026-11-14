import { useRef, useState } from "react";
import { pageUrl, samplePages, uploadPages } from "../api.js";
import Icon from "./Icon.jsx";
import { Disc } from "./Badge.jsx";
import CameraCapture from "./CameraCapture.jsx";
import { plural } from "../format.js";

/**
 * Photos of handwritten scripts, before a run. The teacher adds photos (or the samples), puts them in order and
 * removes any that should not be read. The photos are kept on the server as they arrive; the order chosen here
 * is sent with the goal. The Planner then decides whether the Clerk needs to read them.
 *
 * scripts: { batch, pages: [{ id, original }] } in reading order, or null.
 */
export default function ScriptIngest({ scripts, onScripts, injectOcrFault, onInjectOcrFault, running }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [over, setOver] = useState(false);
  const [camera, setCamera] = useState(false);
  const picker = useRef(null);
  const pages = scripts?.pages || [];

  async function add(promise) {
    setBusy(true);
    setError("");
    try {
      const { batch, pages: kept } = await promise;
      // The server returns every page in the batch; keep the teacher's order and put new pages at the end.
      const known = new Set(pages.map((p) => p.id));
      const fresh = kept.filter((p) => !known.has(p.id));
      onScripts({ batch, pages: batch === scripts?.batch ? [...pages, ...fresh] : kept });
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const addFiles = (files) => files.length && add(uploadPages(files, scripts?.batch));
  const move = (i, by) => {
    const next = [...pages];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    onScripts({ ...scripts, pages: next });
  };
  const remove = (i) => {
    const next = pages.filter((_, j) => j !== i);
    onScripts(next.length ? { ...scripts, pages: next } : null);
  };
  const locked = running || busy;

  return (
    <section className="card">
      <div className="ingest-head">
        <header className="card-head" style={{ marginBottom: 0 }}>
          <div>
            <h2>Handwritten scripts <span className="h-note">optional</span></h2>
            <p>
              Add photos of handwritten pages and the Clerk transcribes them, matches each name to the class list and
              checks the page numbers. A page that fails a check is read again; one that still fails waits for you.
            </p>
          </div>
        </header>
        <div className="ingest-actions">
          <button type="button" className="btn small" disabled={locked} onClick={() => add(samplePages())}>
            <Icon name="zap" size={14} />Use the sample scripts
          </button>
          <button type="button" className="btn small" disabled={locked} onClick={() => picker.current?.click()}>
            <Icon name="download" size={14} className="flip" />Add photos
          </button>
          <button type="button" className="btn small" disabled={locked} onClick={() => setCamera(true)}>
            <Icon name="camera" size={14} />Take photos
          </button>
          <input
            ref={picker}
            type="file"
            accept="image/jpeg,image/png"
            multiple
            hidden
            onChange={(e) => {
              addFiles([...e.target.files]);
              e.target.value = "";
            }}
          />
        </div>
      </div>

      {pages.length === 0 ? (
        <div
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            if (!locked) setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            if (!locked) addFiles([...e.dataTransfer.files]);
          }}
        >
          {busy ? "Uploading…" : (
            <>
              Drop JPEG or PNG photos here, one page per photo, or{" "}
              <button type="button" className="link-btn" disabled={locked} onClick={() => setCamera(true)}>take them with your camera</button>.
              Without photos, the typed essays on file are marked.
            </>
          )}
        </div>
      ) : (
        <>
          <ol className="thumbs a-CL" aria-label="Pages in reading order">
            {pages.map((p, i) => (
              <li className="thumb" key={p.id}>
                <img src={pageUrl(scripts.batch, p.id)} alt={`Page ${i + 1}: ${p.original}`} loading="lazy" />
                <span className="thumb-n">{i + 1}</span>
                <span className="thumb-name" title={p.original}>{p.original}</span>
                <span className="thumb-tools">
                  <button type="button" className="icon-btn" disabled={locked || i === 0} onClick={() => move(i, -1)} aria-label={`Move ${p.original} earlier`}>
                    <Icon name="arrow" size={15} className="flip" />
                  </button>
                  <button type="button" className="icon-btn" disabled={locked} onClick={() => remove(i)} aria-label={`Leave out ${p.original}`}>
                    <Icon name="x" size={15} />
                  </button>
                  <button type="button" className="icon-btn" disabled={locked || i === pages.length - 1} onClick={() => move(i, 1)} aria-label={`Move ${p.original} later`}>
                    <Icon name="arrow" size={15} />
                  </button>
                </span>
              </li>
            ))}
          </ol>
          <div className="ingest-foot">
            <p>
              {plural(pages.length, "page")} will be read in this order. Pages of one script can be in any order: the
              Clerk sorts them by the page numbers written on them.
            </p>
            <div className="ingest-actions">
              {onInjectOcrFault && (
                <label className="switch">
                  <input type="checkbox" checked={injectOcrFault} disabled={running} onChange={(e) => onInjectOcrFault(e.target.checked)} />
                  <span className="switch-track" />
                  <span className="switch-text">
                    Inject an OCR fault
                    <small>Deletes half a transcript; the Clerk must notice</small>
                  </span>
                </label>
              )}
              <button type="button" className="btn small" disabled={locked} onClick={() => onScripts(null)}>
                <Icon name="x" size={14} />Clear
              </button>
            </div>
          </div>
        </>
      )}
      {error && <p className="form-error" role="alert"><Disc tone="critical" icon="alert" />{error}</p>}
      {camera && <CameraCapture onPhotos={addFiles} onClose={() => setCamera(false)} />}
    </section>
  );
}
