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
import { GaugeSkeleton, TableSkeleton, CardSkeleton, StatsSkeleton } from "@/components/Skeletons";

const ScoreGauge = dynamic(
  () => import("@/components/ScoreGauge").then((mod) => mod.ScoreGauge),
  { ssr: false, loading: () => <GaugeSkeleton /> }
);
import type { ScanResponse, ScanStatus } from "@/types/scan";

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
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${meta.classes}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${meta.dotClass} ${RUNNING_STATUSES.includes(status) ? "animate-pulse" : ""
          }`}
        aria-hidden="true"
      />
      {meta.label}
    </span>
  );
}

function EventLog({ events }: { events: { message: string; timestamp: string; current_step: string }[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const recent = events.slice(-8);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, open]);

  if (events.length === 0) return null;

  return (
    <div
      className="rounded-xl bg-[#141414] overflow-hidden"
      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset"
        aria-expanded={open}
      >
        <span className="text-xs font-semibold text-[#A1A1A1]">
          Pipeline log ({events.length} events)
        </span>
        <ChevronDown
          size={14}
          className={`text-[#A1A1A1] transition-transform ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="max-h-48 overflow-y-auto border-t border-white/5 px-4 pb-3 pt-2">
          {recent.map((ev, i) => (
            <div key={i} className="flex gap-2 py-1 text-xs">
              <span className="shrink-0 font-mono text-[#A1A1A1]/60">
                {new Date(ev.timestamp).toLocaleTimeString()}
              </span>
              <span className="text-[#A1A1A1]">{ev.current_step}</span>
              <span className="text-[#EDEDED]">{ev.message}</span>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
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

  // Determine if we need streaming (running) or static display (completed/failed)
  const isRunning =
    initialScan !== null && RUNNING_STATUSES.includes(initialScan.status);

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

  // Not found state
  if (notFound) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="max-w-sm w-full space-y-4 text-center">
          <p className="text-5xl font-black text-[#EDEDED]">404</p>
          <p className="text-sm text-[#A1A1A1]">
            Scan not found. The scan may have expired or the ID is incorrect.
          </p>
          <Link
            href="/"
            className="inline-block rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-violet-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Scan another URL
          </Link>
        </div>
      </div>
    );
  }

  // Initial loading
  if (initialLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
          <StatsSkeleton />
          <GaugeSkeleton />
          <TableSkeleton />
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
                className="rounded-lg bg-[#191919] px-4 py-2 text-sm text-[#EDEDED] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                Back home
              </Link>
            }
          />
        </div>
      </div>
    );
  }

  if (!displayScan) return null;

  const isFailed = currentStatus === "failed";
  const isCompleted = currentStatus === "completed";
  const patchCount = patches.data?.length ?? displayScan.patches.length;

  return (
    <div className="min-h-screen bg-background pb-24">
      {/* Header */}
      <header
        className="sticky top-0 z-30 px-5 py-3 sm:px-8 sm:py-4 lg:px-12"
        style={{
          background: "rgba(10,10,10,0.85)",
          backdropFilter: "blur(12px)",
          boxShadow: "0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        <div className="mx-auto flex max-w-5xl items-center gap-4">
          <Link
            href="/"
            className="flex items-center gap-1.5 text-xs text-[#A1A1A1] transition-colors hover:text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded shrink-0"
          >
            <Image
              src="/logo.png"
              alt="FindableAI"
              width={28}
              height={28}
              className="h-5 w-5 sm:h-7 sm:w-7 rounded"
            />
            <ArrowLeft size={14} aria-hidden="true" />
            Back
          </Link>

          <div className="min-w-0 flex-1 flex items-center gap-2">
            <Globe size={14} className="shrink-0 text-[#A1A1A1]" aria-hidden="true" />
            <span
              className="truncate font-mono text-xs text-[#EDEDED]"
              title={displayScan.target_url}
            >
              {displayScan.target_url}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-3">
            {displayScan.execution_mode && (
              <span
                className={`hidden items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium sm:inline-flex border ${
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
            <ScanStatusBadge status={currentStatus} />
            <div className="hidden items-center gap-1 text-xs text-[#A1A1A1] sm:flex">
              <Clock size={12} aria-hidden="true" />
              {formatRelativeTime(displayScan.created_at)}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
        {/* Failed state */}
        {isFailed && (
          <ErrorState
            title="Scan failed"
            message={displayScan.error ?? "The scan encountered an error during processing."}
            action={
              <Link
                href="/"
                className="rounded-lg bg-[#191919] px-4 py-2 text-sm text-[#EDEDED] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                Scan another URL
              </Link>
            }
          />
        )}

        {/* Running: progress + event log */}
        {!isFailed && !isCompleted && (
          <>
            <ScanProgress
              currentStatus={currentStatus}
              latestEvent={latestEvent}
              lastGoodStatus={lastGoodStatus}
            />
            <EventLog events={eventLog} />
          </>
        )}

        {/* Also show progress during stream even if scan is completed */}
        {isRunning && isCompleted && (
          <ScanProgress
            currentStatus="completed"
            latestEvent={latestEvent}
            lastGoodStatus={lastGoodStatus}
          />
        )}

        {/* Completed dashboard */}
        {isCompleted && (
          <>
            {/* Summary stats */}
            {scan.loading ? (
              <StatsSkeleton />
            ) : displayScan.summary ? (
              <SummaryStats summary={displayScan.summary} />
            ) : null}

            {/* Findability Analytics Matrix (2x2) */}
            {scan.loading || (!displayScan.f_score && !scan.data?.f_score) ? (
              <GaugeSkeleton />
            ) : (() => {
              const fs = displayScan.f_score ?? scan.data?.f_score;
              return fs ? <ScoreGauge fScore={fs} /> : null;
            })()}

            {/* Intent Evaluations */}
            <div>
              <h2 className="mb-3 text-sm font-semibold text-[#EDEDED]">
                Intent Evaluations
              </h2>
              {intents.loading ? (
                <TableSkeleton />
              ) : intents.error ? (
                <ErrorState
                  message={intents.error}
                  onRetry={intents.retry}
                />
              ) : (
                <IntentMatrix intents={intents.data ?? []} />
              )}
            </div>

            {/* Contradictions */}
            <div>
              <h2 className="mb-3 text-sm font-semibold text-[#EDEDED]">
                Contradictions
              </h2>
              {contradictions.loading ? (
                <CardSkeleton count={1} />
              ) : contradictions.error ? (
                <ErrorState
                  message={contradictions.error}
                  onRetry={contradictions.retry}
                />
              ) : (
                <ContradictionCard contradictions={contradictions.data ?? []} />
              )}
            </div>
          </>
        )}
      </main>

      {/* Sticky patches button (only when completed and patches exist) */}
      {isCompleted && (
        <div
          className="fixed bottom-0 inset-x-0 flex justify-center px-4 py-4 z-30"
          style={{
            background: "rgba(10,10,10,0.8)",
            backdropFilter: "blur(12px)",
            boxShadow: "0 -1px 0 rgba(255,255,255,0.06)",
          }}
        >
          <button
            type="button"
            onClick={() => setPatchModalOpen(true)}
            disabled={patchCount === 0 && !patches.loading}
            className="flex items-center gap-2 rounded-xl bg-violet-600 px-6 py-3 text-sm font-semibold text-white shadow-lg transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <GitPullRequest size={16} aria-hidden="true" />
            {patches.loading
              ? "Loading patches..."
              : patchCount > 0
                ? `View ${patchCount} patch${patchCount === 1 ? "" : "es"}`
                : "No patches available"}
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
          onClose={() => setPatchModalOpen(false)}
        />
      )}
    </div>
  );
}