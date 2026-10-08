import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { LighthouseTab } from "@/components/LighthouseTab";
import * as api from "@/lib/api";
import { MOCK_LIGHTHOUSE_RESPONSE } from "@/lib/mockLighthouseData";

describe("LighthouseTab", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders lighthouse data when API call succeeds", async () => {
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

  it("renders in-progress message when backend returns 404 (scan still computing)", async () => {
    const apiError = {
      status: 404,
      message: "Request failed with status 404",
      detail: "Scan 'scan_running123' not found.",
    };
    vi.spyOn(api, "getLighthouse").mockRejectedValueOnce(apiError);

    render(<LighthouseTab scanId="scan_running123" />);

    await waitFor(() => {
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
    });

    expect(screen.getByText("Assessment in Progress")).toBeInTheDocument();
    expect(screen.getByText("Scan 'scan_running123' not found.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry assessment/i })).toBeInTheDocument();
  });

  it("renders error state on network/server failure and retries on button click", async () => {
    const apiError = {
      status: 500,
      message: "Internal server error",
    };
    const getLighthouseMock = vi
      .spyOn(api, "getLighthouse")
      .mockRejectedValueOnce(apiError)
      .mockResolvedValueOnce(MOCK_LIGHTHOUSE_RESPONSE);

    render(<LighthouseTab scanId="scan_err123" />);

    await waitFor(() => {
      expect(screen.getByTestId("error-state")).toBeInTheDocument();
    });

    expect(screen.getByText("Failed to Load AI Lighthouse")).toBeInTheDocument();
    expect(screen.getByText("Internal server error")).toBeInTheDocument();

    const retryBtn = screen.getByRole("button", { name: /retry assessment/i });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByTestId("lighthouse-gauge-chatgpt")).toBeInTheDocument();
    });

    expect(getLighthouseMock).toHaveBeenCalledTimes(2);
  });
});
