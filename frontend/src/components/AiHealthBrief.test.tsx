import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiHealthBrief, AiSummaryTabControl } from "@/components/AiHealthBrief";
import * as api from "@/lib/api";
import type { ScanSummaryResponse } from "@/types/scan";

const READY: ScanSummaryResponse = {
  status: "ready",
  verdict: "insufficient_evidence",
  overall_assessment: {
    text: "20 intents are UNKNOWN and 0 DOM chunks were captured.",
    fact_ids: ["E_unknown_count", "F_dom_chunks"],
  },
  what_the_scan_found: [
    { text: "One page crawled with zero DOM chunks.", fact_ids: ["F_pages", "F_dom_chunks"] },
  ],
  why_it_matters: [],
  evidence_gaps: [
    { text: "All 20 intents remain UNKNOWN.", fact_ids: ["E_unknown_count"] },
  ],
  next_steps: [
    { text: "Re-run after content is crawlable.", priority: "high", fact_ids: ["F_dom_chunks"] },
  ],
  limitations: "Single-page crawl.",
  remediation_status: "unavailable",
  remediation_reason: "no evidence-backed findings",
  generated_at: "2026-10-19T19:00:00Z",
  model: "gemini/gemini-3.5-flash-lite",
  cached: false,
};

function noneResponse(): ScanSummaryResponse {
  return { status: "none" };
}

describe("AiHealthBrief", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads → ready and keeps content when parent callbacks churn (no skeleton blink)", async () => {
    const getSpy = vi.spyOn(api, "getScanSummary").mockResolvedValue(READY);
    const onRestoredReady = vi.fn();

    const { rerender } = render(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        panelOnly
        open
        onRestoredReady={onRestoredReady}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });
    expect(screen.getByTestId("ai-health-brief-overall")).toHaveTextContent(
      /could not be verified/i
    );
    expect(screen.getByTestId("ai-health-brief-verdict")).toHaveTextContent(
      /needs more evidence/i
    );
    expect(getSpy).toHaveBeenCalledTimes(1);

    // Simulate parent SSE/poll re-renders with new callback identities.
    for (let i = 0; i < 5; i++) {
      rerender(
        <AiHealthBrief
          scanId="scan_abc"
          scanStatus="completed"
          panelOnly
          open
          onRestoredReady={() => onRestoredReady()}
          onBusyChange={() => undefined}
          onAutoGenerateConsumed={() => undefined}
        />
      );
    }

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    expect(screen.queryByText(/Preparing your scan findings/i)).not.toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it("autoGenerate posts once and retains ready content", async () => {
    vi.spyOn(api, "getScanSummary").mockResolvedValue(noneResponse());
    let resolvePost!: (v: ScanSummaryResponse) => void;
    const postSpy = vi.spyOn(api, "generateScanSummary").mockImplementation(
      () =>
        new Promise<ScanSummaryResponse>((resolve) => {
          resolvePost = resolve;
        })
    );

    const onConsumed = vi.fn();
    const { rerender } = render(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        panelOnly
        open
        autoGenerate
        onAutoGenerateConsumed={onConsumed}
      />
    );

    await waitFor(() => expect(postSpy).toHaveBeenCalledTimes(1));
    expect(onConsumed).toHaveBeenCalled();
    expect(screen.getByText(/Preparing your scan findings/i)).toBeInTheDocument();

    await act(async () => {
      resolvePost({ ...READY, cached: false });
    });

    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });
    expect(postSpy).toHaveBeenCalledTimes(1);

    // Parent re-asserting autoGenerate after ready must not POST again.
    rerender(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        panelOnly
        open
        autoGenerate
        onAutoGenerateConsumed={onConsumed}
      />
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
  });

  it("disables tab control while loading", () => {
    render(<AiSummaryTabControl active loading onClick={() => undefined} />);
    expect(screen.getByTestId("ai-summary-tab-control")).toBeDisabled();
  });

  it("does not replace ready content with skeleton when scan status props update", async () => {
    vi.spyOn(api, "getScanSummary").mockResolvedValue(READY);

    const { rerender } = render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );

    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });

    rerender(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        outcome="success"
        jobStatus="succeeded"
        panelOnly
        open
      />
    );
    rerender(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        outcome="success"
        jobStatus="succeeded"
        panelOnly
        open
      />
    );

    expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    expect(screen.queryByText(/Preparing your scan findings/i)).not.toBeInTheDocument();
  });

  it("shows error with retry on API failure without looping", async () => {
    const getSpy = vi.spyOn(api, "getScanSummary").mockRejectedValue({
      status: 500,
      message: "Server error",
    });
    const postSpy = vi
      .spyOn(api, "generateScanSummary")
      .mockResolvedValue(READY);

    render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );

    await waitFor(() => {
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
    });
    expect(screen.getByText(/Server error/i)).toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });
  });

  it("shows idle empty state when no summary exists", async () => {
    vi.spyOn(api, "getScanSummary").mockResolvedValue(noneResponse());

    render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );

    await waitFor(() => {
      expect(screen.getByText(/Select/i)).toBeInTheDocument();
      expect(screen.getByText(/AI Summary/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId("ai-health-brief-ready")).not.toBeInTheDocument();
  });

  it("keeps state when collapsed (hidden) then reopened without refetch blink", async () => {
    const getSpy = vi.spyOn(api, "getScanSummary").mockResolvedValue(READY);

    const { rerender } = render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );
    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });

    rerender(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open={false} />
    );
    expect(screen.getByTestId("ai-health-brief-hidden")).toBeInTheDocument();

    rerender(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );
    expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    expect(screen.queryByText(/Preparing your scan findings/i)).not.toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it("uses single-expand accordion; assessment stays visible; all sections retain content", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getScanSummary").mockResolvedValue(READY);

    render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" panelOnly open />
    );

    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });

    // Overall assessment always visible (not buried in accordion only)
    expect(screen.getByTestId("ai-health-brief-overall")).toBeInTheDocument();

    // Default open is "What to do next" when next_steps exist
    const actions = screen.getByTestId("ai-health-brief-actions");
    expect(actions).toHaveAttribute("data-open", "true");
    expect(screen.getByTestId("ai-health-brief-next-steps")).toBeInTheDocument();

    const foundBtn = screen.getByRole("button", { name: /What we found/i });
    await user.click(foundBtn);

    expect(screen.getByTestId("ai-health-brief-found")).toHaveAttribute(
      "data-open",
      "true"
    );
    expect(screen.getByTestId("ai-health-brief-actions")).toHaveAttribute(
      "data-open",
      "false"
    );
    expect(screen.getByTestId("ai-health-brief-found-items")).toBeInTheDocument();

    // Gaps section preserves unverified framing
    await user.click(screen.getByRole("button", { name: /What we couldn’t verify/i }));
    expect(screen.getByTestId("ai-health-brief-gaps")).toHaveAttribute(
      "data-open",
      "true"
    );
    expect(screen.getByTestId("ai-health-brief-found")).toHaveAttribute(
      "data-open",
      "false"
    );
    expect(screen.getByText(/not a pass/i)).toBeInTheDocument();
    expect(screen.getByTestId("ai-health-brief-gaps-items")).toBeInTheDocument();

    // Notes retain remediation
    await user.click(screen.getByRole("button", { name: /Notes & limits/i }));
    expect(screen.getByTestId("ai-health-brief-remediation")).toBeInTheDocument();
  });
});

describe("AiSummaryTabControl", () => {
  it("renders beside-style control with sparkle label as a tab", () => {
    render(<AiSummaryTabControl active={false} onClick={() => undefined} />);
    const tab = screen.getByTestId("ai-summary-tab-control");
    expect(tab).toHaveTextContent("AI Summary");
    expect(tab).toHaveAttribute("role", "tab");
    expect(tab).toHaveAttribute("aria-selected", "false");
  });
});
