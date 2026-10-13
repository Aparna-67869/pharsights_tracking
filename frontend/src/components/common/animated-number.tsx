"use client";

import * as React from "react";
import { useSpring, useTransform, motion } from "framer-motion";

/**
 * Counts up to `value` on mount and animates smoothly on every change.
 * Uses a spring on a motion value so rapid realtime updates do not restart a
 * JS tween on each frame.
 */
export function AnimatedNumber({
  value,
  format = (n) => Math.round(n).toLocaleString(),
  className,
}: {
  value: number;
  format?: (value: number) => string;
  className?: string;
}) {
  const spring = useSpring(value, { stiffness: 90, damping: 22, mass: 0.6 });
  const text = useTransform(spring, (latest) => format(latest));

  React.useEffect(() => {
    spring.set(value);
  }, [spring, value]);

  return <motion.span className={className}>{text}</motion.span>;
}
