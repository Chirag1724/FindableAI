import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  formatScore,
  formatPercent,
  formatDuration,
  formatRelativeTime,
  truncate,
  gradeColor,
  scanStatusMeta,
  entailmentStatusMeta,
} from "@/lib/format";
import type { ScanStatus, EntailmentStatus } from "@/types/scan";

// --- formatScore ---

describe("formatScore", () => {
  it("formats 78.4 as '78.4'", () => expect(formatScore(78.4)).toBe("78.4"));
  it("formats 100 as '100.0'", () => expect(formatScore(100)).toBe("100.0"));
  it("formats 0 as '0.0'", () => expect(formatScore(0)).toBe("0.0"));
  it("rounds to 1 decimal", () => expect(formatScore(78.456)).toBe("78.5"));
});

// --- formatPercent ---

describe("formatPercent", () => {
  it("formats 78.4 as '78.4%'", () => expect(formatPercent(78.4)).toBe("78.4%"));
  it("respects decimals=0", () => expect(formatPercent(78.4, 0)).toBe("78%"));
  it("formats 100 as '100.0%'", () => expect(formatPercent(100)).toBe("100.0%"));
});

// --- formatDuration ---

describe("formatDuration", () => {
  it("formats sub-60s as seconds", () => expect(formatDuration(8.4)).toBe("8.4s"));
  it("formats exactly 60s as '1m 0s'", () => expect(formatDuration(60)).toBe("1m 0s"));
  it("formats 90s as '1m 30s'", () => expect(formatDuration(90)).toBe("1m 30s"));
  it("formats 3661s as '61m 1s'", () => expect(formatDuration(3661)).toBe("61m 1s"));
});

// --- formatRelativeTime ---

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-27T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns 'just now' for < 5s ago", () => {
    expect(formatRelativeTime("2026-09-27T11:59:57Z")).toBe("just now");
  });

  it("returns seconds ago for < 60s", () => {
    expect(formatRelativeTime("2026-09-27T11:59:30Z")).toBe("30s ago");
  });

  it("returns minutes ago for < 60m", () => {
    expect(formatRelativeTime("2026-09-27T11:45:00Z")).toBe("15m ago");
  });

  it("returns hours ago for < 24h", () => {
    expect(formatRelativeTime("2026-09-27T06:00:00Z")).toBe("6h ago");
  });

  it("returns the raw string for an invalid date", () => {
    expect(formatRelativeTime("not-a-date")).toBe("not-a-date");
  });
});

// --- truncate ---

describe("truncate", () => {
  it("returns original string when short enough", () => {
    expect(truncate("hello", 10)).toBe("hello");
  });

  it("truncates and appends ellipsis", () => {
    const r = truncate("hello world", 8);
    expect(r).toHaveLength(8);
    expect(r).toMatch(/\u2026$/);
  });

  it("handles exact length boundary", () => {
    expect(truncate("abcde", 5)).toBe("abcde");
  });
});

// --- gradeColor ---

describe("gradeColor", () => {
  it("S returns amber", () => expect(gradeColor("S")).toContain("amber"));
  it("A returns emerald", () => expect(gradeColor("A")).toContain("emerald"));
  it("A+ returns emerald", () => expect(gradeColor("A+")).toContain("emerald"));
  it("B returns violet", () => expect(gradeColor("B")).toContain("violet"));
  it("B+ returns violet", () => expect(gradeColor("B+")).toContain("violet"));
  it("A- returns violet", () => expect(gradeColor("A-")).toContain("violet"));
  it("C returns sky", () => expect(gradeColor("C")).toContain("sky"));
  it("C+ returns sky", () => expect(gradeColor("C+")).toContain("sky"));
  it("B- returns sky", () => expect(gradeColor("B-")).toContain("sky"));
  it("D returns amber", () => expect(gradeColor("D")).toContain("amber"));
  it("D+ returns amber", () => expect(gradeColor("D+")).toContain("amber"));
  it("C- returns amber", () => expect(gradeColor("C-")).toContain("amber"));
  it("F returns rose (default)", () => expect(gradeColor("F")).toContain("rose"));
  it("unknown returns rose", () => expect(gradeColor("Z")).toContain("rose"));
  it("is case-insensitive", () => expect(gradeColor("a")).toContain("emerald"));
});

// --- scanStatusMeta ---

const ALL_SCAN_STATUSES: ScanStatus[] = [
  "pending",
  "crawling",
  "extracting_dom",
  "synthesizing_intents",
  "hybrid_retrieval",
  "nli_evaluation",
  "computing_fscore",
  "generating_patches",
  "completed",
  "failed",
];

describe("scanStatusMeta", () => {
  for (const status of ALL_SCAN_STATUSES) {
    it(`returns a valid StatusMeta for '${status}'`, () => {
      const meta = scanStatusMeta(status);
      expect(meta).toHaveProperty("label");
      expect(meta).toHaveProperty("iconName");
      expect(meta).toHaveProperty("classes");
      expect(meta).toHaveProperty("dotClass");
      expect(typeof meta.label).toBe("string");
      expect(meta.label.length).toBeGreaterThan(0);
    });
  }

  it("'completed' has emerald color", () => {
    expect(scanStatusMeta("completed").classes).toContain("emerald");
  });

  it("'failed' has rose color", () => {
    expect(scanStatusMeta("failed").classes).toContain("rose");
  });
});

// --- entailmentStatusMeta ---

const ALL_ENTAILMENT_STATUSES: EntailmentStatus[] = [
  "SUPPORTED",
  "PARTIALLY_SUPPORTED",
  "CONTRADICTED",
  "UNKNOWN",
];

describe("entailmentStatusMeta", () => {
  for (const status of ALL_ENTAILMENT_STATUSES) {
    it(`returns a valid StatusMeta for '${status}'`, () => {
      const meta = entailmentStatusMeta(status);
      expect(meta).toHaveProperty("label");
      expect(meta).toHaveProperty("iconName");
      expect(meta).toHaveProperty("classes");
      expect(typeof meta.label).toBe("string");
    });
  }

  it("SUPPORTED is emerald", () => {
    expect(entailmentStatusMeta("SUPPORTED").classes).toContain("emerald");
  });

  it("CONTRADICTED is rose", () => {
    expect(entailmentStatusMeta("CONTRADICTED").classes).toContain("rose");
  });

  it("UNKNOWN is amber", () => {
    expect(entailmentStatusMeta("UNKNOWN").classes).toContain("amber");
  });

  it("PARTIALLY_SUPPORTED is sky", () => {
    expect(entailmentStatusMeta("PARTIALLY_SUPPORTED").classes).toContain("sky");
  });
});