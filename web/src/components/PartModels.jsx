import { useEffect, useState } from "react";
import ModelViewer from "./ModelViewer.jsx";

/**
 * CompuClass per-part viewers, as web embeds.
 * The Sketchfab URLs are the ones in Channel-Zero/Compuclass-v1.5
 * (components/RamAR.js, CPUAR.js, GPUAR.js, PSUAR.js, MotherboardAR.js, StorageAR.js).
 * lutho_branch uses the same model ids. RealAR.js is the whole PC; that file is already
 * local (web/public/models/personal_computer.glb), so it is not loaded from GitHub.
 * If a Sketchfab embed cannot be reached, the local CC BY 4.0 PC is shown instead.
 */
export const PART_MODELS = [
  {
    id: "pc",
    name: "Personal computer",
    source: "RealAR.js",
    localOnly: true,
  },
  {
    id: "motherboard",
    name: "Motherboard",
    source: "MotherboardAR.js",
    uid: "116bdcff94174764a4783164ca57f8e7",
    title: "Motherboard",
    author: "MaaB",
    authorUrl: "https://sketchfab.com/MaaB",
    modelUrl: "https://sketchfab.com/3d-models/motherboard-116bdcff94174764a4783164ca57f8e7",
    loading: "Loading Motherboard Model...",
  },
  {
    id: "cpu",
    name: "CPU",
    source: "CPUAR.js",
    uid: "a50bafa2d9914caa9bf185cd16e6935f",
    title: "3D PBR Quantum GenX3 Processor / CPU (Imaginary)",
    author: "Mustafa Özgen",
    authorUrl: "https://sketchfab.com/mustafaozgen",
    modelUrl: "https://sketchfab.com/3d-models/3d-pbr-quantum-genx3-processor-cpu-imaginary-a50bafa2d9914caa9bf185cd16e6935f",
    loading: "Loading CPU Model...",
  },
  {
    id: "ram",
    name: "RAM",
    source: "RamAR.js",
    uid: "ab2b1c25c31b44c1a757911734bdf942",
    title: "Random Access Memory - RAM Stick - PC",
    author: "Diego G.",
    authorUrl: "https://sketchfab.com/empty_mirror",
    modelUrl: "https://sketchfab.com/3d-models/random-access-memory-ram-stick-pc-ab2b1c25c31b44c1a757911734bdf942",
    loading: "Loading RAM Model...",
  },
  {
    id: "gpu",
    name: "Graphics Card",
    source: "GPUAR.js",
    uid: "6f527569f14b4efc94c7072842bd41ac",
    title: "Asus ROG Geforce RTX 4090 v2.0",
    author: "MajdyModels",
    authorUrl: "https://sketchfab.com/MG990",
    modelUrl: "https://sketchfab.com/3d-models/asus-rog-geforce-rtx-4090-v20-6f527569f14b4efc94c7072842bd41ac",
    loading: "Loading GPU Model...",
  },
  {
    id: "ssd",
    name: "SSD",
    source: "StorageAR.js",
    uid: "dc92372c89f54d82ab378599d3170065",
    title: "(SSD) Solid State Drive",
    author: "MarkCP",
    authorUrl: "https://sketchfab.com/MarkCP",
    modelUrl: "https://sketchfab.com/3d-models/ssd-solid-state-drive-dc92372c89f54d82ab378599d3170065",
    loading: "Loading SSD Model...",
  },
  {
    id: "psu",
    name: "Power Supply",
    source: "PSUAR.js",
    uid: "02db33d66a784c82a6202a3ec6850498",
    title: "Power Supply - Basic",
    author: "Up1x",
    authorUrl: "https://sketchfab.com/alexlh2003",
    modelUrl: "https://sketchfab.com/3d-models/power-supply-basic-02db33d66a784c82a6202a3ec6850498",
    loading: "Loading PSU Model...",
  },
];

const BY_ID = Object.fromEntries(PART_MODELS.map((model) => [model.id, model]));

export function partModel(id) {
  return BY_ID[String(id || "pc").toLowerCase()] || BY_ID.pc;
}

function embedUrl(uid) {
  return `https://sketchfab.com/models/${uid}/embed?autostart=1&ui_controls=1&ui_infos=0&ui_inspector=0&ui_stop=0&ui_watermark=0`;
}

function SketchfabCredit({ model }) {
  if (!model.uid) {
    return (
      <figcaption>
        Personal Computer - 3D View. Drag to rotate, pinch or scroll to zoom. Model: “Personal_computer” by{" "}
        <a href="https://sketchfab.com/alessiaspedicati" target="_blank" rel="noreferrer">alessiaspedicati</a>,{" "}
        <a href="http://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
      </figcaption>
    );
  }
  return (
    <figcaption>
      “{model.title}” by <a href={model.authorUrl} target="_blank" rel="noreferrer">{model.author}</a> on{" "}
      <a href={model.modelUrl} target="_blank" rel="noreferrer">Sketchfab</a>,{" "}
      <a href="http://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
    </figcaption>
  );
}

export default function PartModels({ part, nonce }) {
  const [id, setId] = useState(partModel(part).id);
  const [mode, setMode] = useState("sketchfab");
  const model = partModel(id);

  useEffect(() => {
    if (part) setId(partModel(part).id);
  }, [part, nonce]);

  useEffect(() => {
    if (model.localOnly) {
      setMode("local");
      return undefined;
    }
    let alive = true;
    setMode("sketchfab");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    fetch(`https://api.sketchfab.com/v3/models/${model.uid}`, { signal: controller.signal })
      .then((response) => {
        if (alive && !response.ok) setMode("local");
      })
      .catch(() => {
        if (alive) setMode("local");
      })
      .finally(() => clearTimeout(timer));
    return () => {
      alive = false;
      controller.abort();
    };
  }, [model.uid, model.localOnly, nonce]);

  return (
    <section className="card" id="part-viewer">
      <header className="card-head">
        <div>
          <h2>3D parts</h2>
          <p>One 3D model for each part. Drag to rotate, pinch or scroll to zoom. If a model cannot load, the offline PC is shown instead.</p>
        </div>
      </header>
      <div className="part-switch" role="group" aria-label="Which 3D part">
        {PART_MODELS.map((item) => (
          <button key={item.id} type="button" className={`btn small ${item.id === model.id ? "primary" : ""}`} aria-pressed={item.id === model.id} onClick={() => setId(item.id)}>
            {item.name}
          </button>
        ))}
      </div>
      <figure className="model">
        {mode === "sketchfab" && model.uid ? (
          <iframe className="sketch-frame" title={model.loading} src={embedUrl(model.uid)} allow="autoplay; fullscreen; xr-spatial-tracking" allowFullScreen />
        ) : (
          <>
            {model.uid && <p className="rescue-note">The Sketchfab model did not load, so this is the offline PC, aimed at the {model.name}.</p>}
            <ModelViewer part={model.id === "pc" ? "" : model.id} />
          </>
        )}
        <SketchfabCredit model={model} />
        {model.uid && (
          <p className="no-print">
            <button type="button" className="btn small" onClick={() => setMode((current) => (current === "sketchfab" ? "local" : "sketchfab"))}>
              {mode === "sketchfab" ? "Show the offline PC" : "Show the Sketchfab model"}
            </button>
          </p>
        )}
      </figure>
    </section>
  );
}
