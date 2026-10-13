"use client";

import * as React from "react";

/**
 * A ticking clock. Returns the current time and re-renders on every tick so
 * "fetched 5 minutes ago" style labels stay accurate without a page reload.
 */
export function useNow(intervalMs = 30_000): Date {
  const [now, setNow] = React.useState(() => new Date());

  React.useEffect(() => {
    const id = setInterval(() => setNow(new Date()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return now;
}
