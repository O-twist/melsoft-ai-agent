import { useCallback, useEffect, useState } from "react";

/**
 * Teacher accounts, with Supabase Auth over its REST API (no SDK).
 *
 * The browser asks the server for the Supabase URL and the anon key at runtime (GET /api/config), so one
 * build works on any deployment. The anon key is public by design; the service role key is never sent here.
 * When the server has no Supabase settings, accounts are switched off and LabLess opens straight away.
 */
const SESSION_KEY = "lablest.session";
let config = null;
let session = null;

function load() {
  try {
    return JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
  } catch {
    return null;
  }
}

function save(next) {
  session = next;
  try {
    if (next) localStorage.setItem(SESSION_KEY, JSON.stringify(next));
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    // The session still holds for this visit.
  }
  window.dispatchEvent(new Event("lablest-auth"));
}

session = load();

/** Every same-origin /api call carries the teacher's token, so the server can act as that teacher. */
const plainFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const url = typeof input === "string" ? input : input?.url || "";
  if (session?.access_token && (url.startsWith("/api/") || url.startsWith(`${window.location.origin}/api/`))) {
    const headers = new Headers(init.headers || (typeof input !== "string" ? input.headers : undefined));
    if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${session.access_token}`);
    return plainFetch(input, { ...init, headers });
  }
  return plainFetch(input, init);
};

export async function getConfig() {
  if (config) return config;
  try {
    const res = await plainFetch("/api/config");
    config = res.ok ? await res.json() : { auth: false };
  } catch {
    config = { auth: false };
  }
  return config;
}

async function call(path, body, token) {
  const cfg = await getConfig();
  let res;
  try {
    res = await plainFetch(`${cfg.supabase_url}/auth/v1/${path}`, {
      method: "POST",
      headers: { apikey: cfg.anon_key, "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new Error("Cannot reach the sign-in service. Check the internet connection and try again.");
  }
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(friendly(json.error_description || json.msg || json.message || json.error || ""));
  return json;
}

function friendly(text) {
  const t = String(text).toLowerCase();
  if (t.includes("invalid login")) return "That email and password do not match an account.";
  if (t.includes("email not confirmed")) return "Confirm your email address first: open the link we sent you.";
  if (t.includes("already registered") || t.includes("already been registered")) return "There is already an account with this email. Log in instead.";
  if (t.includes("password") && t.includes("6")) return "Use a password of at least 6 characters.";
  if (t.includes("rate limit")) return "Too many attempts. Wait a minute and try again.";
  return text || "That did not work. Try again.";
}

function keep(json) {
  if (!json?.access_token) return null;
  const next = {
    access_token: json.access_token, refresh_token: json.refresh_token,
    expires_at: Date.now() + (json.expires_in || 3600) * 1000,
    user: { id: json.user?.id, email: json.user?.email, name: json.user?.user_metadata?.display_name || "", school: json.user?.user_metadata?.school || "" },
  };
  save(next);
  return next;
}

/** Returns the session, or null when the project asks new teachers to confirm their email first. */
export async function signUp({ email, password, name, school }) {
  const json = await call("signup", { email, password, data: { display_name: name, school } });
  return keep(json);
}

export async function signIn({ email, password }) {
  return keep(await call("token?grant_type=password", { email, password }));
}

export async function sendReset(email) {
  await call("recover", { email });
}

export async function signOut() {
  const token = session?.access_token;
  save(null);
  if (token) call("logout", {}, token).catch(() => {});
}

async function refresh() {
  if (!session?.refresh_token) return null;
  try {
    return keep(await call("token?grant_type=refresh_token", { refresh_token: session.refresh_token }));
  } catch {
    save(null);
    return null;
  }
}

/** { ready, enabled, session } plus a guest mode for the offline demo when accounts cannot be reached. */
export function useAuth() {
  const [state, setState] = useState({ ready: false, enabled: false, session });
  const sync = useCallback(() => setState((s) => ({ ...s, session })), []);
  useEffect(() => {
    let alive = true;
    (async () => {
      const cfg = await getConfig();
      if (session && session.expires_at - Date.now() < 5 * 60 * 1000) await refresh();
      if (alive) setState({ ready: true, enabled: Boolean(cfg.auth), session });
    })();
    window.addEventListener("lablest-auth", sync);
    const timer = setInterval(() => {
      if (session && session.expires_at - Date.now() < 5 * 60 * 1000) refresh();
    }, 60 * 1000);
    return () => {
      alive = false;
      window.removeEventListener("lablest-auth", sync);
      clearInterval(timer);
    };
  }, [sync]);
  return state;
}
