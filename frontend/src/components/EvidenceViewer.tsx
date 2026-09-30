"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import type { EvidenceReference } from "@/types/scan";
import { CopyButton } from "./CopyButton";

interface EvidenceViewerProps {
  evidence: EvidenceReference;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLElement>;
}

export function EvidenceViewer({ evidence, onClose, triggerRef }: EvidenceViewerProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Focus trap + return focus on close
  useEffect(() => {
    const triggerEl = triggerRef.current;
    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
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
      window.scrollTo(0, scrollY);
      triggerEl?.focus();
    };
  }, [onClose, triggerRef]);

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ backgroundColor: "rgba(0,0,0,0.6)", backdropFilter: "blur(2px)" }}
      onClick={handleBackdropClick}
      aria-hidden="false"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-viewer-title"
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto"
        style={{
          background: "rgba(20,20,20,0.72)",
          backdropFilter: "blur(16px)",
          boxShadow: "-1px 0 0 0 rgba(255,255,255,0.08), -20px 0 60px rgba(0,0,0,0.6)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4 sticky top-0 z-10"
          style={{
            background: "rgba(20,20,20,0.9)",
            boxShadow: "0 1px 0 rgba(255,255,255,0.06)",
          }}
        >
          <h2
            id="evidence-viewer-title"
            className="text-sm font-semibold text-[#EDEDED]"
          >
            Evidence Reference
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close evidence viewer"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[#A1A1A1] transition-colors hover:bg-white/10 hover:text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-5 px-5 py-5">
          {/* Excerpt */}
          {evidence.excerpt && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#A1A1A1]">
                Excerpt
              </h3>
              <p className="rounded-lg bg-[#191919] px-3 py-2.5 text-sm text-[#EDEDED]">
                {evidence.excerpt}
              </p>
            </section>
          )}

          {/* DOM path */}
          <section>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-[10px] font-semibold uppercase tracking-wider text-[#A1A1A1]">
                DOM Path
              </h3>
              <CopyButton text={evidence.dom_path} label="Copy path" />
            </div>
            <p className="rounded-lg bg-[#191919] px-3 py-2 font-mono text-xs text-[#EDEDED] break-all">
              {evidence.dom_path || "(not available)"}
            </p>
          </section>

          {/* Source URL */}
          {evidence.url && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#A1A1A1]">
                Source URL
              </h3>
              <a
                href={evidence.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block truncate text-sm text-violet-400 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
              >
                {evidence.url}
              </a>
            </section>
          )}

          {/* Rank + RRF score */}
          {(evidence.rank !== undefined || evidence.rrf_score !== undefined) && (
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#A1A1A1]">
                Retrieval Scores
              </h3>
              <div className="flex gap-4">
                {evidence.rank !== undefined && (
                  <div className="rounded-lg bg-[#191919] px-3 py-2">
                    <p className="text-[10px] text-[#A1A1A1]">Rank</p>
                    <p className="font-mono text-sm text-[#EDEDED]">#{evidence.rank}</p>
                  </div>
                )}
                {evidence.rrf_score !== undefined && (
                  <div className="rounded-lg bg-[#191919] px-3 py-2">
                    <p className="text-[10px] text-[#A1A1A1]">RRF Score</p>
                    <p className="font-mono text-sm text-[#EDEDED]">
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