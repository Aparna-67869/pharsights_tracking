import { format, formatDistanceToNow, parseISO } from "date-fns";

export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return format(parseISO(value), "dd MMM yyyy");
  } catch {
    return value;
  }
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return "—";
  try {
    return format(parseISO(value), "dd MMM yyyy HH:mm");
  } catch {
    return value;
  }
}

export function fmtRelative(value?: string | null): string {
  if (!value) return "—";
  try {
    return formatDistanceToNow(parseISO(value), { addSuffix: true });
  } catch {
    return value;
  }
}

export function fmtNumber(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

export function fmtCompact(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

/** Whole days from today until the given date (negative = already past). */
export function daysUntil(value?: string | null): number | null {
  if (!value) return null;
  try {
    const target = parseISO(value);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((target.getTime() - today.getTime()) / 86_400_000);
  } catch {
    return null;
  }
}

export function fmtExtension(days?: number | null): string {
  if (days === null || days === undefined) return "—";
  const years = days / 365.25;
  return `${days.toLocaleString()} d${years >= 1 ? ` (${years.toFixed(1)} yr)` : ""}`;
}

export const MODULE_LABELS: Record<string, string> = {
  ftf: "First-to-File",
  pte: "Patent Term Extension",
  pde: "Approved Active Moiety",
  orange_book: "Orange Book",
  patents: "Patent Intelligence",
};

export function moduleLabel(module?: string | null): string {
  if (!module) return "General";
  return MODULE_LABELS[module] ?? module;
}

export const PRIORITY_STYLES: Record<string, string> = {
  critical:
    "bg-destructive/15 text-destructive border-destructive/30 dark:text-red-300",
  high: "bg-warning/15 text-warning-foreground border-warning/40 dark:text-amber-300",
  medium: "bg-primary/15 text-primary border-primary/30",
  low: "bg-muted text-muted-foreground border-border",
};

export const CHANGE_STYLES: Record<string, string> = {
  added: "bg-success/15 text-success border-success/30 dark:text-emerald-300",
  updated: "bg-primary/15 text-primary border-primary/30",
  removed: "bg-destructive/15 text-destructive border-destructive/30 dark:text-red-300",
};

/**
 * Resolve the value a row displays for one column, preferring the exact cell
 * text published in the source document (`raw`) over the normalized field.
 * `rawKey` is matched case/space-insensitively so callers can pass the label a
 * human sees on FDA.gov / USPTO.gov.
 */
export function rawValue<T extends { raw?: Record<string, unknown> | null }>(
  row: T,
  rawKey: string,
  fallbackKey?: keyof T & string,
): string | null {
  const raw = row.raw;
  if (raw) {
    const target = normalize(rawKey);
    for (const [key, value] of Object.entries(raw)) {
      if (normalize(key) === target && value != null && value !== "") {
        return String(value);
      }
    }
  }
  if (fallbackKey) {
    const value = row[fallbackKey];
    return value == null || value === "" ? null : String(value);
  }
  return null;
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** True when a row carries at least one preserved source cell. */
export function hasRaw(row: { raw?: Record<string, unknown> | null }): boolean {
  return Boolean(row.raw && Object.keys(row.raw).length > 0);
}
