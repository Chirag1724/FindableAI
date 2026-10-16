import type { ScanResponse, ScanStatus, ScanStatusEvent } from "@/types/scan";

const TERMINAL: ScanStatus[] = ["completed", "failed"];

/**
 * Map durable progress stage labels (and optional coarse status) onto the
 * fine-grained ScanStatus the stepper / live cards expect.
 */
export function stageToScanStatus(stage: string | null | undefined): ScanStatus | null {
  if (!stage) return null;
  const s = stage.trim().toLowerCase();
  if (!s) return null;
  if (s.includes("audit complete") || s.includes("scan finished")) return "completed";
  if (s.includes("patch")) return "generating_patches";
  if (s.includes("f-score") || s.includes("fscore") || s.includes("reflect")) {
    return "computing_fscore";
  }
  if (s.includes("nli") || s.includes("entailment") || s.includes("contradiction")) {
    return "nli_evaluation";
  }
  if (s.includes("retrieval") || s.includes("evidence") || s.includes("hybrid")) {
    return "hybrid_retrieval";
  }
  if (s.includes("intent") || s.includes("persona") || s.includes("synthetic intent")) {
    return "synthesizing_intents";
  }
  if (s.includes("dom") || s.includes("chunk") || s.includes("structural extraction")) {
    return "extracting_dom";
  }
  if (s.includes("crawl") || s.includes("playwright") || s.includes("observe")) {
    return "crawling";
  }
  return null;
}

export function deriveUiScanStatus(input: {
  status: ScanStatus;
  progressStage?: string | null;
  progressMessage?: string | null;
  progressPercent?: number | null;
  jobStatus?: string | null;
  currentStep?: string | null;
}): ScanStatus {
  const { status } = input;
  if (TERMINAL.includes(status)) return status;

  const fromStage =
    stageToScanStatus(input.currentStep) ||
    stageToScanStatus(input.progressStage) ||
    stageToScanStatus(input.progressMessage);
  if (fromStage) return fromStage;

  // Percent bands as last-resort when stage text is missing.
  const pct = input.progressPercent;
  if (typeof pct === "number" && pct > 0) {
    if (pct >= 97) return "generating_patches";
    if (pct >= 90) return "computing_fscore";
    if (pct >= 80) return "nli_evaluation";
    if (pct >= 70) return "hybrid_retrieval";
    if (pct >= 55) return "synthesizing_intents";
    if (pct >= 35) return "extracting_dom";
    if (pct >= 5) return "crawling";
  }

  if (
    input.jobStatus &&
    ["queued", "claimed", "running", "retry_scheduled"].includes(input.jobStatus)
  ) {
    return status === "pending" ? "crawling" : status;
  }

  return status;
}

/** Wall-clock duration in seconds from ISO timestamps (0 when unknown). */
export function durationFromTimestamps(
  createdAt?: string | null,
  completedAt?: string | null
): number {
  if (!createdAt) return 0;
  const start = Date.parse(createdAt);
  if (Number.isNaN(start)) return 0;
  const end = completedAt ? Date.parse(completedAt) : Date.now();
  if (Number.isNaN(end)) return 0;
  return Math.max(0, (end - start) / 1000);
}

/**
 * Prefer the newer of SSE event vs polled scan snapshot by progress_seq so the
 * progress bar keeps moving when EventSource stays open but quiet.
 */
export function mergeScanProgress(
  scan: ScanResponse | null,
  event: ScanStatusEvent | null
): ScanStatusEvent | null {
  if (!scan && !event) return null;
  if (!scan) return event;
  if (!event) {
    if (
      scan.progress_percent == null &&
      !scan.progress_stage &&
      !scan.progress_message
    ) {
      return null;
    }
    const status = deriveUiScanStatus({
      status: scan.status,
      progressStage: scan.progress_stage,
      progressMessage: scan.progress_message,
      progressPercent: scan.progress_percent,
      jobStatus: scan.job_status,
    });
    return {
      scan_id: scan.scan_id,
      status,
      progress_percent: scan.progress_percent ?? 0,
      current_step: scan.progress_stage || scan.status,
      message: scan.progress_message || `Status: ${scan.status}`,
      timestamp: new Date().toISOString(),
      seq: scan.progress_seq ?? null,
      progress_current: scan.progress_current ?? null,
      progress_total: scan.progress_total ?? null,
    };
  }

  const eventSeq = event.seq ?? -1;
  const scanSeq = scan.progress_seq ?? -1;
  const scanAhead =
    (scanSeq >= 0 && scanSeq > eventSeq) ||
    (typeof scan.progress_percent === "number" &&
      scan.progress_percent > (event.progress_percent ?? 0));

  if (!scanAhead) {
    return {
      ...event,
      status: TERMINAL.includes(event.status)
        ? event.status
        : deriveUiScanStatus({
            status: event.status,
            progressStage: event.current_step,
            progressMessage: event.message,
            progressPercent: event.progress_percent,
            jobStatus: scan.job_status,
            currentStep: event.current_step,
          }),
    };
  }

  const status = TERMINAL.includes(scan.status)
    ? scan.status
    : deriveUiScanStatus({
        status: scan.status,
        progressStage: scan.progress_stage,
        progressMessage: scan.progress_message,
        progressPercent: scan.progress_percent,
        jobStatus: scan.job_status,
      });

  return {
    scan_id: scan.scan_id,
    status,
    progress_percent: scan.progress_percent ?? event.progress_percent ?? 0,
    current_step: scan.progress_stage || event.current_step,
    message: scan.progress_message || event.message,
    timestamp: new Date().toISOString(),
    seq: scan.progress_seq ?? event.seq ?? null,
    progress_current: scan.progress_current ?? event.progress_current ?? null,
    progress_total: scan.progress_total ?? event.progress_total ?? null,
  };
}
