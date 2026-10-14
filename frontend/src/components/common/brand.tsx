import { cn } from "@/lib/utils";

/**
 * Brand mark and wordmark for Pharsights Intel Command Center.
 *
 * The mark is drawn without gradients or clip paths so it needs no per-instance
 * ids — it renders identically wherever it appears on a page. The wordmark
 * splits "Pharsights" so "Phar" carries the blue and "sights" the green.
 */
export function BrandLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label="Pharsights"
      className={cn("shrink-0", className)}
    >
      {/* Circle split down the middle: blue left, green right. */}
      <path d="M16 3 A13 13 0 0 0 16 29 Z" className="fill-blue-600 dark:fill-blue-500" />
      <path d="M16 3 A13 13 0 0 1 16 29 Z" className="fill-emerald-500 dark:fill-emerald-400" />
      {/* Rising pulse: the monitoring signal. */}
      <path
        d="M8.6 20.8 L13.2 14.6 L17.6 18.4 L23.4 9.6"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="23.4" cy="9.6" r="2.5" fill="#ffffff" />
    </svg>
  );
}

export function BrandWordmark({
  className,
  suffix = "Intel",
}: {
  className?: string;
  suffix?: string | null;
}) {
  return (
    <span className={cn("inline-flex items-baseline whitespace-nowrap", className)}>
      <span className="text-blue-600 dark:text-blue-400">Phar</span>
      <span className="text-emerald-600 dark:text-emerald-400">sights</span>
      {suffix ? <span className="ml-1">{suffix}</span> : null}
    </span>
  );
}
