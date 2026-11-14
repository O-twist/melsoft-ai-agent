import { useEffect, useState } from "react";
import { listLiveAttempts } from "../api.js";
import PCAssembly from "../components/PCAssembly.jsx";
import PartModels from "../components/PartModels.jsx";
import WindowsStation from "../components/WindowsStation.jsx";
import { go } from "../router.js";
import { Empty, Head, Tabs } from "./ui.jsx";

/** Practical work in the browser: the PC build, 3D parts and Windows tasks, each on its own tab. */
export default function Lab({ state, query, onChanged }) {
  const tab = query.tab || "pc";
  const [attempts, setAttempts] = useState(null);
  const [nonce] = useState(() => Date.now());
  useEffect(() => {
    if (tab === "attempts") listLiveAttempts().then(setAttempts).catch(() => setAttempts([]));
  }, [tab]);
  const subs = state?.subs || [];
  const names = Object.fromEntries(subs.map((s) => [s.id, s.learner]));
  const set = (next) => go("lab", { tab: next, learner: query.learner });
  const focus = query.step || query.learner ? { learnerId: query.learner, step: query.step, nonce: query.n || nonce } : null;

  return (
    <div className="l-page">
      <Head title="Lab" sub="Practical work learners do in the browser. Finished attempts feed straight into marking and the Learners page." />
      <Tabs label="Lab" value={tab} onChange={set} tabs={[["pc", "PC assembly"], ["parts", "3D parts"], ["windows", "Windows tasks"], ["attempts", "Attempts", attempts ? attempts.length : null]]} />
      {tab === "pc" && <div className="l-embed"><PCAssembly subs={subs} focus={focus} onViewModel={(id) => go("lab", { tab: "parts", part: id, learner: query.learner })} /></div>}
      {tab === "parts" && <div className="l-embed"><PartModels part={query.part || "pc"} nonce={query.n || nonce} /></div>}
      {tab === "windows" && <div className="l-embed"><WindowsStation subs={subs} focus={query.task || query.learner ? { learnerId: query.learner, target: query.task, nonce: query.n || nonce } : null} onSaved={onChanged} /></div>}
      {tab === "attempts" && (
        !attempts ? <div className="l-muted">Loading…</div> : attempts.length === 0 ? (
          <Empty title="No attempts saved from the lab yet" action={<button type="button" className="l-btn p" onClick={() => set("pc")}>Open the PC assembly</button>}>
            The sample class's attempts are already on file. Builds saved here are used in the next practical run.
          </Empty>
        ) : (
          <section className="l-card"><div className="l-list">
            {attempts.map((a) => (
              <div className="it" key={a.learner_id}><div className="grow"><div className="t">{names[a.learner_id] || a.learner_id}</div><div className="d">Saved {new Date(a.saved * 1000).toLocaleString("en-ZA")}</div></div><span className="r"><span className="l-chip ok">Used in the next practical run</span></span></div>
            ))}
          </div></section>
        )
      )}
    </div>
  );
}
