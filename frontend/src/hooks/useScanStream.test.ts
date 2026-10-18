import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useScanStream } from "@/hooks/useScanStream";

function encodeSSE(payload: object): Uint8Array {
  const data = `data: ${JSON.stringify(payload)}\n\n`;
  return new TextEncoder().encode(data);
}

function makeStreamResponse(events: object[], ok = true): Response {
  const chunks = events.map(encodeSSE);
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(chunks[i++]);
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream, {
    status: ok ? 200 : 401,
    headers: { "Content-Type": "text/event-stream" },
  });
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useScanStream - fetch SSE lifecycle", () => {
  it("starts in idle state when active=false", () => {
    const { result } = renderHook(() => useScanStream("scan_test", false));
    expect(result.current.connectionState).toBe("idle");
    expect(result.current.latestEvent).toBeNull();
  });

  it("opens an authenticated fetch stream when active=true", async () => {
    fetchMock.mockResolvedValueOnce(makeStreamResponse([]));
    renderHook(() => useScanStream("scan_test", true));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/scans/scan_test/stream");
    expect(init.headers).toMatchObject({ Accept: "text/event-stream" });
  });

  it("parses SSE data events into latestEvent", async () => {
    fetchMock.mockResolvedValueOnce(
      makeStreamResponse([
        {
          scan_id: "scan_test",
          status: "crawling",
          progress_percent: 30,
          current_step: "crawling",
          message: "Status: crawling",
          timestamp: new Date().toISOString(),
        },
      ])
    );
    const { result } = renderHook(() => useScanStream("scan_test", true));
    await waitFor(() => expect(result.current.latestEvent?.status).toBe("crawling"));
    expect(result.current.eventLog.length).toBeGreaterThanOrEqual(1);
  });

  it("closes on terminal status completed", async () => {
    fetchMock.mockResolvedValueOnce(
      makeStreamResponse([
        {
          scan_id: "scan_test",
          status: "completed",
          progress_percent: 100,
          current_step: "completed",
          message: "done",
          timestamp: new Date().toISOString(),
        },
      ])
    );
    const { result } = renderHook(() => useScanStream("scan_test", true));
    await waitFor(() => expect(result.current.connectionState).toBe("closed"));
  });

  it("falls back to polling when stream returns non-OK", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValue({
        ok: true,
        json: async () => ({
          scan_id: "scan_test",
          status: "pending",
          progress_percent: 5,
          created_at: new Date().toISOString(),
          target_url: "https://example.com",
          patches: [],
          intents: [],
          contradictions: [],
        }),
      });
    const { result } = renderHook(() => useScanStream("scan_test", true));
    await waitFor(() => expect(result.current.connectionState).toBe("error"), {
      timeout: 3000,
    });
  });
});
