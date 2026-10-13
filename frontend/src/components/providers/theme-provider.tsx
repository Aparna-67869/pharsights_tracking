"use client";

import * as React from "react";

export type Theme = "dark" | "light" | "hc";

interface ThemeContextValue {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  /** Cycles dark -> light -> high-contrast -> dark. */
  cycle: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "pharma.theme";
const ORDER: Theme[] = ["dark", "light", "hc"];

// "hc" stacks on top of dark so any dark-tuned utility still applies.
const CLASSES: Record<Theme, string[]> = {
  dark: ["dark"],
  light: [],
  hc: ["dark", "hc"],
};

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>("dark");

  React.useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
    const initial: Theme =
      stored && ORDER.includes(stored)
        ? stored
        : window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark";
    setThemeState(initial);
  }, []);

  React.useEffect(() => {
    const root = document.documentElement;
    root.classList.remove("dark", "hc");
    const classes = CLASSES[theme];
    if (classes.length) root.classList.add(...classes);
    root.style.colorScheme = theme === "light" ? "light" : "dark";
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const setTheme = React.useCallback((next: Theme) => setThemeState(next), []);
  const cycle = React.useCallback(
    () => setThemeState((current) => ORDER[(ORDER.indexOf(current) + 1) % ORDER.length]),
    [],
  );

  const value = React.useMemo(() => ({ theme, setTheme, cycle }), [theme, setTheme, cycle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
