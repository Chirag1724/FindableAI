import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { LighthouseTab } from "@/components/LighthouseTab";
import * as api from "@/lib/api";
import { MOCK_LIGHTHOUSE_RESPONSE } from "@/lib/mockLighthouseData";

describe("LighthouseTab", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders mock lighthouse data when API call succeeds", async () => {
    vi.spyOn(api, "getLighthouse").mockResolvedValueOnce(MOCK_LIGHTHOUSE_RESPONSE);

    render(<LighthouseTab scanId="scan_test123" />);

    await waitFor(() => {
      expect(screen.getByTestId("lighthouse-gauge-chatgpt")).toBeInTheDocument();
    });

    expect(screen.getByTestId("lighthouse-gauge-gemini")).toBeInTheDocument();
    expect(screen.getByTestId("lighthouse-gauge-perplexity")).toBeInTheDocument();
    expect(screen.getByTestId("lighthouse-gauge-claude")).toBeInTheDocument();

    expect(screen.getByTestId("crawler-governance-panel")).toBeInTheDocument();
    expect(screen.getByTestId("audit-checklist")).toBeInTheDocument();
  });

  it("falls back to MOCK_LIGHTHOUSE_RESPONSE when backend endpoint fails (mock fallback mode)", async () => {
    vi.spyOn(api, "getLighthouse").mockRejectedValueOnce(new Error("404 Not Found"));

    render(<LighthouseTab scanId="scan_fallback" />);

    await waitFor(() => {
      expect(screen.getByTestId("lighthouse-tab")).toBeInTheDocument();
    });

    expect(screen.getByText(/AI Lighthouse Preview Mode/i)).toBeInTheDocument();
    expect(screen.getByTestId("lighthouse-gauge-chatgpt")).toBeInTheDocument();
  });
});
