import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useScanStream } from "@/hooks/useScanStream";

// --- EventSource mock factory ---

type MockES = {
  onopen: ((e: Event) => void) | null;
  onmessage: ((e: MessageEvent) => void) | null;
  onerror: ((e: Event) => void) | null;
  close: ReturnType<typeof vi.fn>;
  url: string;
};

let lastES: MockES | null = null;

function makeMockES(url: string): MockES {
  const es: MockES = {
    url,
    onopen: null,
    onmessage: null,
    onerror: null,
    close: vi.fn(),
  };
  lastES = es;
  return es;
}

// Mock fetch for polling fallback
const fetchMock = vi.fn();

beforeEach(() => {
  lastES = null;
  fetchMock.mockReset();
  vi.stubGlobal("EventSource", vi.fn().mockImplementation((url: string) => makeMockES(url)));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// --- Helpers ---

function makeEvent(status: string, progress = 50): string {
  return JSON.stringify({
    scan_id: "scan_test",
    status,
    progress_percent: progress,
    current_step: status,
    message: `Status: ${status}`,
    timestamp: new Date().toISOString(),
  });
}

// --- Tests ---

describe("useScanStream - connection lifecycle", () => {
  it("starts in idle state when active=false", () => {
    const { result } = renderHook(() => useScanStream("scan_test", false));
    expect(result.current.connectionState).toBe("idle");
    expect(result.current.latestEvent).toBeNull();
  });

  it("opens an EventSource when active=true", () => {
    renderHook(() => useScanStream("scan_test", true));
    expect(vi.mocked(EventSource)).toHaveBeenCalledWith("/api/v1/scans/scan_test/stream");
  });

  it("transitions to 'open' when onopen fires", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => { lastES!.onopen!(new Event("open")); });
    await waitFor(() => expect(result.current.connectionState).toBe("open"));
  });

  it("parses incoming messages and populates latestEvent", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => {
      lastES!.onmessage!({ data: makeEvent("crawling", 30) } as MessageEvent);
    });
    await waitFor(() => expect(result.current.latestEvent?.status).toBe("crawling"));
    expect(result.current.eventLog).toHaveLength(1);
  });

  it("closes on terminal status 'completed'", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => {
      lastES!.onmessage!({ data: makeEvent("completed", 100) } as MessageEvent);
    });
    await waitFor(() => expect(result.current.connectionState).toBe("closed"));
    expect(lastES!.close).toHaveBeenCalled();
  });

  it("closes on terminal status 'failed'", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => {
      lastES!.onmessage!({ data: makeEvent("failed", 100) } as MessageEvent);
    });
    await waitFor(() => expect(result.current.connectionState).toBe("closed"));
  });

  it("does not update lastGoodStatus when status is 'failed'", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => {
      lastES!.onmessage!({ data: makeEvent("crawling", 20) } as MessageEvent);
    });
    act(() => {
      lastES!.onmessage!({ data: makeEvent("failed", 100) } as MessageEvent);
    });
    await waitFor(() => expect(result.current.lastGoodStatus).toBe("crawling"));
  });
});

describe("useScanStream - error fallback to polling", () => {
  it("transitions to 'error' and starts polling on onerror", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        scan_id: "scan_test",
        status: "nli_evaluation",
        created_at: new Date().toISOString(),
        patches: [],
        target_url: "https://example.com",
        progress_percent: 85,
        progress_stage: "NLI Entailment Classifier",
        progress_message: "Evaluating claims",
        progress_seq: 12,
      }),
    });

    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => { lastES!.onerror!(new Event("error")); });
    await waitFor(() => expect(result.current.connectionState).toBe("error"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(result.current.latestEvent?.progress_percent).toBe(85)
    );
    expect(result.current.latestEvent?.current_step).toBe(
      "NLI Entailment Classifier"
    );
  });

  it("does not fabricate mid-run progress percent when durable fields missing", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        scan_id: "scan_test",
        status: "crawling",
        created_at: new Date().toISOString(),
        patches: [],
        target_url: "https://example.com",
      }),
    });

    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => { lastES!.onerror!(new Event("error")); });
    await waitFor(() =>
      expect(result.current.latestEvent?.progress_percent).toBe(0)
    );
  });

  it("stops polling when polled status is 'completed'", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        scan_id: "scan_test",
        status: "completed",
        created_at: new Date().toISOString(),
        patches: [],
        target_url: "https://example.com",
      }),
    });

    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => { lastES!.onerror!(new Event("error")); });
    await waitFor(() => expect(result.current.connectionState).toBe("closed"));
  });
});

describe("useScanStream - unmount cleanup", () => {
  it("closes EventSource on unmount without error", async () => {
    const { unmount } = renderHook(() => useScanStream("scan_test", true));
    expect(() => unmount()).not.toThrow();
    expect(lastES!.close).toHaveBeenCalled();
  });

  it("silently ignores bad JSON in messages", async () => {
    const { result } = renderHook(() => useScanStream("scan_test", true));
    act(() => {
      lastES!.onmessage!({ data: "{{not valid json}}" } as MessageEvent);
    });
    // Should remain null - bad message is skipped
    expect(result.current.latestEvent).toBeNull();
  });
});