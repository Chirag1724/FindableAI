"use client";

import { useEffect, useRef, useCallback } from "react";
import { X } from "lucide-react";
import type { EvidenceReference } from "@/types/scan";
import { CopyButton } from "./CopyButton";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

interface EvidenceViewerProps {
  evidence: EvidenceReference;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLElement>;
}

export function EvidenceViewer({ evidence, onClose, triggerRef }: EvidenceViewerProps) {
  const backdropRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const handleAnimatedClose = useCallback(() => {
    if (prefersReducedMotion() || !panelRef.current || !backdropRef.current) {
      onClose();
      return;
    }

    const tl = gsap.timeline({
      onComplete: onClose,
    });
    tl.to(panelRef.current, {
      xPercent: 100,
      duration: 0.2,
      ease: "power2.in",
    }).to(
      backdropRef.current,
      {
        opacity: 0,
        duration: 0.18,
        ease: "power2.in",
      },
      "-=0.1"
    );
  }, [onClose]);

  // Entrance animation
  useEffect(() => {
    if (prefersReducedMotion()) return;

    if (backdropRef.current && panelRef.current) {
      gsap.fromTo(
        backdropRef.current,
        { opacity: 0 },
        { opacity: 1, duration: 0.25, ease: EASING.modal }
      );
      gsap.fromTo(
        panelRef.current,
        { xPercent: 100 },
        { xPercent: 0, duration: 0.28, ease: EASING.modal }
      );
    }
  }, []);

  // Focus trap + return focus on close
  useEffect(() => {
    const triggerEl = triggerRef.current;
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        handleAnimatedClose();
        return;
      }
      if (e.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;

      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
      ).filter((el) => !el.hasAttribute("disabled"));

      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    // Lock body scroll
    const scrollY = window.scrollY;
    document.body.style.position = "fixed";
    document.body.style.top = `-${scrollY}px`;
    document.body.style.width = "100%";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.position = "";
      document.body.style.top = "";
      document.body.style.width = "";
      try {
        window.scrollTo(0, scrollY);
      } catch {
        // Safe ignore in jsdom
      }
      if (triggerEl && typeof triggerEl.focus === "function") {
        triggerEl.focus();
      }
    };
  }, [handleAnimatedClose, triggerRef]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) handleAnimatedClose();
  };

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
      onClick={handleBackdropClick}
      aria-hidden="false"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-viewer-title"
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto glass shadow-2xl custom-scrollbar"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 sticky top-0 z-10 glass border-b border-white/[0.08]">
          <h2
            id="evidence-viewer-title"
            className="text-sm font-semibold text-text-primary"
          >
            Evidence Reference
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={handleAnimatedClose}
            aria-label="Close evidence viewer"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors duration-150 hover:bg-white/10 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-5 px-5 py-5">
          {/* Excerpt */}
          {evidence.excerpt && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                Excerpt
              </h3>
              <p className="rounded-lg bg-surface shadow-border px-3.5 py-3 text-xs text-text-primary leading-relaxed">
                {evidence.excerpt}
              </p>
            </section>
          )}

          {/* DOM path */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                DOM Path
              </h3>
              <CopyButton text={evidence.dom_path} label="Copy path" />
            </div>
            <p className="rounded-lg bg-surface shadow-border px-3.5 py-2.5 font-mono text-xs text-text-primary break-all">
              {evidence.dom_path || "(not available)"}
            </p>
          </section>

          {/* Source URL */}
          {evidence.url && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                Source URL
              </h3>
              <a
                href={evidence.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block truncate text-xs text-violet-400 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded font-mono"
              >
                {evidence.url}
              </a>
            </section>
          )}

          {/* Rank + RRF score */}
          {(evidence.rank !== undefined || evidence.rrf_score !== undefined) && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                Retrieval Scores
              </h3>
              <div className="flex gap-4">
                {evidence.rank !== undefined && (
                  <div className="rounded-lg bg-surface shadow-border px-3 py-2 flex-1">
                    <p className="text-[10px] text-text-muted">Rank</p>
                    <p className="font-mono text-sm text-text-primary">#{evidence.rank}</p>
                  </div>
                )}
                {evidence.rrf_score !== undefined && (
                  <div className="rounded-lg bg-surface shadow-border px-3 py-2 flex-1">
                    <p className="text-[10px] text-text-muted">RRF Score</p>
                    <p className="font-mono text-sm text-text-primary">
                      {evidence.rrf_score.toFixed(4)}
                    </p>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}