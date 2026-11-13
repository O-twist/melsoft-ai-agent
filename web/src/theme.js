import { useState } from "react";

/**
 * Light or dark. index.html sets the starting theme before first paint (saved choice, else the
 * system setting); this hook flips it and remembers the choice.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || "light");

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("mc-theme", next);
    } catch {
      // Private windows may refuse storage; the theme still changes for this visit.
    }
    setTheme(next);
  }

  return [theme, toggle];
}
