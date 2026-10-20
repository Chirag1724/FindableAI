import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createScan,
  getScan,
  getIntents,
  getContradictions,
  getPatches,
  applyPatches,
  getHealth,
  getScanSummary,
  generateScanSummary,
} from "@/lib/api";

// --- Helpers ---

function mockFetchSuccess(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status,
      json: async () => body,
    } as unknown as Response)
  );
}

function mockFetchError(status: number, detail?: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status,
      json: async () => (detail ? { detail } : { message: "err" }),
    } as unknown as Response)
  );
}

function mockFetchJson(status: number, body: unknown, ok?: boolean) {
  const resolvedOk = ok ?? (status >= 200 && status < 300);
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: resolvedOk,
      status,
      json: async () => body,
    } as unknown as Response)
  );
}

function mockFetchNetworkFailure(message = "Network request failed") {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new Error(message))
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

// --- createScan ---

const MOCK_SCAN = {
  scan_id: "scan_abc123",
  target_url: "https://example.com",
  status: "pending",
  created_at: "2026-09-27T00:00:00Z",
  patches: [],
};

describe("createScan", () => {
  it("posts to /api/v1/scans and returns data on success", async () => {
    mockFetchSuccess(MOCK_SCAN);
    const result = await createScan({ url: "https://example.com" });
    expect(result.scan_id).toBe("scan_abc123");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/scans",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws ApiError with correct status on 400", async () => {
    mockFetchError(400, "Security rejection: blocked IP");
    await expect(createScan({ url: "http://127.0.0.1" })).rejects.toMatchObject({
      status: 400,
      message: "Security rejection: blocked IP",
    });
  });

  it("throws ApiError with status 0 on network failure", async () => {
    mockFetchNetworkFailure("Failed to fetch");
    await expect(createScan({ url: "https://example.com" })).rejects.toMatchObject({
      status: 0,
    });
  });
});

// --- getScan ---

describe("getScan", () => {
  it("fetches /api/v1/scans/:id and returns data", async () => {
    mockFetchSuccess({ ...MOCK_SCAN, status: "completed" });
    const result = await getScan("scan_abc123");
    expect(result.status).toBe("completed");
  });

  it("throws ApiError on 404", async () => {
    mockFetchError(404, "Scan not found");
    await expect(getScan("nonexistent")).rejects.toMatchObject({ status: 404 });
  });

  it("throws ApiError on network failure", async () => {
    mockFetchNetworkFailure();
    await expect(getScan("scan_abc123")).rejects.toMatchObject({ status: 0 });
  });
});

// --- getIntents ---

describe("getIntents", () => {
  it("returns an array on success", async () => {
    mockFetchSuccess([{ query: "test", status: "supported" }]);
    const result = await getIntents("scan_abc123");
    expect(Array.isArray(result)).toBe(true);
    expect(result).toHaveLength(1);
  });

  it("throws ApiError on 500", async () => {
    mockFetchError(500, "Internal server error");
    await expect(getIntents("scan_abc123")).rejects.toMatchObject({ status: 500 });
  });

  it("throws ApiError on network failure", async () => {
    mockFetchNetworkFailure();
    await expect(getIntents("scan_abc123")).rejects.toMatchObject({ status: 0 });
  });
});

// --- getContradictions ---

describe("getContradictions", () => {
  it("returns an array on success", async () => {
    mockFetchSuccess([{ contradiction_id: "con_1", severity: "hard_contradiction" }]);
    const result = await getContradictions("scan_abc123");
    expect(Array.isArray(result)).toBe(true);
  });

  it("throws ApiError on 422", async () => {
    mockFetchError(422, "Unprocessable entity");
    await expect(getContradictions("scan_abc123")).rejects.toMatchObject({ status: 422 });
  });

  it("throws on network failure", async () => {
    mockFetchNetworkFailure();
    await expect(getContradictions("scan_abc123")).rejects.toMatchObject({ status: 0 });
  });
});

// --- getPatches ---

describe("getPatches", () => {
  const PATCH = {
    patch_id: "patch_001",
    patch_type: "schema_microdata",
    title: "Add JSON-LD",
    rationale: "Missing schema",
    impact_score_delta: 5.0,
    dom_anchor: { css_selector: "head", tag_name: "head", original_snippet: "", suggested_snippet: "" },
    unified_diff: "--- a/index.html\n+++ b/index.html",
    applied: false,
  };

  it("returns patch array on success", async () => {
    mockFetchSuccess([PATCH]);
    const result = await getPatches("scan_abc123");
    expect(result).toHaveLength(1);
    expect(result[0]!.patch_id).toBe("patch_001");
  });

  it("throws ApiError on non-2xx without JSON detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => { throw new Error("not JSON"); },
      } as unknown as Response)
    );
    await expect(getPatches("scan_abc123")).rejects.toMatchObject({
      status: 503,
      message: expect.stringContaining("503"),
    });
  });
});

// --- applyPatches ---

describe("applyPatches", () => {
  const PR_RESULT = {
    pr_url: "https://github.com/org/repo/pull/42",
    pr_number: 42,
    branch_name: "findable-ai/patch-abc",
    title: "fix(discoverability): inject JSON-LD",
    created_at: "2026-09-27T00:00:00Z",
  };

  it("posts and returns PullRequestResult on success", async () => {
    mockFetchSuccess(PR_RESULT);
    const result = await applyPatches("scan_abc123");
    expect(result.pr_number).toBe(42);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/scans/scan_abc123/patches/apply",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws ApiError on 401", async () => {
    mockFetchError(401, "GitHub auth required");
    await expect(applyPatches("scan_abc123")).rejects.toMatchObject({ status: 401 });
  });

  it("throws on network failure", async () => {
    mockFetchNetworkFailure();
    await expect(applyPatches("scan_abc123")).rejects.toMatchObject({ status: 0 });
  });
});

// --- getHealth ---

describe("getHealth", () => {
  it("returns health response on success", async () => {
    mockFetchSuccess({ status: "ok", service: "findable-ai", version: "0.1.0" });
    const result = await getHealth();
    expect(result.status).toBe("ok");
    expect(result.service).toBe("findable-ai");
  });

  it("throws on non-2xx", async () => {
    mockFetchError(503, "Service unavailable");
    await expect(getHealth()).rejects.toMatchObject({ status: 503 });
  });

  it("throws on network failure", async () => {
    mockFetchNetworkFailure("Connection refused");
    await expect(getHealth()).rejects.toMatchObject({ status: 0, message: "Connection refused" });
  });
});

// --- scan summary ---

describe("getScanSummary", () => {
  it("GETs /scans/{id}/summary", async () => {
    mockFetchSuccess({ status: "none", coverage: { findings_included: 0 } });
    const result = await getScanSummary("scan_abc123");
    expect(result.status).toBe("none");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/scans/scan_abc123/summary",
      expect.any(Object)
    );
  });

  it("appends scope query parameter when provided", async () => {
    mockFetchSuccess({ status: "none", scope: "lighthouse" });
    const result = await getScanSummary("scan_abc123", undefined, "lighthouse");
    expect(result.scope).toBe("lighthouse");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/scans/scan_abc123/summary?scope=lighthouse",
      expect.any(Object)
    );
  });
});

describe("generateScanSummary", () => {
  it("returns body on 202 generating", async () => {
    mockFetchJson(202, {
      status: "generating",
      reason: "summary_generating",
      message: "In progress",
    });
    const result = await generateScanSummary("scan_abc123");
    expect(result.status).toBe("generating");
  });

  it("appends scope query parameter when generating lighthouse summary", async () => {
    mockFetchJson(200, {
      status: "ready",
      scope: "lighthouse",
    });
    const result = await generateScanSummary("scan_abc123", undefined, "lighthouse");
    expect(result.status).toBe("ready");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "/api/v1/scans/scan_abc123/summary?scope=lighthouse",
      expect.objectContaining({ method: "POST" })
    );
  });

  it("throws enriched ApiError on 409 ineligible", async () => {
    mockFetchJson(409, {
      status: "none",
      reason: "scan_failed",
      message: "Scan failed; summary is unavailable.",
    });
    await expect(generateScanSummary("scan_abc123")).rejects.toMatchObject({
      status: 409,
      message: "Scan failed; summary is unavailable.",
      body: { reason: "scan_failed" },
    });
  });

  it("throws enriched ApiError with retry_after on 429", async () => {
    mockFetchJson(429, {
      status: "failed",
      reason: "summary_rate_limited",
      message: "Rate limit exceeded.",
      retry_after: 120,
    });
    await expect(generateScanSummary("scan_abc123")).rejects.toMatchObject({
      status: 429,
      retry_after: 120,
      body: { reason: "summary_rate_limited" },
    });
  });
});