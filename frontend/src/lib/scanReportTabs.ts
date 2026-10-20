/** Scan-detail report view tabs — mutually exclusive panels. */

export type ScanReportTab = "overview" | "lighthouse";

export function parseScanReportTab(param: string | null | undefined): ScanReportTab {
  if (param === "lighthouse") return "lighthouse";
  return "overview";
}

export function scanReportTabHref(scanId: string, tab: ScanReportTab): string {
  if (tab === "lighthouse") return `/scans/${scanId}?tab=lighthouse`;
  return `/scans/${scanId}`;
}

/** Only the active tab's panel may render. */
export function isScanReportPanelActive(
  activeTab: ScanReportTab,
  panel: ScanReportTab
): boolean {
  return activeTab === panel;
}
