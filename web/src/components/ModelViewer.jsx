import { useEffect, useState } from "react";

const PARTS = {
  ram: { label: "RAM", orbit: "28deg 68deg 115%", img: "ram.png" },
  cpu: { label: "CPU", orbit: "8deg 58deg 95%", img: "cpu.png" },
  motherboard: { label: "motherboard", orbit: "18deg 78deg 130%", img: "motherboard.png" },
  gpu: { label: "graphics card", orbit: "-32deg 80deg 110%", img: "gpu.png" },
  ssd: { label: "SSD", orbit: "64deg 72deg 100%", img: "ssd.png" },
  psu: { label: "power supply", orbit: "12deg 100deg 115%", img: "psu.png" },
};

/**
 * A 3D PC to turn and zoom. <model-viewer> is bundled with the dashboard and the
 * model is a local file (web/public/models), so it works with no internet. The library is loaded only when
 * this view is shown. `part` aims the camera and names that component, for a catch-up link.
 */
export default function ModelViewer({ part }) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const focus = PARTS[(part || "").toLowerCase()] || null;

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
      {focus && (
        <p className="model-focus">
          <img src={`/pc-assembly/${focus.img}`} alt="" />
          <span>Focused on the {focus.label}</span>
        </p>
      )}
      {failed ? (
        <p className="empty-note">The 3D viewer could not be loaded in this browser.</p>
      ) : ready ? (
        <model-viewer
          key={focus ? focus.label : "pc"}
          src="/models/personal_computer.glb"
          alt={focus ? `A 3D model of a desktop PC, focused on the ${focus.label}` : "A 3D model of a desktop PC that can be turned and zoomed"}
          camera-controls=""
          auto-rotate={focus ? undefined : ""}
          camera-orbit={focus ? focus.orbit : "auto auto auto"}
          touch-action="pan-y"
          shadow-intensity="0.8"
          exposure="1"
          style={{ width: "100%", height: "320px", background: "transparent" }}
        />
      ) : (
        <p className="empty-note">Loading the 3D model…</p>
      )}
      <figcaption>
        {focus ? `Focused on the ${focus.label}. ` : ""}
        Drag to turn the PC, scroll or pinch to zoom. Model: “Personal_computer” by{" "}
        <a href="https://sketchfab.com/alessiaspedicati" target="_blank" rel="noreferrer">alessiaspedicati</a>,{" "}
        <a href="http://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
      </figcaption>
    </figure>
  );
}
