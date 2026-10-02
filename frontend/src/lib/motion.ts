import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Only register ScrollTrigger in full browser environments (avoiding jsdom in vitest)
if (
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  process.env.NODE_ENV !== "test"
) {
  gsap.registerPlugin(ScrollTrigger);
}

/**
 * Checks if the user prefers reduced motion.
 * Safely guards against SSR and environments without window.matchMedia (like jsdom).
 */
export function prefersReducedMotion(): boolean {
  if (
    typeof window === "undefined" ||
    typeof window.matchMedia !== "function" ||
    process.env.NODE_ENV === "test"
  ) {
    return true;
  }
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/**
 * Standard easing presets for consistent interaction feel.
 */
export const EASING = {
  entrance: "power3.out",
  expand: "power2.out",
  modal: "power3.out",
  subtle: "power1.out",
};

/**
 * Safe animate helper that respects prefers-reduced-motion.
 */
export function safeAnimate(
  target: gsap.TweenTarget,
  vars: gsap.TweenVars
): gsap.core.Tween | null {
  if (prefersReducedMotion()) {
    gsap.set(target, vars);
    return null;
  }
  return gsap.to(target, vars);
}

export { gsap, ScrollTrigger };
