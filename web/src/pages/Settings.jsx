import { useState } from "react";
import { saveProfile } from "../api.js";
import { signOut } from "../auth.js";
import { TEST_KEY, TEST_OFF, usePref } from "../prefs.js";
import { go } from "../router.js";
import { AGENT_ROLES, Av, Head, Ico, Switch, Tabs } from "./ui.jsx";

/** Profile, how the AI is reached, and the test-mode switches (off by default, never beside Start). */
export default function Settings({ state, tab = "test", auth, profile, onProfile, uploads }) {
  const [test, setTest] = usePref(TEST_KEY, TEST_OFF);
  const [name, setName] = useState(profile?.display_name || auth?.session?.user?.name || "");
  const [school, setSchool] = useState(profile?.school || auth?.session?.user?.school || "");
  const [saved, setSaved] = useState("");
  const llm = state?.llm || {};
  const offline = llm.name === "mock";
  const set = (k) => (v) => setTest({ ...test, [k]: v });

  async function save(e) {
    e.preventDefault();
    setSaved("");
    try {
      const out = await saveProfile({ display_name: name.trim(), school: school.trim() });
      onProfile(out.profile || { display_name: name.trim(), school: school.trim() });
      setSaved("Saved.");
    } catch (err) {
      setSaved(err.message);
    }
  }

  return (
    <div className="l-page">
      <Head title="Settings & test mode" sub="Your profile, how your colleague works, and tools for showing that it checks itself." />
      <Tabs label="Settings" value={tab} onChange={(t) => go("settings", { tab: t })} tabs={[["general", "General"], ["ai", "AI marking"], ["test", "Test mode"], ["agents", "About the agents"]]} />

      {tab === "general" && (
        <div className="l-row">
          <section className="l-card" style={{ flex: 1.4 }}>
            <div className="hd"><h2>Profile</h2></div>
            <div className="bd">
              {auth?.enabled && auth.session ? (
                <form onSubmit={save} style={{ display: "grid", gap: 12, maxWidth: 420 }}>
                  <div className="l-small l-muted">Signed in as <b style={{ color: "var(--ink)" }}>{auth.session.user.email}</b></div>
                  <label><span className="l-label">Your name, as learners see it</span><input className="l-field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ms Chili" /></label>
                  <label><span className="l-label">School</span><input className="l-field" value={school} onChange={(e) => setSchool(e.target.value)} /></label>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <button type="submit" className="l-btn p">Save</button>
                    <button type="button" className="l-btn danger" onClick={() => signOut()}>Sign out</button>
                    {saved && <span className="l-small l-muted">{saved}</span>}
                  </div>
                </form>
              ) : (
                <div className="l-muted">{auth?.enabled ? "You are trying LabLess without an account. Nothing you do is kept after you close the browser." : "Teacher accounts are not set up on this copy of LabLess, so everyone shares the sample class."}
                  {auth?.enabled && <div style={{ marginTop: 10 }}><button type="button" className="l-btn p" onClick={() => signOut()}>Sign in or create an account</button></div>}</div>
              )}
            </div>
          </section>
          <section className="l-card" style={{ flex: 1 }}>
            <div className="hd"><h2>This copy of LabLess</h2></div>
            <div className="bd l-small" style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 8 }}>
              <span className="l-muted">Class</span><b>Grade 12 CAT</b>
              <span className="l-muted">Uploads</span><b>{uploads ? "On" : "Off on this deployment"}</b>
              <span className="l-muted">Accounts</span><b>{auth?.enabled ? "On" : "Off"}</b>
              <span className="l-muted">Appearance</span><b>Light</b>
            </div>
          </section>
        </div>
      )}

      {tab === "ai" && (
        <section className="l-card" style={{ maxWidth: 640 }}>
          <div className="hd"><h2>AI marking</h2></div>
          <div className="bd l-small" style={{ display: "grid", gridTemplateColumns: "1fr auto", rowGap: 10 }}>
            <span className="l-muted">Status</span><span><span className={`l-dot ${offline ? "off" : ""}`} /> {offline ? (llm.switched ? "Offline backup took over" : "Offline mode") : "On"}</span>
            <span className="l-muted">Answering now</span><b>{offline ? "Offline demo marker" : `${llm.name === "gemini" ? "Gemini" : "OpenRouter"} (${llm.model})`}</b>
            <span className="l-muted">Backup</span><b>{llm.backup ? `OpenRouter (${llm.backup})` : offline ? "–" : "Offline demo marker"}</b>
            <span className="l-muted">Calls in the latest run</span><b>{llm.calls ?? 0}</b>
          </div>
          <div className="bd" style={{ borderTop: "1px solid var(--line2)" }}>
            <div className="l-callout">If the main model is busy or refuses a request, the backup takes over for the rest of that run. If no live model can answer, the offline demo marker finishes the run and the Activity log says so. A run is never lost to a busy model.</div>
          </div>
        </section>
      )}

      {tab === "test" && (
        <div className="l-row">
          <section className="l-card" style={{ flex: 1.4 }}>
            <div className="hd"><Ico name="shield" /><h2>Show how it checks itself</h2><span className="r"><span className="l-chip gr">For demos and training</span></span></div>
            <div className="l-list">
              <label className="it" style={{ cursor: "pointer" }}><Switch label="Plant a wrong mark" checked={test.fault} onChange={set("fault")} />
                <div className="grow"><div className="t">Plant a wrong mark</div><div className="d">Spoils one mark and one lesson exercise on purpose. The Reviewer should catch and fix them without being told.</div></div></label>
              <label className="it" style={{ cursor: "pointer" }}><Switch label="Plant a bad handwriting reading" checked={test.ocr} onChange={set("ocr")} disabled={!uploads} />
                <div className="grow"><div className="t">Plant a bad handwriting reading</div><div className="d">Deletes half of one transcript. The Clerk should notice and read the page again.{!uploads && " Needs handwritten scripts, which are off on this deployment."}</div></div></label>
              <label className="it" style={{ cursor: "pointer" }}><Switch label="Use the sample handwritten scripts" checked={test.sample} onChange={set("sample")} disabled={!uploads} />
                <div className="grow"><div className="t">Use the sample handwritten scripts</div><div className="d">When a run includes handwritten scripts and you have not added photos, the built-in photographed pages are used.</div></div></label>
            </div>
            <div className="bd" style={{ borderTop: "1px solid var(--line2)" }}>
              <div className="l-callout">While test mode is on, the top bar shows <span className="l-chip md">Test mode on</span>, each run is labelled, and planted faults are tagged <span className="l-chip md">Planted fault</span> in Checks. Nothing planted is sent to a learner.</div>
            </div>
          </section>
          <section className="l-card" style={{ flex: 1 }}>
            <div className="hd"><h2>What happens to a planted fault</h2></div>
            <div className="l-steps">
              {["The Marker marks as usual.", "One mark is changed after it is written. Nobody tells the Reviewer.", "The Reviewer marks again without seeing the first mark, and the attempt log is checked in code.", "The difference sends the mark back to the Marker once.", "If it is still wrong, it is held for you."].map((t, i) => (
                <div className="l-step" key={t}><span className="b">{i + 1}</span><div className="n" style={{ color: "var(--ink-2)" }}>{t}</div></div>
              ))}
            </div>
          </section>
        </div>
      )}

      {tab === "agents" && (
        <section className="l-card" style={{ maxWidth: 820 }}>
          <div className="hd"><h2>About the agents</h2><span className="r l-small l-muted">Seven colleagues, one plan: Plan → Do → Check → Correct → Deliver</span></div>
          <div className="l-list">{Object.entries(AGENT_ROLES).map(([k, [n, role, d]]) => <div className="it" key={k}><Av name={n} /><div className="grow"><div className="t">{n} <span className="l-muted" style={{ fontWeight: 400 }}>· {role}</span></div><div className="d">{d}</div></div></div>)}</div>
          <div className="bd" style={{ borderTop: "1px solid var(--line2)" }}><div className="l-callout">The risk score is worked out by fixed rules in code, not by the AI, so every score can show its reason and is the same every time.</div></div>
        </section>
      )}
    </div>
  );
}
