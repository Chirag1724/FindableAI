import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ScanReportTabPanels } from "@/components/ScanReportTabPanels";
import { AiSummaryTabControl } from "@/components/AiHealthBrief";
import type { ScanReportTab } from "@/lib/scanReportTabs";

function TabHarness({ initial = "overview" as ScanReportTab }) {
  const [activeTab, setActiveTab] = useState<ScanReportTab>(initial);
  return (
    <div>
      <div role="tablist" aria-label="Scan Report Views">
        <button
          type="button"
          role="tab"
          id="tab-overview"
          aria-selected={activeTab === "overview"}
          onClick={() => setActiveTab("overview")}
        >
          Intelligence Overview
        </button>
        <button
          type="button"
          role="tab"
          id="tab-lighthouse"
          aria-selected={activeTab === "lighthouse"}
          onClick={() => setActiveTab("lighthouse")}
        >
          AI Lighthouse
        </button>
        <AiSummaryTabControl
          active={activeTab === "summary"}
          onClick={() => setActiveTab("summary")}
        />
      </div>
      <ScanReportTabPanels
        activeTab={activeTab}
        overview={<div>Overview body</div>}
        lighthouse={<div>Lighthouse body</div>}
        summary={<div>Summary body</div>}
      />
    </div>
  );
}

describe("ScanReportTabPanels", () => {
  it("shows only overview content by default", () => {
    render(<TabHarness />);
    expect(screen.getByTestId("panel-overview")).toBeInTheDocument();
    expect(screen.getByText("Overview body")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-lighthouse")).not.toBeInTheDocument();
    expect(screen.queryByTestId("panel-summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Summary body")).not.toBeInTheDocument();
  });

  it("switches to lighthouse without leaving overview/summary mounted", async () => {
    const user = userEvent.setup();
    render(<TabHarness />);
    await user.click(screen.getByRole("tab", { name: /AI Lighthouse/i }));
    expect(screen.getByTestId("panel-lighthouse")).toBeInTheDocument();
    expect(screen.getByText("Lighthouse body")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-overview")).not.toBeInTheDocument();
    expect(screen.queryByTestId("panel-summary")).not.toBeInTheDocument();
  });

  it("switches to AI Summary without overview underneath", async () => {
    const user = userEvent.setup();
    render(<TabHarness />);
    await user.click(screen.getByTestId("ai-summary-tab-control"));
    expect(screen.getByTestId("panel-summary")).toBeInTheDocument();
    expect(screen.getByText("Summary body")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-overview")).not.toBeInTheDocument();
    expect(screen.queryByText("Overview body")).not.toBeInTheDocument();
    expect(screen.queryByTestId("panel-lighthouse")).not.toBeInTheDocument();
    expect(screen.getByTestId("ai-summary-tab-control")).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("returns to overview from summary with exclusive content", async () => {
    const user = userEvent.setup();
    render(<TabHarness initial="summary" />);
    expect(screen.getByTestId("panel-summary")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Intelligence Overview/i }));
    expect(screen.getByTestId("panel-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-summary")).not.toBeInTheDocument();
  });
});
