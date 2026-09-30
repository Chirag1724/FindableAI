"use client";

import { useEffect, useRef, useState } from "react";

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

const DURATION_MS = 1200;

/**
 * Animates a number from 0 to `target` using requestAnimationFrame.
 * Triggered once when the element enters the viewport via IntersectionObserver.
 * Respects prefers-reduced-motion: shows final value immediately.
 */
export function useCountUp(
  target: number,
  decimals = 0
): { value: string; ref: React.RefObject<HTMLSpanElement> } {
  const [displayValue, setDisplayValue] = useState("0");
  const ref = useRef<HTMLSpanElement>(null);
  const rafRef = useRef<number | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    // Respect reduced motion
    const prefersReduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;
    if (prefersReduced) {
      setDisplayValue(target.toFixed(decimals));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !startedRef.current) {
          startedRef.current = true;
          const startTime = performance.now();

          const tick = (now: number) => {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / DURATION_MS, 1);
            const eased = easeOutCubic(progress);
            setDisplayValue((eased * target).toFixed(decimals));

            if (progress < 1) {
              rafRef.current = requestAnimationFrame(tick);
            }
          };

          rafRef.current = requestAnimationFrame(tick);
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(el);

    return () => {
      observer.disconnect();
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [target, decimals]);

  return { value: displayValue, ref };
}