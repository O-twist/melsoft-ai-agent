import { useCallback, useEffect, useState } from "react";

/** Small things this browser remembers: test mode switches, dismissed notices and the list of runs. */
function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private windows may refuse storage; the setting still holds for this visit.
  }
  window.dispatchEvent(new CustomEvent("lablest-pref", { detail: key }));
}

/** A remembered value that every component using the same key sees change at once. */
export function usePref(key, fallback) {
  const [value, setValue] = useState(() => read(key, fallback));
  useEffect(() => {
    const on = (e) => {
      if (!e.detail || e.detail === key) setValue(read(key, fallback));
    };
    window.addEventListener("lablest-pref", on);
    return () => window.removeEventListener("lablest-pref", on);
    // fallback is a literal at each call site
  }, [key]);
  const set = useCallback((next) => write(key, typeof next === "function" ? next(read(key, fallback)) : next), [key]);
  return [value, set];
}

export const TEST_KEY = "lablest.test";
export const TEST_OFF = { fault: false, ocr: false, sample: false };
export const RUNS_KEY = "lablest.history";
export const SEEN_KEY = "lablest.seen";

/** Keep a finished run in this browser's history (newest first, at most 30). */
export function remember(summary) {
  if (!summary?.id) return;
  const list = read(RUNS_KEY, []).filter((r) => r.id !== summary.id);
  write(RUNS_KEY, [summary, ...list].slice(0, 30));
}
