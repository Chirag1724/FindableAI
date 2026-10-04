import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SummaryStats } from "@/components/SummaryStats";
import type { AuditSummary } from "@/types/scan";

const MOCK_SUMMARY: AuditSummary = {
  pages_crawled: 3,
  max_pages_requested: 5,
  dom_chunks_extracted: 42,
  intents_generated: 15,
  contradictions_detected: 1,
  execution_time_seconds: 4.82,
  crawled_pages: [
    {
      url: "https://example.com/",
      status_code: 200,
      chunks_count: 20,
      title: "Example Domain Home",
      load_time_ms: 120,
    },
    {
      url: "https://example.com/pricing",
      status_code: 200,
      chunks_count: 14,
      title: "Pricing Plans",
      load_time_ms: 95,
    },
    {
      url: "https://example.com/docs",
      status_code: 200,
      chunks_count: 8,
      title: "Documentation",
      load_time_ms: 110,
    },
  ],
};

describe("SummaryStats component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "IntersectionObserver",
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
      }))
    );
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("renders all 5 stat cards with correct labels", () => {
    render(<SummaryStats summary={MOCK_SUMMARY} />);

    expect(screen.getByText("Pages Crawled")).toBeInTheDocument();
    expect(screen.getByText("DOM Chunks")).toBeInTheDocument();
    expect(screen.getByText("Intents Tested")).toBeInTheDocument();
    expect(screen.getByText("Contradictions")).toBeInTheDocument();
    expect(screen.getByText("Scan Duration")).toBeInTheDocument();
  });

  it("opens Crawl Scope Manifest modal when Pages Crawled card is clicked", async () => {
    render(<SummaryStats summary={MOCK_SUMMARY} />);

    // Modal is not visible initially
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Click the Pages Crawled card button
    const pagesCard = screen.getByRole("button", {
      name: /Pages Crawled: click to view details/i,
    });
    await userEvent.click(pagesCard);

    // Modal is open
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Crawl Scope Manifest")).toBeInTheDocument();
    expect(screen.getByText("3 pages crawled (Configured Scope: 5)")).toBeInTheDocument();

    // Shows crawled routes
    expect(screen.getByText("Home (/)")).toBeInTheDocument();
    expect(screen.getByText("/pricing")).toBeInTheDocument();
    expect(screen.getByText("/docs")).toBeInTheDocument();

    // Shows domain boundary explanation
    expect(screen.getByText(/Reachable domain boundary/i)).toBeInTheDocument();
  });

  it("closes modal on close button click", async () => {
    render(<SummaryStats summary={MOCK_SUMMARY} />);

    const pagesCard = screen.getByRole("button", {
      name: /Pages Crawled: click to view details/i,
    });
    await userEvent.click(pagesCard);

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /Close crawl manifest/i });
    await userEvent.click(closeBtn);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes modal on Escape key press", async () => {
    render(<SummaryStats summary={MOCK_SUMMARY} />);

    const pagesCard = screen.getByRole("button", {
      name: /Pages Crawled: click to view details/i,
    });
    await userEvent.click(pagesCard);

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
