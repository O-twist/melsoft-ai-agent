import { useEffect, useState } from "react";

/**
 * A 3D PC to turn and zoom, for the practical's lesson. <model-viewer> is bundled with the dashboard and the
 * model is a local file (web/public/models), so it works with no internet. The library is loaded only when
 * this view is shown, so essay runs never download it.
 */
export default function ModelViewer() {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    import("@google/model-viewer")
      .then(() => alive && setReady(true))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <figure className="model">
      {failed ? (
        <p className="empty-note">The 3D viewer could not be loaded in this browser.</p>
      ) : ready ? (
        <model-viewer
          src="/models/personal_computer.glb"
          alt="A 3D model of a desktop PC that can be turned and zoomed"
          camera-controls=""
          auto-rotate=""
          touch-action="pan-y"
          shadow-intensity="0.8"
          exposure="1"
          style={{ width: "100%", height: "320px", background: "transparent" }}
        />
      ) : (
        <p className="empty-note">Loading the 3D model…</p>
      )}
      <figcaption>
        Drag to turn the PC, scroll or pinch to zoom. Model: “Personal_computer” by{" "}
        <a href="https://sketchfab.com/alessiaspedicati" target="_blank" rel="noreferrer">alessiaspedicati</a>,{" "}
        <a href="http://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
      </figcaption>
    </figure>
  );
}
