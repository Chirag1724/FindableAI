import { describe, expect, it } from "vitest";
import {
  isScanReportPanelActive,
  parseScanReportTab,
  scanReportTabHref,
  type ScanReportTab,
} from "@/lib/scanReportTabs";

describe("parseScanReportTab", () => {
  it("defaults to overview", () => {
    expect(parseScanReportTab(null)).toBe("overview");
    expect(parseScanReportTab(undefined)).toBe("overview");
    expect(parseScanReportTab("")).toBe("overview");
    expect(parseScanReportTab("other")).toBe("overview");
  });

  it("accepts lighthouse and summary", () => {
    expect(parseScanReportTab("lighthouse")).toBe("lighthouse");
    expect(parseScanReportTab("summary")).toBe("summary");
  });
});

describe("scanReportTabHref", () => {
  it("builds stable URLs per tab", () => {
    expect(scanReportTabHref("scan_abc", "overview")).toBe("/scans/scan_abc");
    expect(scanReportTabHref("scan_abc", "lighthouse")).toBe(
      "/scans/scan_abc?tab=lighthouse"
    );
    expect(scanReportTabHref("scan_abc", "summary")).toBe(
      "/scans/scan_abc?tab=summary"
    );
  });
});

describe("isScanReportPanelActive", () => {
  const tabs: ScanReportTab[] = ["overview", "lighthouse", "summary"];

  it("activates exactly one panel for each selected tab", () => {
    for (const active of tabs) {
      const visible = tabs.filter((panel) =>
        isScanReportPanelActive(active, panel)
      );
      expect(visible).toEqual([active]);
    }
  });
});
