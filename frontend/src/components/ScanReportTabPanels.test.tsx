import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ScanReportTabPanels } from "@/components/ScanReportTabPanels";
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
      </div>
      <ScanReportTabPanels
        activeTab={activeTab}
        overview={<div>Overview body</div>}
        lighthouse={<div>Lighthouse body</div>}
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
  });

  it("switches to lighthouse without leaving overview mounted", async () => {
    const user = userEvent.setup();
    render(<TabHarness />);
    await user.click(screen.getByRole("tab", { name: /AI Lighthouse/i }));
    expect(screen.getByTestId("panel-lighthouse")).toBeInTheDocument();
    expect(screen.getByText("Lighthouse body")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-overview")).not.toBeInTheDocument();
  });

  it("switches back from lighthouse to overview with exclusive content", async () => {
    const user = userEvent.setup();
    render(<TabHarness initial="lighthouse" />);
    expect(screen.getByTestId("panel-lighthouse")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Intelligence Overview/i }));
    expect(screen.getByTestId("panel-overview")).toBeInTheDocument();
    expect(screen.queryByTestId("panel-lighthouse")).not.toBeInTheDocument();
  });
});
