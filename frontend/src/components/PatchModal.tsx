"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { X, GitPullRequest, ExternalLink, Loader2 } from "lucide-react";
import type { PatchProposal, PullRequestResult } from "@/types/scan";
import { parseUnifiedDiff } from "@/lib/diff";
import type { DiffLine } from "@/lib/diff";
import { applyPatches } from "@/lib/api";
import type { ApiError } from "@/types/scan";
import { EmptyState } from "./EmptyState";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

interface PatchModalProps {
  scanId: string;
  patches: PatchProposal[];
  currentScore: number;
  repoUrl?: string | null;
  onClose: () => void;
}

function DiffRenderer({ diffText }: { diffText: string }) {
  const parsed = parseUnifiedDiff(diffText);

  if (parsed.hunks.length === 0) {
    return (
      <p className="text-xs text-text-muted italic">No diff available.</p>
    );
  }

  const lineClass = (line: DiffLine): string => {
    switch (line.type) {
      case "add":
        return "bg-emerald-950/50 text-emerald-300";
      case "del":
        return "bg-rose-950/50 text-rose-300";
      case "meta":
        return "text-text-muted bg-transparent";
      default:
        return "text-text-muted";
    }
  };

  const linePrefix = (line: DiffLine): string => {
    switch (line.type) {
      case "add": return "+";
      case "del": return "-";
      default: return " ";
    }
  };

  return (
    <div className="overflow-x-auto rounded-lg shadow-border custom-scrollbar">
      <pre className="min-w-max bg-black/60 p-3 font-mono text-xs leading-relaxed">
        {parsed.hunks.map((hunk, hi) => (
          <div key={hi}>
            <div className="text-violet-400/80 mb-1 font-semibold">{hunk.header}</div>
            {hunk.lines.map((line, li) => {
              const oldNo = line.oldLineNo !== null ? String(line.oldLineNo).padStart(3, " ") : "   ";
              const newNo = line.newLineNo !== null ? String(line.newLineNo).padStart(3, " ") : "   ";
              return (
                <div key={li} className={`flex ${lineClass(line)}`}>
                  <span className="w-8 shrink-0 select-none pr-2 text-right text-text-muted/40">
                    {oldNo}
                  </span>
                  <span className="w-8 shrink-0 select-none pr-2 text-right text-text-muted/40">
                    {newNo}
                  </span>
                  <span className="shrink-0 pr-2 select-none font-bold">{linePrefix(line)}</span>
                  <span>{line.content}</span>
                </div>
              );
            })}
          </div>
        ))}
      </pre>
    </div>
  );
}

const PATCH_TYPE_LABELS: Record<string, string> = {
  content_clarification: "Content",
  schema_microdata: "Schema",
  heading_structure: "Heading",
  factual_conflict_resolution: "Conflict Fix",
};

export function PatchModal({
  scanId,
  patches,
  currentScore,
  repoUrl,
  onClose,
}: PatchModalProps) {
  const hasRepoUrl = Boolean(repoUrl && repoUrl.trim().length > 0);
  const [prState, setPrState] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [prResult, setPrResult] = useState<PullRequestResult | null>(null);
  const [prError, setPrError] = useState<string | null>(null);

  const backdropRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);

  const totalDelta = patches.reduce(
    (sum, p) => sum + p.impact_score_delta,
    0
  );
  const projectedScore = Math.min(100, currentScore + totalDelta);

  const handleAnimatedClose = useCallback(() => {
    if (prefersReducedMotion() || !panelRef.current || !backdropRef.current) {
      onClose();
      return;
    }

    const tl = gsap.timeline({
      onComplete: onClose,
    });
    tl.to(panelRef.current, {
      y: 16,
      scale: 0.98,
      opacity: 0,
      duration: 0.18,
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
        { y: 20, scale: 0.97, opacity: 0 },
        { y: 0, scale: 1, opacity: 1, duration: 0.3, ease: EASING.modal }
      );
    }
  }, []);

  // Focus trap
  useEffect(() => {
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
          'button, [href], input, [tabindex]:not([tabindex="-1"])'
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
    };
  }, [handleAnimatedClose]);

  const handleCreatePr = async () => {
    if (prState === "loading") return;
    setPrState("loading");
    setPrError(null);

    try {
      const result = await applyPatches(scanId);
      setPrResult(result);
      setPrState("success");
    } catch (err) {
      const apiErr = err as ApiError;
      setPrError(apiErr.message ?? "Failed to create pull request.");
      setPrState("error");
    }
  };

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-end justify-center sm:items-center px-0 sm:px-4 bg-black/75 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) handleAnimatedClose(); }}
    >
      <div
        ref={panelRef}
        data-testid="patch-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="patch-modal-title"
        className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-t-2xl sm:rounded-xl glass shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between px-5 py-4 border-b border-white/[0.08]">
          <div>
            <h2
              id="patch-modal-title"
              className="flex items-center gap-2 text-sm font-semibold text-text-primary"
            >
              <GitPullRequest size={16} aria-hidden="true" />
              Proposed Patches ({patches.length})
            </h2>
            {patches.length > 0 && (
              <p className="mt-0.5 text-xs text-text-muted">
                Projected F-Score: {currentScore.toFixed(1)} &rarr;{" "}
                <span className="font-semibold text-emerald-400">
                  {projectedScore.toFixed(1)}
                </span>{" "}
                (+{totalDelta.toFixed(1)} pts)
              </p>
            )}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={handleAnimatedClose}
            aria-label="Close patches modal"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors duration-150 hover:bg-white/10 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar">
          {patches.length === 0 ? (
            <EmptyState
              title="No patches available"
              description="No remediation patches were generated for this scan."
            />
          ) : (
            patches.map((patch) => (
              <div
                key={patch.patch_id}
                className="space-y-3"
              >
                {/* Patch header */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-1 flex items-center gap-2 flex-wrap">
                      <span className="rounded-md bg-violet-900/50 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-violet-300">
                        {PATCH_TYPE_LABELS[patch.patch_type] ?? patch.patch_type}
                      </span>
                      <span className="rounded-full bg-emerald-950/80 px-2 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-800/50">
                        +{patch.impact_score_delta.toFixed(1)} pts
                      </span>
                    </div>
                    <h3 className="text-sm font-semibold text-text-primary">
                      {patch.title}
                    </h3>
                    <p className="mt-1 text-xs text-text-muted leading-relaxed">
                      {patch.rationale}
                    </p>
                  </div>
                </div>

                {/* DOM anchor */}
                <div className="rounded-lg bg-surface shadow-border px-3.5 py-3 space-y-2 text-xs">
                  <p className="font-medium text-text-muted">DOM Anchor</p>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <p className="text-[10px] text-text-muted mb-0.5">Selector</p>
                      <p className="font-mono text-text-primary break-all">{patch.dom_anchor.css_selector}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-text-muted mb-0.5">Tag</p>
                      <p className="font-mono text-text-primary">{patch.dom_anchor.tag_name}</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <div>
                      <p className="text-[10px] text-text-muted mb-0.5">Before</p>
                      <pre className="whitespace-pre-wrap break-all font-mono text-[10px] text-rose-300 bg-rose-950/30 rounded p-2 border border-rose-800/30">
                        {patch.dom_anchor.original_snippet}
                      </pre>
                    </div>
                    <div>
                      <p className="text-[10px] text-text-muted mb-0.5">After</p>
                      <pre className="whitespace-pre-wrap break-all font-mono text-[10px] text-emerald-300 bg-emerald-950/30 rounded p-2 border border-emerald-800/30">
                        {patch.dom_anchor.suggested_snippet}
                      </pre>
                    </div>
                  </div>
                </div>

                {/* Diff */}
                <DiffRenderer diffText={patch.unified_diff} />

                {/* Separator */}
                <div className="h-px bg-white/[0.06]" />
              </div>
            ))
          )}
        </div>

        {/* Footer - PR button */}
        <div className="shrink-0 px-5 py-4 border-t border-white/[0.08] bg-surface">
          {prState === "success" && prResult ? (
            <div
              data-testid="pr-result"
              className="flex flex-wrap items-center gap-3 rounded-lg bg-emerald-950/50 border border-emerald-800/40 px-4 py-3 text-sm"
            >
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-emerald-300">
                  PR #{prResult.pr_number} created
                </p>
                <p className="font-mono text-xs text-emerald-400/70">
                  {prResult.branch_name}
                </p>
              </div>
              <a
                href={prResult.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-semibold text-white transition-colors duration-150 hover:bg-emerald-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <ExternalLink size={12} aria-hidden="true" />
                View on GitHub
              </a>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {!hasRepoUrl && (
                <div
                  data-testid="no-repo-warning"
                  className="flex items-center gap-2 rounded-lg bg-amber-500/10 border border-amber-500/20 px-3.5 py-2 text-xs text-amber-300/90"
                >
                  <p>
                    No GitHub repository connected for this scan. Add a GitHub repo URL in Advanced options when starting a scan to enable automated PR creation.
                  </p>
                </div>
              )}
              {hasRepoUrl && repoUrl && (
                <div className="flex items-center justify-between text-[11px] text-text-muted px-0.5">
                  <span>Target Repository:</span>
                  <span className="font-mono text-text-secondary">{repoUrl}</span>
                </div>
              )}
              {prState === "error" && prError && (
                <p className="text-xs text-rose-400">{prError}</p>
              )}
              <button
                ref={submitRef}
                type="button"
                data-testid="create-pr-button"
                onClick={() => void handleCreatePr()}
                disabled={prState === "loading" || patches.length === 0 || !hasRepoUrl}
                title={!hasRepoUrl ? "Connect a GitHub repository to enable PR creation" : undefined}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-white text-black px-5 py-3 text-xs font-semibold tracking-wider uppercase transition-all duration-150 hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 active:scale-[0.99]"
              >
                {prState === "loading" ? (
                  <>
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                    Creating pull request...
                  </>
                ) : prState === "error" ? (
                  <>
                    <GitPullRequest size={16} aria-hidden="true" />
                    Retry
                  </>
                ) : (
                  <>
                    <GitPullRequest size={16} aria-hidden="true" />
                    Create Pull Request
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}