"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * Fades its children in once the page has mounted. Unlike a scroll-triggered
 * animation, this never leaves a card stuck at opacity 0 waiting for an
 * intersection that a nested scroll container may not report.
 */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  return (
    <motion.div
      initial={false}
      animate={mounted ? { opacity: 1, y: 0 } : { opacity: 0, y: 10 }}
      transition={{ duration: 0.4, delay, ease: "easeOut" }}
      className={cn(mounted ? "" : "opacity-0", className)}
    >
      {children}
    </motion.div>
  );
}
