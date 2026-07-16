import { useEffect, useState } from "react";

// Categorical slots 1-3 from the dataviz reference palette (fixed order, not cycled).
const LIGHT = { blue: "#2a78d6", green: "#008300", magenta: "#e87ba4", muted: "#898781", grid: "#e1e0d9" };
const DARK = { blue: "#3987e5", green: "#008300", magenta: "#d55181", muted: "#898781", grid: "#2c2c2a" };

export function useIsDark(): boolean {
  const [isDark, setIsDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mql.addEventListener("change", listener);
    return () => mql.removeEventListener("change", listener);
  }, []);
  return isDark;
}

export function usePalette() {
  return useIsDark() ? DARK : LIGHT;
}
