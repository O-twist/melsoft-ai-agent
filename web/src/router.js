import { useEffect, useState } from "react";

/**
 * Pages live in the URL hash (#/learners/E10?tab=essay), so a refresh or a shared link opens the same page
 * on any host, with no server rewrites needed.
 */
export function parse(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, qs = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(qs));
  return { page: parts[0] || "today", parts, query };
}

export function useRoute() {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

/** Go to a page: go("learners", "E10", { tab: "essay" }). */
export function go(...args) {
  const query = args.length && typeof args[args.length - 1] === "object" ? args.pop() : null;
  const qs = query ? new URLSearchParams(Object.fromEntries(Object.entries(query).filter(([, v]) => v != null && v !== ""))).toString() : "";
  const next = `#/${args.map((a) => encodeURIComponent(String(a))).join("/")}${qs ? `?${qs}` : ""}`;
  if (window.location.hash !== next) window.location.hash = next;
}

export const href = (...args) => {
  const query = args.length && typeof args[args.length - 1] === "object" ? args.pop() : null;
  const qs = query ? new URLSearchParams(query).toString() : "";
  return `#/${args.join("/")}${qs ? `?${qs}` : ""}`;
};
