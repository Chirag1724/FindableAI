import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useScanData } from "@/hooks/useScanData";

// --- Mock the api module ---

vi.mock("@/lib/api", () => ({
  getScan: vi.fn(),
  getIntents: vi.fn(),
  getContradictions: vi.fn(),
  getPatches: vi.fn(),
}));

import * as api from "@/lib/api";

const COMPLETED_SCAN = {
  scan_id: "scan_test",
  target_url: "https://example.com",
  status: "completed" as const,
  created_at: "2026-09-27T00:00:00Z",
  patches: [],
};

const PENDING_SCAN = {
  ...COMPLETED_SCAN,
  status: "pending" as const,
};

const MOCK_INTENTS = [
  {
    intent_id: "int_1",
    query: "Does it work?",
    category: "availability" as const,
    status: "SUPPORTED" as const,
    reasoning: "Yes",
    evidence: [],
    confidence: 0.9,
  },
];

const MOCK_CONTRADICTIONS = [
  {
    contradiction_id: "con_1",
    entity: "hours",
    conflict: "10 PM vs 9 PM",
    values: ["10 PM", "9 PM"],
    severity: "HARD_CONTRADICTION" as const,
    source_urls: [],
    dom_paths: [],
  },
];

const MOCK_PATCHES = [
  {
    patch_id: "patch_1",
    patch_type: "schema_microdata" as const,
    title: "Add JSON-LD",
    rationale: "Missing schema",
    impact_score_delta: 5.0,
    dom_anchor: { css_selector: "head", tag_name: "head", original_snippet: "", suggested_snippet: "" },
    unified_diff: "",
    applied: false,
  },
];

beforeEach(() => {
  vi.mocked(api.getScan).mockResolvedValue(COMPLETED_SCAN as ReturnType<typeof api.getScan> extends Promise<infer T> ? T : never);
  vi.mocked(api.getIntents).mockResolvedValue(MOCK_INTENTS);
  vi.mocked(api.getContradictions).mockResolvedValue(MOCK_CONTRADICTIONS);
  vi.mocked(api.getPatches).mockResolvedValue(MOCK_PATCHES);
});

afterEach(() => {
  vi.clearAllMocks();
});

// --- Tests ---

describe("useScanData - initial state", () => {
  it("starts with all resources in loading=false, data=null state", () => {
    const { result } = renderHook(() => useScanData(null, false));
    expect(result.current.scan.data).toBeNull();
    expect(result.current.scan.loading).toBe(false);
    expect(result.current.intents.data).toBeNull();
  });

  it("does not fetch when triggerFetch=false", async () => {
    renderHook(() => useScanData("scan_test", false));
    await new Promise((r) => setTimeout(r, 50));
    expect(api.getScan).not.toHaveBeenCalled();
  });
});

describe("useScanData - completed scan", () => {
  it("fetches scan and all three resources in parallel", async () => {
    const { result } = renderHook(() => useScanData("scan_test", true));
    await waitFor(() => expect(result.current.scan.loading).toBe(false));
    await waitFor(() => expect(result.current.intents.data).not.toBeNull());
    await waitFor(() => expect(result.current.contradictions.data).not.toBeNull());
    await waitFor(() => expect(result.current.patches.data).not.toBeNull());
    expect(api.getIntents).toHaveBeenCalledWith("scan_test", expect.any(AbortSignal));
    expect(api.getContradictions).toHaveBeenCalledWith("scan_test", expect.any(AbortSignal));
    expect(api.getPatches).toHaveBeenCalledWith("scan_test", expect.any(AbortSignal));
  });

  it("normalizes intents from raw shape", async () => {
    const { result } = renderHook(() => useScanData("scan_test", true));
    await waitFor(() => expect(result.current.intents.data).not.toBeNull());
    expect(result.current.intents.data).toHaveLength(1);
    expect(result.current.intents.data![0]!.status).toBe("SUPPORTED");
  });
});

describe("useScanData - pending scan", () => {
  it("does not fetch intents/contradictions/patches when status is not completed", async () => {
    vi.mocked(api.getScan).mockResolvedValue(PENDING_SCAN as ReturnType<typeof api.getScan> extends Promise<infer T> ? T : never);
    const { result } = renderHook(() => useScanData("scan_test", true));
    await waitFor(() => expect(result.current.scan.data?.status).toBe("pending"));
    expect(api.getIntents).not.toHaveBeenCalled();
    expect(api.getContradictions).not.toHaveBeenCalled();
    expect(api.getPatches).not.toHaveBeenCalled();
  });
});

describe("useScanData - one endpoint failing", () => {
  it("does not prevent other endpoints from succeeding (Promise.allSettled)", async () => {
    vi.mocked(api.getIntents).mockRejectedValue(new Error("Intents service down"));
    // contradictions and patches should still resolve

    const { result } = renderHook(() => useScanData("scan_test", true));
    await waitFor(() => expect(result.current.contradictions.data).not.toBeNull());
    await waitFor(() => expect(result.current.patches.data).not.toBeNull());
    // intents should have error
    await waitFor(() => expect(result.current.intents.error).toBe("Intents service down"));
    // contradictions and patches still populated
    expect(result.current.contradictions.data).not.toBeNull();
    expect(result.current.patches.data).not.toBeNull();
  });
});

describe("useScanData - scan fetch failure", () => {
  it("sets scan.error when getScan throws", async () => {
    vi.mocked(api.getScan).mockRejectedValue(new Error("Scan not found"));
    const { result } = renderHook(() => useScanData("scan_test", true));
    await waitFor(() => expect(result.current.scan.error).toBe("Scan not found"));
    expect(result.current.scan.loading).toBe(false);
    // secondary resources should not have been fetched
    expect(api.getIntents).not.toHaveBeenCalled();
  });
});

describe("useScanData - unmount", () => {
  it("does not throw on unmount during in-flight request", async () => {
    vi.mocked(api.getScan).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve(COMPLETED_SCAN as ReturnType<typeof api.getScan> extends Promise<infer T> ? T : never), 200))
    );
    const { unmount } = renderHook(() => useScanData("scan_test", true));
    expect(() => unmount()).not.toThrow();
  });
});