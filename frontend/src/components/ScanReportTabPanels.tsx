import type { ReactNode } from "react";
import {
  isScanReportPanelActive,
  type ScanReportTab,
} from "@/lib/scanReportTabs";

export interface ScanReportTabPanelsProps {
  activeTab: ScanReportTab;
  overview: ReactNode;
  lighthouse: ReactNode;
  summary: ReactNode;
}

/**
 * Renders exactly one scan-report panel for the selected tab.
 * Prevents AI Summary from stacking on top of Overview/Lighthouse.
 */
export function ScanReportTabPanels({
  activeTab,
  overview,
  lighthouse,
  summary,
}: ScanReportTabPanelsProps) {
  return (
    <div data-testid="scan-report-tab-panels" data-active-tab={activeTab}>
      {isScanReportPanelActive(activeTab, "overview") && (
        <div
          role="tabpanel"
          id="panel-overview"
          aria-labelledby="tab-overview"
          data-testid="panel-overview"
          className="space-y-8 sm:space-y-10 animate-fade-in"
        >
          {overview}
        </div>
      )}
      {isScanReportPanelActive(activeTab, "lighthouse") && (
        <div
          role="tabpanel"
          id="panel-lighthouse"
          aria-labelledby="tab-lighthouse"
          data-testid="panel-lighthouse"
          className="animate-fade-in"
        >
          {lighthouse}
        </div>
      )}
      {isScanReportPanelActive(activeTab, "summary") && (
        <div
          role="tabpanel"
          id="panel-summary"
          aria-labelledby="tab-summary"
          data-testid="panel-summary"
          className="animate-fade-in"
        >
          {summary}
        </div>
      )}
    </div>
  );
}
