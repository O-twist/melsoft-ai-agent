import { useState } from "react";
import { sendReset, signIn, signUp } from "../auth.js";

/** Sign up, log in, forgot password and "check your email". Clean and centred, no marketing. */
export default function Auth({ onGuest }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", school: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await signIn(form);
      else if (mode === "signup") {
        const session = await signUp(form);
        if (!session) setMode("check");
      } else if (mode === "forgot") {
        await sendReset(form.email);
        setNote("If there is an account for that email, a reset link is on its way.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const brand = (
    <div className="brand"><span className="l-logo" style={{ width: 34, height: 34, borderRadius: 9, background: "#041B3A", color: "#fff", display: "grid", placeItems: "center", fontWeight: 700 }}>L</span>
      <div><b style={{ display: "block" }}>LabLess</b><small style={{ color: "#5F6779" }}>Teaching colleague</small></div></div>
  );

  return (
    <div className="l-auth l-app" style={{ display: "grid", height: "auto", minHeight: "100vh" }}>
      <div className="box">
        {brand}
        {mode === "check" ? (
          <>
            <h1>Check your email</h1>
            <p style={{ color: "#4A5568" }}>We sent a link to <b>{form.email}</b>. Open it to confirm your account, then come back and log in.</p>
            <div className="alt"><button type="button" className="l-link" onClick={() => setMode("login")}>Back to log in</button></div>
          </>
        ) : (
          <>
            <h1>{mode === "login" ? "Log in" : mode === "signup" ? "Create your teacher account" : "Reset your password"}</h1>
            <p style={{ color: "#5F6779", fontSize: 13.5 }}>{mode === "signup" ? "Your classes and runs are kept private to your account." : mode === "forgot" ? "We will email you a link to choose a new password." : "Welcome back."}</p>
            <form onSubmit={submit}>
              {mode === "signup" && <>
                <label><span className="l-label">Your name, as learners see it</span><input className="l-field" required value={form.name} onChange={set("name")} placeholder="Ms Chili" autoComplete="name" /></label>
                <label><span className="l-label">School (optional)</span><input className="l-field" value={form.school} onChange={set("school")} /></label>
              </>}
              <label><span className="l-label">Email</span><input className="l-field" type="email" required value={form.email} onChange={set("email")} autoComplete="email" /></label>
              {mode !== "forgot" && <label><span className="l-label">Password</span><input className="l-field" type="password" required minLength={6} value={form.password} onChange={set("password")} autoComplete={mode === "signup" ? "new-password" : "current-password"} /></label>}
              {error && <p className="l-error" role="alert" style={{ margin: 0 }}>{error}</p>}
              {note && <p className="l-small" role="status" style={{ margin: 0, color: "#1C6B55" }}>{note}</p>}
              <button type="submit" className="l-btn p lg" disabled={busy}>{busy ? "One moment…" : mode === "login" ? "Log in" : mode === "signup" ? "Create account" : "Send the link"}</button>
            </form>
            <div className="alt">
              {mode === "login" ? <>
                <button type="button" className="l-link" onClick={() => { setMode("signup"); setError(""); }}>Create an account</button>
                <button type="button" className="l-link" onClick={() => { setMode("forgot"); setError(""); }}>Forgot password?</button>
              </> : <button type="button" className="l-link" onClick={() => { setMode("login"); setError(""); setNote(""); }}>I already have an account</button>}
            </div>
          </>
        )}
        <div style={{ borderTop: "1px solid #E5E7EB", marginTop: 18, paddingTop: 14, fontSize: 13, color: "#5F6779" }}>
          Just looking? <button type="button" className="l-link" onClick={onGuest}>Try the sample class without an account</button>
        </div>
      </div>
    </div>
  );
}
