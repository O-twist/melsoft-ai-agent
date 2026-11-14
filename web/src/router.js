import { useCallback, useEffect, useState } from "react";

/**
 * A hash router, so every page has its own URL (#/learners) and a reload or a deep link lands
 * back where the teacher was. A hash is used deliberately: the Python server serves one page and
 * knows nothing about these routes, so nothing on the server has to change.
 */
export const PAGES = ["today", "new", "runs", "run", "learners", "classes", "lab", "messages", "settings"];

function read() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const page = path.split("/")[0] || "today";
  return {
    page: PAGES.includes(page) ? page : "today",
    params: Object.fromEntries(new URLSearchParams(query || "")),
  };
}

export function useRoute() {
  const [route, setRoute] = useState(read);

  useEffect(() => {
    const onChange = () => setRoute(read());
    window.addEventListener("hashchange", onChange);
    if (!window.location.hash) window.location.replace("#/today");
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const go = useCallback((page, params = {}) => {
    const query = new URLSearchParams(params).toString();
    window.location.hash = `#/${page}${query ? `?${query}` : ""}`;
    // The page changed under the teacher, so start them at the top of the new one.
    requestAnimationFrame(() => document.querySelector(".page-body")?.scrollTo({ top: 0 }));
  }, []);

  return [route, go];
}
