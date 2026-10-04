"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowLeft,
  Globe,
  Clock,
  GitPullRequest,
  ChevronDown,
  Github,
  Plus,
} from "lucide-react";
import { getScan } from "@/lib/api";
import { useScanStream } from "@/hooks/useScanStream";
import { useScanData } from "@/hooks/useScanData";
import { scanStatusMeta, formatRelativeTime } from "@/lib/format";
import dynamic from "next/dynamic";
import { ScanProgress } from "@/components/ScanProgress";
import { SummaryStats } from "@/components/SummaryStats";
import { IntentMatrix } from "@/components/IntentMatrix";
import { ContradictionCard } from "@/components/ContradictionCard";
import { PatchModal } from "@/components/PatchModal";
import { ErrorState } from "@/components/ErrorState";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";
import { LiveScanConsole } from "@/components/LiveScanConsole";

const ScoreGauge = dynamic(
  () => import("@/components/ScoreGauge").then((mod) => mod.ScoreGauge),
  { ssr: false }
);
import type { ScanResponse, ScanStatus, ScanStatusEvent } from "@/types/scan";

const TERMINAL_STATUSES: ScanStatus[] = ["completed", "failed"];
const RUNNING_STATUSES: ScanStatus[] = [
  "pending",
  "crawling",
  "extracting_dom",
  "synthesizing_intents",
  "hybrid_retrieval",
  "nli_evaluation",
  "computing_fscore",
  "generating_patches",
];

function ScanStatusBadge({ status }: { status: ScanStatus }) {
  const meta = scanStatusMeta(status);
  const isRunning = RUNNING_STATUSES.includes(status);

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium border border-white/[0.08] ${meta.classes}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${meta.dotClass} ${isRunning ? "animate-pulse" : ""}`}
      />
      {meta.label}
    </span>
  );
}

export default function ScanDashboardPage() {
  const params = useParams();
  const router = useRouter();
  const scanId = typeof params?.id === "string" ? params.id : null;

  const [initialScan, setInitialScan] = useState<ScanResponse | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [initialError, setInitialError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [patchModalOpen, setPatchModalOpen] = useState(false);
  const [dataReadyTimedOut, setDataReadyTimedOut] = useState(false);

  // SSE Stream: active while scan is running
  const isRunning =
    initialScan === null || RUNNING_STATUSES.includes(initialScan.status);

  const { latestEvent, eventLog, lastGoodStatus } = useScanStream(
    scanId,
    isRunning
  );

  // When stream reaches terminal, re-fetch to get final scan record
  const streamStatus = latestEvent?.status ?? null;
  const streamCompleted =
    streamStatus !== null && TERMINAL_STATUSES.includes(streamStatus);

  const triggerDataFetch =
    (initialScan?.status === "completed") ||
    (streamCompleted && streamStatus === "completed");

  const { scan, intents, contradictions, patches } = useScanData(
    scanId,
    triggerDataFetch
  );

  // Effective displayed scan: prefer rich data from useScanData if available
  const displayScan: ScanResponse | null = scan.data ?? initialScan;

  // Effective status: stream status overrides initial if running
  const currentStatus: ScanStatus =
    (isRunning && latestEvent?.status) ? latestEvent.status : (displayScan?.status ?? "pending");

  // Title update
  useEffect(() => {
    if (displayScan) {
      const domain = (() => {
        try {
          return new URL(displayScan.target_url).hostname;
        } catch {
          return displayScan.target_url;
        }
      })();
      document.title = `${domain} audit | FindableAI`;
    }
  }, [displayScan]);

  // Initial fetch
  const fetchInitial = useCallback(async () => {
    if (!scanId) return;
    setInitialLoading(true);
    setInitialError(null);
    setNotFound(false);
    try {
      const data = await getScan(scanId);
      setInitialScan(data);
    } catch (err) {
      const apiErr = err as { status?: number; message?: string };
      if (apiErr.status === 404) {
        setNotFound(true);
      } else {
        setInitialError(apiErr.message ?? "Failed to load scan.");
      }
    } finally {
      setInitialLoading(false);
    }
  }, [scanId]);

  useEffect(() => {
    void fetchInitial();
  }, [fetchInitial]);

  // Check if data is fully ready to show completed dashboard
  const isFailed = currentStatus === "failed";
  const isCompleted = currentStatus === "completed";

  const isDataReady = Boolean(
    displayScan &&
    displayScan.summary &&
    (displayScan.f_score || scan.data?.f_score) &&
    !scan.loading &&
    !intents.loading &&
    !contradictions.loading &&
    !patches.loading
  );

  useEffect(() => {
    if (isCompleted && !isDataReady && !dataReadyTimedOut) {
      const timer = setTimeout(() => {
        setDataReadyTimedOut(true);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [isCompleted, isDataReady, dataReadyTimedOut]);

  const showCompletedDashboard = isCompleted && (isDataReady || dataReadyTimedOut);
  const patchCount = patches.data?.length ?? displayScan?.patches.length ?? 0;

  // Not found state
  if (notFound) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full space-y-4 text-center">
          <p className="text-5xl font-bold text-text-primary">404</p>
          <p className="text-sm text-text-muted">
            Scan not found. The scan may have expired or the ID is incorrect.
          </p>
          <Link
            href="/"
            className="inline-block rounded-lg bg-white px-5 py-2.5 text-xs font-semibold text-black tracking-wider uppercase transition-colors duration-150 hover:bg-neutral-200 focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Scan another URL
          </Link>
        </div>
      </div>
    );
  }

  // Initial error
  if (initialError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-sm">
          <ErrorState
            title="Failed to load scan"
            message={initialError}
            onRetry={() => void fetchInitial()}
            action={
              <Link
                href="/"
                className="rounded-lg bg-surface-secondary shadow-border px-4 py-2 text-xs font-medium text-text-primary transition-colors duration-150 hover:bg-surface-tertiary focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                Back home
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  // Initial loading: show full processing screen instead of skeleton placeholders
  if (initialLoading || !displayScan) {
    return (
      <div className="min-h-screen bg-background pb-24 relative overflow-x-hidden">
        <div className="pointer-events-none absolute inset-0 -top-20 flex items-center justify-center overflow-hidden">
          <div className="hero-grid-bg absolute inset-0 opacity-40" />
          <div className="hero-glow absolute inset-0 opacity-40" />
        </div>

        <header className="sticky top-0 z-50 glass border-b border-white/[0.08] py-3 sm:py-3.5 w-full">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2 sm:gap-3 group">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={32}
                height={32}
                className="h-7 w-7 rounded-lg object-contain transition-transform duration-150 group-hover:scale-105"
                priority
              />
              <div className="flex items-baseline gap-1.5">
                <span className="text-base tracking-tight text-text-primary font-semibold">
                  FindableAI
                </span>
                <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase hidden sm:inline">
                  MDO
                </span>
              </div>
            </Link>
          </div>
        </header>

        <main className="relative z-10 mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
          <ScanProgress
            currentStatus="pending"
            latestEvent={{
              scan_id: scanId ?? "",
              status: "pending",
              progress_percent: 10,
              current_step: "Initializing",
              message: "Connecting to telemetry stream and loading scan status...",
              timestamp: new Date().toISOString(),
            }}
            lastGoodStatus="pending"
          />
          <LiveScanConsole
            currentStatus="pending"
            latestEvent={null}
            events={[]}
            targetUrl="Initializing audit session..."
          />
        </main>
      </div>
    );
  }

  const activeEvent: ScanStatusEvent | null =
    isCompleted && !showCompletedDashboard
      ? {
          scan_id: scanId ?? "",
          status: "generating_patches",
          progress_percent: 98,
          current_step: "Synthesizing",
          message: "Assembling audit findings, intent evaluations, and patch remediations...",
          timestamp: latestEvent?.timestamp ?? new Date().toISOString(),
        }
      : latestEvent;

  return (
    <div className="min-h-screen bg-background pb-24 relative overflow-x-hidden">
      {/* Ambient Grid & Glow Background */}
      <div className="pointer-events-none absolute inset-0 -top-20 flex items-center justify-center overflow-hidden">
        <div className="hero-grid-bg absolute inset-0 opacity-40" />
        <div className="hero-glow absolute inset-0 opacity-40" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-50 glass border-b border-white/[0.08] py-3 sm:py-3.5 w-full">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            {/* Brand Logo */}
            <Link href="/" className="flex items-center gap-2 sm:gap-3 group">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={32}
                height={32}
                className="h-7 w-7 rounded-lg object-contain transition-transform duration-150 group-hover:scale-105"
                priority
              />
              <div className="flex items-baseline gap-1.5">
                <span className="text-base tracking-tight text-text-primary font-semibold">
                  FindableAI
                </span>
                <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase hidden sm:inline">
                  MDO
                </span>
              </div>
            </Link>

            {/* Right Actions */}
            <div className="flex items-center gap-3">
              <Link
                href="/audit"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white text-black text-xs font-semibold tracking-wide uppercase transition-all duration-150 hover:bg-neutral-200 active:scale-95"
              >
                <Plus size={13} aria-hidden="true" />
                <span>New Audit</span>
              </Link>

              <a
                href="https://github.com/Chirag1724/FindableAI"
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-surface-secondary shadow-border text-xs text-text-muted hover:text-white transition-colors duration-150"
                aria-label="GitHub Repository"
              >
                <Github size={13} className="text-white" />
                <span>GitHub</span>
              </a>
            </div>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
        {/* Page Breadcrumb & Scan Target Meta Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/[0.08]">
          {/* Left: Breadcrumbs + Target URL */}
          <div className="space-y-1.5 min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Link href="/" className="hover:text-white transition-colors duration-150">
                Overview
              </Link>
              <span>/</span>
              <Link href="/audit" className="hover:text-white transition-colors duration-150">
                Audit
              </Link>
              <span>/</span>
              <span className="font-mono text-text-primary text-[11px] truncate">
                {scanId ? (scanId.startsWith("scan_") ? scanId : `scan_${scanId.slice(0, 8)}`) : "Report"}
              </span>
            </div>

            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-secondary shadow-border text-sky-400 shrink-0">
                <Globe size={15} aria-hidden="true" />
              </div>
              <h1 className="font-mono text-base sm:text-lg font-semibold text-white tracking-tight truncate">
                {displayScan.target_url}
              </h1>
            </div>
          </div>

          {/* Right: Badges & Status Meta */}
          <div className="flex flex-wrap items-center gap-2.5 sm:gap-3 shrink-0">
            {displayScan.execution_mode && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium border ${
                  displayScan.execution_mode === "real_llm"
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                    : "border-amber-500/20 bg-amber-500/10 text-amber-400"
                }`}
                title={
                  displayScan.execution_mode === "real_llm"
                    ? `Real LLM Pipeline active (${displayScan.llm_calls_made ?? 0} calls)`
                    : "Deterministic Fallback Mode (LLM rate-limited or unconfigured)"
                }
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    displayScan.execution_mode === "real_llm" ? "bg-emerald-400" : "bg-amber-400"
                  }`}
                />
                {displayScan.execution_mode === "real_llm" ? "Real LLM" : "Fallback Mode"}
              </span>
            )}

            <ScanStatusBadge
              status={
                showCompletedDashboard
                  ? "completed"
                  : currentStatus === "completed"
                  ? "generating_patches"
                  : currentStatus
              }
            />

            <div className="flex items-center gap-1.5 text-xs text-text-muted rounded-lg bg-surface-secondary px-2.5 py-1 shadow-border font-mono">
              <Clock size={12} aria-hidden="true" />
              <span>{formatRelativeTime(displayScan.created_at)}</span>
            </div>
          </div>
        </div>

        {/* Failed state */}
        {isFailed && (
          <ErrorState
            title="Scan failed"
            message={displayScan.error ?? "The scan encountered an error during processing."}
            action={
              <Link
                href="/"
                className="rounded-lg bg-surface-secondary shadow-border px-4 py-2 text-xs font-medium text-text-primary transition-colors duration-150 hover:bg-surface-tertiary focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                Scan another URL
              </Link>
            }
          />
        )}

        {/* Processing Screen: Live Telemetry Pipeline Workspace (shown until page is fully loaded) */}
        {!isFailed && !showCompletedDashboard && (
          <div className="space-y-6 sm:space-y-8">
            <ScanProgress
              currentStatus={isCompleted ? "generating_patches" : currentStatus}
              latestEvent={activeEvent}
              lastGoodStatus={lastGoodStatus}
            />
            <LiveScanConsole
              currentStatus={currentStatus}
              latestEvent={activeEvent}
              events={
                isCompleted && !isDataReady && eventLog.length > 0 && !eventLog.some(e => e.current_step === "Synthesizing")
                  ? [
                      ...eventLog,
                      {
                        message: "Compiling machine discoverability index & verifying patch remediations...",
                        current_step: "Synthesizing",
                        timestamp: new Date().toISOString(),
                      },
                    ]
                  : eventLog
              }
              targetUrl={displayScan.target_url}
            />
          </div>
        )}

        {/* Completed dashboard (ONLY rendered when fully loaded and ready) */}
        {showCompletedDashboard && (
          <div className="space-y-8 sm:space-y-10 animate-fade-in">
            {/* Summary stats */}
            {displayScan.summary && (
              <SummaryStats summary={displayScan.summary} />
            )}

            {/* Findability Analytics Matrix (2x2) */}
            {(() => {
              const fs = displayScan.f_score ?? scan.data?.f_score;
              return fs ? <ScoreGauge fScore={fs} /> : null;
            })()}

            {/* Intent Evaluations */}
            <div className="space-y-3">
              <div className="flex items-center justify-between pb-1 border-b border-white/[0.06]">
                <h2 className="text-xs sm:text-sm font-semibold uppercase tracking-wider text-text-primary">
                  Intent Vector Evaluations
                </h2>
                <span className="font-mono text-[11px] text-text-muted">
                  {intents.data?.length ?? displayScan.summary?.intents_generated ?? 30} Simulated Vectors
                </span>
              </div>
              {intents.error ? (
                <ErrorState
                  message={intents.error}
                  onRetry={intents.retry}
                />
              ) : (
                <IntentMatrix intents={intents.data ?? []} />
              )}
            </div>

            {/* Contradictions */}
            <div className="space-y-3">
              <div className="flex items-center justify-between pb-1 border-b border-white/[0.06]">
                <h2 className="text-xs sm:text-sm font-semibold uppercase tracking-wider text-text-primary">
                  Cross-Page Contradictions &amp; Conflicts
                </h2>
                <span className="font-mono text-[11px] text-text-muted">
                  {contradictions.error ? (
                    <ErrorState
                      message={contradictions.error}
                      onRetry={contradictions.retry}
                    />
                  ) : (
                    <ContradictionCard contradictions={contradictions.data ?? []} />
                  )}
                </span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Sticky patches button (ONLY shown when dashboard is fully loaded) */}
      {showCompletedDashboard && (
        <div className="fixed bottom-0 inset-x-0 flex justify-center px-4 py-3.5 z-30 bg-background/80 backdrop-blur-lg border-t border-white/[0.08] shadow-2xl">
          <button
            type="button"
            onClick={() => setPatchModalOpen(true)}
            disabled={patchCount === 0 && !patches.loading}
            className="flex items-center gap-2 rounded-lg bg-white text-black px-6 py-2.5 text-xs font-bold tracking-wider uppercase shadow-lg transition-all duration-150 hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-blue-500 active:scale-95"
          >
            <GitPullRequest size={15} aria-hidden="true" />
            {patches.loading
              ? "Loading patches..."
              : patchCount > 0
                ? `View ${patchCount} Unified Patch${patchCount === 1 ? "" : "es"}`
                : "No patches required"}
          </button>
        </div>
      )}

      {/* Patch modal */}
      {patchModalOpen && scanId && (
        <PatchModal
          scanId={scanId}
          patches={patches.data ?? displayScan.patches}
          currentScore={
            (displayScan.f_score?.overall_score ?? scan.data?.f_score?.overall_score) ?? 0
          }
          repoUrl={displayScan.repo_url ?? displayScan.github_repo_url ?? scan.data?.repo_url ?? scan.data?.github_repo_url}
          onClose={() => setPatchModalOpen(false)}
        />
      )}
    </div>
  );
}