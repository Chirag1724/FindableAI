"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  X,
  GitPullRequest,
  GitCommit,
  ExternalLink,
  Loader2,
  FileCode,
  Globe,
  Check,
  Copy,
  RefreshCw,
  Info,
  Code2,
} from "lucide-react";
import type { PatchProposal, PullRequestResult, VerificationRun } from "@/types/scan";
import { parseUnifiedDiff } from "@/lib/diff";
import type { DiffLine } from "@/lib/diff";
import { applyPatches, getPatches, verifyRemediation } from "@/lib/api";
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

function CodeFileViewer({ content, filePath }: { content: string; filePath: string }) {
  const [copied, setCopied] = useState(false);
  const lines = content.split("\n");

  const handleCopy = () => {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="overflow-hidden rounded-lg shadow-border border border-white/[0.08]">
      <div className="flex items-center justify-between bg-black/80 px-3.5 py-2 border-b border-white/[0.08] text-xs font-mono">
        <span className="text-text-secondary flex items-center gap-1.5 truncate">
          <FileCode size={13} className="text-emerald-400 shrink-0" aria-hidden="true" />
          {filePath}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-emerald-400 font-semibold bg-emerald-950/70 border border-emerald-800/50 px-2 py-0.5 rounded text-[10px] tracking-wide">
            + NEW COMPONENT
          </span>
          <button
            type="button"
            onClick={handleCopy}
            className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text-primary px-2 py-0.5 rounded hover:bg-white/10 transition-colors"
            title="Copy code"
          >
            {copied ? (
              <Check size={12} className="text-emerald-400" />
            ) : (
              <Copy size={12} />
            )}
            <span>{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>
      </div>
      <div className="overflow-x-auto custom-scrollbar">
        <pre className="min-w-max bg-black/60 p-3 font-mono text-xs leading-relaxed">
          {lines.map((line, idx) => (
            <div key={idx} className="flex bg-emerald-950/20 text-emerald-300">
              <span className="w-8 shrink-0 select-none pr-2 text-right text-text-muted/40">
                {idx + 1}
              </span>
              <span className="shrink-0 pr-2 select-none font-bold text-emerald-500/80">+</span>
              <span>{line}</span>
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

const PATCH_TYPE_LABELS: Record<string, string> = {
  content_clarification: "Content",
  schema_microdata: "Schema",
  heading_structure: "Heading",
  factual_conflict_resolution: "Conflict Fix",
  robots_governance: "Crawler Governance",
  llms_manifest: "LLMs Manifest",
};

interface PrFileItem {
  filePath: string;
  displayName: string;
  type: "diff" | "new_component";
  diffText?: string;
  content?: string;
  patchId: string;
}

function extractPrFiles(
  primaryPatch: PatchProposal,
  allPatches: PatchProposal[]
): PrFileItem[] {
  const patchesToInspect = allPatches.length > 0 ? allPatches : [primaryPatch];
  const files: PrFileItem[] = [];
  const seenPaths = new Set<string>();

  const hasFrameworkFiles = patchesToInspect.some(
    (p) => Boolean(p.framework || (p.auxiliary_files && p.auxiliary_files.length > 0))
  );

  const addTargetFile = (p: PatchProposal) => {
    if (!p.target_file) return;
    if (hasFrameworkFiles && (p.target_file === "index.html" || p.target_file.endsWith(".html"))) {
      return;
    }
    if (!seenPaths.has(p.target_file)) {
      seenPaths.add(p.target_file);
      files.push({
        filePath: p.target_file,
        displayName: p.target_file.split("/").pop() || p.target_file,
        type: "diff",
        diffText: p.code_diff || p.unified_diff,
        patchId: p.patch_id,
      });
    }
  };

  const addAuxFiles = (p: PatchProposal) => {
    if (!p.auxiliary_files) return;
    for (const aux of p.auxiliary_files) {
      if (!seenPaths.has(aux.file_path)) {
        seenPaths.add(aux.file_path);
        files.push({
          filePath: aux.file_path,
          displayName: aux.file_path.split("/").pop() || aux.file_path,
          type: "new_component",
          content: aux.content,
          patchId: p.patch_id,
        });
      }
    }
  };

  // 1. Primary patch target file & aux files first
  addTargetFile(primaryPatch);
  addAuxFiles(primaryPatch);

  // 2. Additional files across remaining patches
  for (const p of patchesToInspect) {
    if (p.patch_id === primaryPatch.patch_id) continue;
    addTargetFile(p);
    addAuxFiles(p);
  }

  return files;
}

function PatchCard({
  patch,
  totalUnifiedCount,
  totalPrDelta,
  allPatches = [],
}: {
  patch: PatchProposal;
  totalUnifiedCount?: number;
  totalPrDelta?: number;
  allPatches?: PatchProposal[];
}) {
  const prFiles = extractPrFiles(patch, allPatches);
  const hasFrameworkPatch = Boolean(
    patch.target_file || patch.code_diff || prFiles.length > 0
  );
  const isMultiPatchPR = Boolean(hasFrameworkPatch && totalUnifiedCount && totalUnifiedCount > 1);

  // Active file tab in framework PR view
  const [selectedFile, setSelectedFile] = useState<string>(
    prFiles[0]?.filePath ?? patch.target_file ?? ""
  );

  useEffect(() => {
    if (prFiles.length > 0 && !prFiles.some((f) => f.filePath === selectedFile)) {
      setSelectedFile(prFiles[0].filePath);
    }
  }, [prFiles, selectedFile]);

  const frameworkPatch =
    allPatches.find((p) => Boolean(p.framework)) ??
    (patch.framework ? patch : null);

  const frameworkLabel =
    frameworkPatch?.framework === "nextjs_app_router"
      ? "Next.js App Router"
      : frameworkPatch?.framework === "nextjs_pages"
        ? "Next.js Pages Router"
        : frameworkPatch?.framework || (hasFrameworkPatch ? "Framework Native" : null);

  const displayTitle = isMultiPatchPR
    ? `Pull Request Remediation (${totalUnifiedCount} Unified Patches)`
    : patch.title;

  const displayDelta = isMultiPatchPR
    ? (totalPrDelta ?? patch.impact_score_delta)
    : patch.impact_score_delta;

  const fileSummary =
    prFiles.length > 0
      ? ` (${prFiles.map((f) => f.displayName).join(" & ")})`
      : "";

  const displayRationale = isMultiPatchPR
    ? `Consolidates all ${totalUnifiedCount} remediation patches into a single PR branch${fileSummary} for machine discoverability.`
    : patch.rationale;

  const activeFile = prFiles.find((f) => f.filePath === selectedFile) ?? prFiles[0];

  return (
    <div className="space-y-3" data-testid={`patch-card-${patch.patch_id}`}>
      {/* Patch header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2 flex-wrap">
            <span className="rounded-md bg-violet-900/50 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-violet-300">
              {PATCH_TYPE_LABELS[patch.patch_type] ?? patch.patch_type}
            </span>
            <span className="rounded-full bg-emerald-950/80 px-2 py-0.5 text-xs font-semibold text-emerald-400 border border-emerald-800/50">
              +{displayDelta.toFixed(1)} pts
            </span>
            {frameworkLabel && (
              <span className="rounded-md bg-blue-950/60 border border-blue-800/40 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-300 flex items-center gap-1">
                <Code2 size={11} className="text-blue-400" />
                {frameworkLabel}
              </span>
            )}
            {hasFrameworkPatch && (
              <span className="rounded-md bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300 flex items-center gap-1">
                <GitPullRequest size={11} className="text-emerald-400" />
                1:1 GitHub PR Parity
              </span>
            )}
            {!hasFrameworkPatch && patch.framework && (
              <span className="rounded-md bg-blue-950/40 border border-blue-800/30 px-2 py-0.5 font-mono text-[10px] font-semibold text-blue-300 flex items-center gap-1">
                <Code2 size={11} className="text-blue-400" />
                Included in PR (JsonLd.tsx)
              </span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-text-primary">
            {displayTitle}
          </h3>
          <p className="mt-1 text-xs text-text-muted leading-relaxed">
            {displayRationale}
          </p>
        </div>
      </div>

      {/* Case 1: Primary Framework Patch - Show the exact PR files being modified/created */}
      {hasFrameworkPatch && prFiles.length > 0 ? (
        <div className="space-y-2 border-b border-white/[0.08] pb-2.5">
          {/* Sub-tabs for exact files modified/created in PR */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none no-scrollbar flex-wrap">
              {prFiles.map((file) => {
                const isSelected = activeFile?.filePath === file.filePath;
                return (
                  <button
                    key={file.filePath}
                    type="button"
                    data-testid={`tab-${file.filePath}`}
                    onClick={() => setSelectedFile(file.filePath)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                      isSelected
                        ? file.type === "new_component"
                          ? "bg-emerald-950/70 text-emerald-300 border border-emerald-800/50 font-medium shadow-sm"
                          : "bg-blue-950/70 text-blue-300 border border-blue-800/50 font-medium shadow-sm"
                        : "text-text-muted hover:text-text-primary hover:bg-white/5"
                    }`}
                  >
                    <FileCode
                      size={13}
                      className={file.type === "new_component" ? "text-emerald-400" : "text-blue-400"}
                    />
                    <span>{file.displayName}</span>
                    <span
                      className={`text-[10px] px-1 rounded border ${
                        file.type === "new_component"
                          ? "bg-emerald-900/60 text-emerald-200 border border-emerald-700/40"
                          : "bg-blue-900/60 text-blue-200 border border-blue-700/40"
                      }`}
                    >
                      {file.type === "new_component" ? "+ new component" : "diff"}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="text-[11px] text-text-muted font-mono flex items-center gap-1.5">
              <GitCommit size={12} className="text-text-muted" />
              <span>Exact PR files committed to branch</span>
            </div>
          </div>

          {/* Active File Display */}
          {activeFile && (
            activeFile.type === "new_component" ? (
              <div className="pt-1">
                <CodeFileViewer
                  content={activeFile.content || ""}
                  filePath={activeFile.filePath}
                />
              </div>
            ) : (
              <div className="space-y-2 pt-1">
                <div className="flex items-center justify-between text-xs px-1 text-text-muted font-mono">
                  <span className="text-text-secondary flex items-center gap-1.5">
                    <FileCode size={13} className="text-blue-400" />
                    {activeFile.filePath}
                  </span>
                  <span className="text-[10px] text-blue-400/80">Unified Git Diff</span>
                </div>
                <DiffRenderer diffText={activeFile.diffText || ""} />
              </div>
            )
          )}
        </div>
      ) : (
        /* Case 2: Plain Static HTML Site (No Framework / No Repo) - Show raw DOM patch */
        <div className="space-y-3">
          <div className="rounded-lg bg-surface shadow-border px-3.5 py-3 space-y-2 text-xs">
            <p className="font-medium text-text-muted">DOM Anchor</p>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-[10px] text-text-muted mb-0.5">Selector</p>
                <p className="font-mono text-text-primary break-all">
                  {patch.dom_anchor.css_selector}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-text-muted mb-0.5">Tag</p>
                <p className="font-mono text-text-primary">
                  {patch.dom_anchor.tag_name}
                </p>
              </div>
            </div>
          </div>
          <DiffRenderer diffText={patch.unified_diff} />
        </div>
      )}

      {/* Separator */}
      <div className="h-px bg-white/[0.06]" />
    </div>
  );
}

export function PatchModal({
  scanId,
  patches,
  currentScore,
  repoUrl,
  onClose,
}: PatchModalProps) {
  const [customRepoUrl, setCustomRepoUrl] = useState(repoUrl ?? "");
  const activeRepo = customRepoUrl.trim();
  const hasRepoUrl = Boolean(activeRepo.length > 0);
  const [resolvedPatches, setResolvedPatches] = useState<PatchProposal[]>(patches);
  const [resolvingDiffs, setResolvingDiffs] = useState(false);
  const [prState, setPrState] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [prResult, setPrResult] = useState<PullRequestResult | null>(null);
  const [prError, setPrError] = useState<string | null>(null);
  const [verifyState, setVerifyState] = useState<
    "idle" | "loading" | "done" | "error"
  >("idle");
  const [verifyResult, setVerifyResult] = useState<VerificationRun | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const backdropRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);

  const totalDelta = resolvedPatches.reduce(
    (sum, p) => sum + p.impact_score_delta,
    0
  );
  const projectedScore = Math.min(100, currentScore + totalDelta);

  const primaryFrameworkPatch =
    resolvedPatches.find(
      (p) => Boolean(p.framework || (p.auxiliary_files && p.auxiliary_files.length > 0))
    ) ??
    resolvedPatches.find((p) => Boolean(p.target_file || p.code_diff));
  const hasFrameworkPR = Boolean(primaryFrameworkPatch);

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

  // Sync patches when prop updates
  useEffect(() => {
    setResolvedPatches(patches);
  }, [patches]);

  // Live framework patch enrichment when repository is present
  const handleResolveFrameworkDiffs = useCallback(
    async (targetRepo: string) => {
      if (!targetRepo.trim() || typeof getPatches !== "function") return;
      setResolvingDiffs(true);
      try {
        const updated = await getPatches(scanId, targetRepo.trim());
        if (Array.isArray(updated) && updated.length > 0) {
          setResolvedPatches(updated);
        }
      } catch {
        // Fallback to existing proposals gracefully
      } finally {
        setResolvingDiffs(false);
      }
    },
    [scanId]
  );

  useEffect(() => {
    if (repoUrl && patches.length > 0 && patches.some((p) => !p.code_diff)) {
      void handleResolveFrameworkDiffs(repoUrl);
    }
  }, [repoUrl, patches, handleResolveFrameworkDiffs]);

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
        if (
          typeof window !== "undefined" &&
          typeof window.scrollTo === "function" &&
          process.env.NODE_ENV !== "test"
        ) {
          window.scrollTo(0, scrollY);
        }
      } catch {
        // Safe ignore
      }
    };
  }, [handleAnimatedClose]);

  const handleCreatePr = async () => {
    if (prState === "loading") return;
    setPrState("loading");
    setPrError(null);
    setVerifyState("idle");
    setVerifyResult(null);
    setVerifyError(null);

    try {
      const trimmedCustom = customRepoUrl.trim();
      const hasOverride = trimmedCustom.length > 0 && trimmedCustom !== (repoUrl ?? "").trim();
      const result = hasOverride
        ? await applyPatches(scanId, { repo_url: trimmedCustom })
        : await applyPatches(scanId);
      setPrResult(result);
      setPrState("success");
      const effectiveRepo = (hasOverride ? trimmedCustom : repoUrl) || "";
      if (effectiveRepo) {
        void handleResolveFrameworkDiffs(effectiveRepo);
      }
    } catch (err) {
      const apiErr = err as ApiError;
      setPrError(apiErr.message ?? "Failed to create pull request.");
      setPrState("error");
    }
  };

  const handleVerifyRemediation = async () => {
    if (verifyState === "loading" || !prResult) return;
    setVerifyState("loading");
    setVerifyError(null);
    try {
      const payload = prResult.remediation_run_id
        ? { remediation_run_id: prResult.remediation_run_id }
        : undefined;
      const result = await verifyRemediation(scanId, payload);
      setVerifyResult(result);
      setVerifyState("done");
    } catch (err) {
      const apiErr = err as ApiError;
      setVerifyError(apiErr.message ?? "Post-PR verification failed.");
      setVerifyState("error");
    }
  };

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-stretch sm:items-center justify-center p-0 sm:p-4 bg-background sm:bg-black/75 sm:backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) handleAnimatedClose(); }}
    >
      <div
        ref={panelRef}
        data-testid="patch-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="patch-modal-title"
        className="flex h-full sm:h-auto sm:max-h-[90vh] w-full max-w-3xl flex-col rounded-none sm:rounded-xl bg-background sm:glass shadow-2xl overflow-hidden"
      >
        {/* Header: Full-screen mobile app top bar + desktop modal header */}
        <div className="flex shrink-0 items-center justify-between px-4 sm:px-5 py-3.5 sm:py-4 border-b border-white/[0.08] bg-surface/70 sm:bg-transparent pt-[calc(0.875rem+env(safe-area-inset-top,0px))] sm:pt-4">
          <div className="min-w-0 pr-2">
            <h2
              id="patch-modal-title"
              className="flex items-center gap-2 text-xs sm:text-sm font-semibold text-text-primary"
            >
              <GitPullRequest size={15} className="shrink-0 text-violet-400" aria-hidden="true" />
              <span className="truncate">
                {hasFrameworkPR
                  ? `Pull Request: ${resolvedPatches.length} Unified Patch${resolvedPatches.length === 1 ? "" : "es"}`
                  : `Proposed Patches (${resolvedPatches.length})`}
              </span>
            </h2>
            {resolvedPatches.length > 0 && (
              <p className="mt-0.5 text-[11px] sm:text-xs text-text-muted">
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
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors duration-150 hover:bg-white/10 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 shrink-0"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 sm:space-y-6 custom-scrollbar">
          {resolvedPatches.length === 0 ? (
            <EmptyState
              title="No patches available"
              description="No remediation patches were generated for this scan."
            />
          ) : hasFrameworkPR ? (
            <div className="space-y-6">
              {/* Primary Framework PR Files */}
              <PatchCard
                patch={primaryFrameworkPatch!}
                totalUnifiedCount={resolvedPatches.length}
                totalPrDelta={totalDelta}
                allPatches={resolvedPatches}
              />

              {/* Remediations Bundled in this PR */}
              {resolvedPatches.length > 1 && (
                <div className="rounded-xl bg-surface/70 border border-white/[0.08] p-4 space-y-3">
                  <div className="flex items-center justify-between text-xs pb-1 border-b border-white/[0.06]">
                    <span className="font-semibold text-text-primary flex items-center gap-1.5">
                      <GitPullRequest size={13} className="text-violet-400" />
                      Remediations Bundled in this PR ({resolvedPatches.length})
                    </span>
                    <span className="font-mono text-emerald-400 font-semibold">
                      +{totalDelta.toFixed(1)} pts total
                    </span>
                  </div>
                  <div className="space-y-2">
                    {resolvedPatches
                      .filter((p) => p.patch_id !== primaryFrameworkPatch!.patch_id)
                      .map((p) => (
                        <div
                          key={p.patch_id}
                          className="flex items-start justify-between gap-3 p-3 rounded-lg bg-black/40 border border-white/[0.04] text-xs"
                          data-testid={`patch-card-${p.patch_id}`}
                        >
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span className="rounded bg-violet-900/50 px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase text-violet-300">
                                {PATCH_TYPE_LABELS[p.patch_type] ?? p.patch_type}
                              </span>
                              <span className="font-semibold text-text-primary text-xs">
                                {p.title}
                              </span>
                            </div>
                            <p className="text-[11px] text-text-muted leading-relaxed">
                              {p.rationale}
                            </p>
                          </div>
                          <span className="shrink-0 text-emerald-400 font-mono text-xs font-semibold bg-emerald-950/80 border border-emerald-800/40 px-2 py-0.5 rounded">
                            +{p.impact_score_delta.toFixed(1)} pts
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            resolvedPatches.map((patch) => (
              <PatchCard key={patch.patch_id} patch={patch} />
            ))
          )}
        </div>

        {/* Footer - PR button */}
        <div className="shrink-0 px-4 sm:px-5 py-4 border-t border-white/[0.08] bg-surface pb-[calc(1rem+env(safe-area-inset-bottom,0px))] sm:pb-4">
          {prState === "success" && prResult ? (
            <div
              data-testid="pr-result"
              className="flex flex-col gap-2 rounded-lg bg-emerald-950/50 border border-emerald-800/40 px-4 py-3 text-sm"
            >
              <div className="flex flex-wrap items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-emerald-300">
                    PR #{prResult.pr_number} opened
                  </p>
                  <p className="font-mono text-xs text-emerald-400/70">
                    {prResult.branch_name}
                  </p>
                  {prResult.lifecycle_state && (
                    <p className="text-[11px] text-emerald-400/60 mt-0.5" data-testid="pr-lifecycle-state">
                      Lifecycle: {prResult.lifecycle_state}
                      {prResult.lifecycle_state === "pr_open"
                        ? " — PR created is not a verified fix"
                        : prResult.lifecycle_state === "verified"
                          ? " — heuristic check only (not a full website re-scan)"
                          : ""}
                    </p>
                  )}
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
              <div className="flex flex-col gap-2 pt-1 border-t border-emerald-800/30">
                {verifyState === "done" && verifyResult ? (
                  <div data-testid="verify-result" className="text-xs space-y-1">
                    <p className="font-semibold text-text-primary" data-testid="verify-outcome">
                      {verifyResult.issue_outcome === "fixed"
                        ? "Heuristic check: issue terms found"
                        : verifyResult.issue_outcome === "unresolved"
                          ? "Heuristic check: issue appears unresolved"
                          : "Verification inconclusive"}
                      {verifyResult.fully_verified
                        ? " — fully verified"
                        : " (not fully verified)"}
                    </p>
                    <p className="text-[10px] text-text-muted" data-testid="verify-method">
                      method: {verifyResult.verification_method ?? "heuristic_post_pr"}
                    </p>
                    {verifyResult.detail && (
                      <p className="text-text-muted leading-relaxed">{verifyResult.detail}</p>
                    )}
                    {verifyResult.evaluated_revision && (
                      <p className="font-mono text-[10px] text-text-muted/80" data-testid="verify-revision">
                        revision {verifyResult.evaluated_revision}
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    <p className="text-[11px] text-text-muted leading-relaxed">
                      Opening a PR does not prove the finding is fixed. Run a post-PR
                      verification against the PR head revision.
                    </p>
                    <button
                      type="button"
                      data-testid="verify-remediation-btn"
                      onClick={() => void handleVerifyRemediation()}
                      disabled={verifyState === "loading"}
                      className="inline-flex items-center justify-center gap-1.5 self-start rounded-lg border border-emerald-700/50 bg-emerald-950/40 px-3 py-1.5 text-xs font-semibold text-emerald-200 transition-colors hover:bg-emerald-900/50 disabled:opacity-60"
                    >
                      {verifyState === "loading" ? (
                        <>
                          <Loader2 size={12} className="animate-spin" aria-hidden="true" />
                          Verifying…
                        </>
                      ) : (
                        "Run post-PR verification"
                      )}
                    </button>
                    {verifyState === "error" && verifyError && (
                      <p className="text-[11px] text-rose-400/90" data-testid="verify-error">
                        {verifyError}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {!repoUrl && (
                <div
                  data-testid="no-repo-warning"
                  className="flex flex-col gap-2 rounded-lg bg-surface/80 border border-amber-500/20 p-3 text-xs"
                >
                  <p className="text-amber-400/90 leading-relaxed">
                    No GitHub repository connected for this scan. Add a GitHub repo URL in Advanced options when starting a scan to enable automated PR creation, or enter one below:
                  </p>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="patch-modal-repo-input" className="text-text-muted font-medium flex items-center justify-between">
                      <span>Target GitHub Repository:</span>
                      <span className="text-[10px] text-text-muted/60">owner/repo or URL</span>
                    </label>
                    <div className="flex gap-2">
                      <input
                        id="patch-modal-repo-input"
                        type="text"
                        placeholder="https://github.com/Chirag1724/FindableAI"
                        value={customRepoUrl}
                        onChange={(e) => setCustomRepoUrl(e.target.value)}
                        className="w-full rounded-md bg-black/50 border border-white/10 px-3 py-1.5 font-mono text-xs text-text-primary placeholder:text-text-muted/40 focus:border-blue-500 focus:outline-none"
                      />
                      {activeRepo && (
                        <button
                          type="button"
                          onClick={() => void handleResolveFrameworkDiffs(customRepoUrl)}
                          disabled={resolvingDiffs}
                          className="shrink-0 flex items-center gap-1.5 rounded-md bg-white/10 hover:bg-white/15 px-3 py-1.5 text-[11px] font-mono font-medium text-text-primary border border-white/10 transition-colors"
                          title="Preview code diffs for this repository"
                        >
                          <RefreshCw size={11} className={resolvingDiffs ? "animate-spin" : ""} />
                          <span>Sync</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
              {repoUrl && (
                <div className="flex items-center justify-between text-[11px] text-text-muted px-0.5">
                  <span>Target Repository:</span>
                  <span className="font-mono text-text-secondary">{activeRepo}</span>
                </div>
              )}
              {prState === "error" && prError && (
                <div className="rounded-md bg-rose-950/40 border border-rose-800/40 px-3 py-2 text-xs text-rose-300">
                  <p className="font-medium">PR Creation Failed</p>
                  <p className="text-[11px] text-rose-400/90 mt-0.5">{prError}</p>
                </div>
              )}
              <button
                ref={submitRef}
                type="button"
                data-testid="create-pr-button"
                onClick={() => void handleCreatePr()}
                disabled={prState === "loading" || resolvedPatches.length === 0 || !hasRepoUrl}
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