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
    expect(getSpy).toHaveBeenCalledWith("scan_abc", expect.any(AbortSignal), "intelligence");

    // Simulate parent SSE/poll re-renders with new callback identities.
    for (let i = 0; i < 5; i++) {
      rerender(
        <AiHealthBrief
          scanId="scan_abc"
          scanStatus="completed"
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
    expect(screen.queryByText(/Preparing search query evaluations/i)).not.toBeInTheDocument();
    expect(getSpy).toHaveBeenCalledTimes(1);
  });

  it("renders on-demand idle trigger with professional technical styling (no sparkles)", async () => {
    vi.spyOn(api, "getScanSummary").mockResolvedValue(noneResponse());

    render(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        scope="intelligence"
        title="Search Intelligence Summary"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Search Intelligence Summary")).toBeInTheDocument();
    });

    const generateBtn = screen.getByTestId("ai-health-brief-generate");
    expect(generateBtn).toBeInTheDocument();
    expect(generateBtn).toHaveTextContent("Generate Intelligence Summary");
    // Ensure no sparkle text or emojis
    expect(generateBtn.innerHTML).not.toContain("✨");
    expect(generateBtn.innerHTML).not.toContain("sparkle");
  });

  it("triggers on-demand generation when button is clicked with scope='lighthouse'", async () => {
    vi.spyOn(api, "getScanSummary").mockResolvedValue(noneResponse());
    const postSpy = vi.spyOn(api, "generateScanSummary").mockResolvedValue({
      ...READY,
      scope: "lighthouse",
    });

    render(
      <AiHealthBrief
        scanId="scan_abc"
        scanStatus="completed"
        scope="lighthouse"
        title="AI Bot Readiness Summary"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("AI Bot Readiness Summary")).toBeInTheDocument();
    });

    const generateBtn = screen.getByTestId("ai-health-brief-generate");
    expect(generateBtn).toHaveTextContent("Generate Readiness Summary");

    await userEvent.click(generateBtn);

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith("scan_abc", expect.any(AbortSignal), "lighthouse");
    });

    await waitFor(() => {
      expect(screen.getByTestId("ai-health-brief-ready")).toBeInTheDocument();
    });
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
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" open />
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

  it("uses single-expand accordion; assessment stays visible; all sections retain content", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getScanSummary").mockResolvedValue(READY);

    render(
      <AiHealthBrief scanId="scan_abc" scanStatus="completed" open />
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
  it("renders beside-style control without sparkles", () => {
    render(<AiSummaryTabControl active={false} onClick={() => undefined} />);
    const tab = screen.getByTestId("ai-summary-tab-control");
    expect(tab).toHaveTextContent("AI Summary");
    expect(tab).toHaveAttribute("role", "tab");
    expect(tab).toHaveAttribute("aria-selected", "false");
    expect(tab.innerHTML).not.toContain("✨");
  });
});
