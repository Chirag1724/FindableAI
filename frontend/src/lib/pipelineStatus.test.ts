import { describe, expect, it } from "vitest";
import {
  deriveUiScanStatus,
  durationFromTimestamps,
  mergeScanProgress,
  stageToScanStatus,
} from "./pipelineStatus";
import type { ScanResponse, ScanStatusEvent } from "@/types/scan";

describe("stageToScanStatus", () => {
  it("maps NLI stage labels", () => {
    expect(stageToScanStatus("NLI Entailment Classifier")).toBe("nli_evaluation");
  });

  it("maps crawl and DOM labels", () => {
    expect(stageToScanStatus("Playwright Crawling")).toBe("crawling");
    expect(stageToScanStatus("DOM Structural Extraction")).toBe("extracting_dom");
  });
});

describe("deriveUiScanStatus", () => {
  it("keeps terminal statuses", () => {
    expect(
      deriveUiScanStatus({ status: "completed", progressStage: "NLI Entailment Classifier" })
    ).toBe("completed");
  });

  it("upgrades pending using progress stage", () => {
    expect(
      deriveUiScanStatus({
        status: "pending",
        progressStage: "NLI Entailment Classifier",
        progressPercent: 86,
        jobStatus: "running",
      })
    ).toBe("nli_evaluation");
  });

  it("uses percent bands when stage is missing", () => {
    expect(
      deriveUiScanStatus({ status: "pending", progressPercent: 85, jobStatus: "running" })
    ).toBe("nli_evaluation");
  });
});

describe("durationFromTimestamps", () => {
  it("computes positive duration", () => {
    const start = "2026-10-16T15:00:00.000Z";
    const end = "2026-10-16T15:02:30.000Z";
    expect(durationFromTimestamps(start, end)).toBe(150);
  });

  it("returns 0 for missing created_at", () => {
    expect(durationFromTimestamps(null, "2026-10-16T15:02:30.000Z")).toBe(0);
  });
});

describe("mergeScanProgress", () => {
  it("prefers polled scan when progress_seq is ahead of SSE", () => {
    const event: ScanStatusEvent = {
      scan_id: "scan_1",
      status: "pending",
      progress_percent: 50,
      current_step: "old",
      message: "stale",
      timestamp: "2026-10-16T15:00:00.000Z",
      seq: 5,
    };
    const scan = {
      scan_id: "scan_1",
      status: "pending",
      progress_percent: 86,
      progress_stage: "NLI Entailment Classifier",
      progress_message: "[20/30] claim...",
      progress_seq: 12,
      progress_current: 20,
      progress_total: 30,
      job_status: "running",
      target_url: "https://example.com",
      created_at: "2026-10-16T15:00:00.000Z",
    } as ScanResponse;

    const merged = mergeScanProgress(scan, event);
    expect(merged?.progress_percent).toBe(86);
    expect(merged?.status).toBe("nli_evaluation");
    expect(merged?.seq).toBe(12);
  });
});
