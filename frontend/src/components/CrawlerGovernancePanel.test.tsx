import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CrawlerGovernancePanel } from "@/components/CrawlerGovernancePanel";
import type { CrawlerGovernance } from "@/types/lighthouse";

const MOCK_GOVERNANCE: CrawlerGovernance = {
  ai_visibility_index: 88,
  scraping_risk: "low",
  bot_matrix: [
    { bot: "GPTBot", category: "training", status: "allowed" },
    { bot: "PerplexityBot", category: "search", status: "blocked", impact: "critical" },
    { bot: "Bytespider", category: "scraper", status: "blocked", impact: "positive" },
  ],
  llms_txt_present: true,
};

describe("CrawlerGovernancePanel", () => {
  it("renders AI Visibility Index and Data Scraping Risk badge", () => {
    render(<CrawlerGovernancePanel governance={MOCK_GOVERNANCE} />);

    expect(screen.getByText("AI Visibility Index")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
    expect(screen.getByText("Data Scraping Risk")).toBeInTheDocument();
    expect(screen.getByText("Low Scraping Risk")).toBeInTheDocument();
    expect(screen.getByText("Active Manifest")).toBeInTheDocument();
  });

  it("renders the bot status matrix with user agents and categories", () => {
    render(<CrawlerGovernancePanel governance={MOCK_GOVERNANCE} />);

    expect(screen.getByText("GPTBot")).toBeInTheDocument();
    expect(screen.getByText("PerplexityBot")).toBeInTheDocument();
    expect(screen.getByText("Bytespider")).toBeInTheDocument();

    expect(screen.getByText("Model Training")).toBeInTheDocument();
    expect(screen.getByText("Search / Citation")).toBeInTheDocument();
    expect(screen.getByText("Commercial Scraper")).toBeInTheDocument();

    expect(screen.getByText("Protected")).toBeInTheDocument();
    expect(screen.getByText("Critical Citation Drop")).toBeInTheDocument();
  });

  it("opens and closes the optimized robots.txt modal", () => {
    render(<CrawlerGovernancePanel governance={MOCK_GOVERNANCE} />);

    const openBtn = screen.getByRole("button", {
      name: /generate optimized robots\.txt/i,
    });
    fireEvent.click(openBtn);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Optimized robots.txt Configuration")).toBeInTheDocument();
    expect(screen.getByText(/User-agent: OAI-SearchBot/i)).toBeInTheDocument();

    const closeBtn = screen.getByRole("button", { name: /close dialog/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the modal when Escape key is pressed", () => {
    render(<CrawlerGovernancePanel governance={MOCK_GOVERNANCE} />);

    const openBtn = screen.getByRole("button", {
      name: /generate optimized robots\.txt/i,
    });
    fireEvent.click(openBtn);

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
