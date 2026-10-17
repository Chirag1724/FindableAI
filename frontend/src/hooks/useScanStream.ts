"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { ScanStatusEvent, ScanStatus } from "@/types/scan";
import { getScan } from "@/lib/api";
import { getAuthHeaders } from "@/lib/authHeaders";
import { deriveUiScanStatus } from "@/lib/pipelineStatus";

export type StreamConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "error";

const TERMINAL: ScanStatus[] = ["completed", "failed"];
const POLL_INTERVAL_MS = 2000;
const EVENT_LOG_CAP = 200;

export interface ScanStreamResult {
  latestEvent: ScanStatusEvent | null;
  eventLog: ScanStatusEvent[];
  connectionState: StreamConnectionState;
  lastGoodStatus: ScanStatus | null;
}

/**
 * Opens an authenticated SSE stream for a scanId when `active` is true.
 *
 * Uses fetch + ReadableStream (not EventSource) so ``X-API-Key`` /
 * ``Authorization`` headers can be sent. Auth is re-validated on every
 * reconnect because each connection is a new HTTP request.
 *
 * Falls back to polling GET /api/v1/scans/{id} every 2s on stream error.
 * Safe under React 18 StrictMode double-effects.
 */
export function useScanStream(
  scanId: string | null,
  active: boolean
): ScanStreamResult {
  const [latestEvent, setLatestEvent] = useState<ScanStatusEvent | null>(null);
  const [eventLog, setEventLog] = useState<ScanStatusEvent[]>([]);
  const [connectionState, setConnectionState] =
    useState<StreamConnectionState>("idle");
  const [lastGoodStatus, setLastGoodStatus] = useState<ScanStatus | null>(null);

  const streamAbortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const activeRef = useRef(active);
  const lastSeqRef = useRef<number>(-1);
  const streamingRef = useRef(false);
  activeRef.current = active;

  const pushEvent = useCallback((event: ScanStatusEvent) => {
    if (!isMountedRef.current) return;
    if (typeof event.seq === "number" && event.seq >= 0) {
      if (event.seq < lastSeqRef.current) {
        return;
      }
      lastSeqRef.current = event.seq;
    }
    setLatestEvent(event);
    if (event.status !== "failed") {
      setLastGoodStatus(event.status);
    }
    setEventLog((prev) => {
      const next = [...prev, event];
      return next.length > EVENT_LOG_CAP
        ? next.slice(next.length - EVENT_LOG_CAP)
        : next;
    });
  }, []);

  const stopPoll = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }, []);

  const stopStream = useCallback(() => {
    if (streamAbortRef.current) {
      streamAbortRef.current.abort();
      streamAbortRef.current = null;
    }
    streamingRef.current = false;
    stopPoll();
  }, [stopPoll]);

  const startPolling = useCallback(
    (id: string) => {
      if (pollRef.current !== null) return;
      if (!isMountedRef.current) return;

      setConnectionState("error");

      const poll = async () => {
        if (!isMountedRef.current || !activeRef.current) {
          stopPoll();
          return;
        }
        const ac = new AbortController();
        abortRef.current = ac;
        try {
          const scan = await getScan(id, ac.signal);
          if (!isMountedRef.current) return;
          const durablePercent =
            typeof scan.progress_percent === "number"
              ? scan.progress_percent
              : TERMINAL.includes(scan.status)
                ? 100
                : 0;
          const uiStatus = deriveUiScanStatus({
            status: scan.status,
            progressStage: scan.progress_stage,
            progressMessage: scan.progress_message,
            progressPercent: durablePercent,
            jobStatus: scan.job_status,
          });
          const synth: ScanStatusEvent = {
            scan_id: scan.scan_id,
            status: uiStatus,
            progress_percent: durablePercent,
            current_step: scan.progress_stage || scan.status,
            message:
              scan.progress_message ||
              scan.error ||
              `Polled status: ${scan.status}`,
            timestamp: new Date().toISOString(),
            seq: scan.progress_seq ?? null,
            progress_current: scan.progress_current ?? null,
            progress_total: scan.progress_total ?? null,
          };
          pushEvent(synth);
          if (TERMINAL.includes(scan.status)) {
            stopPoll();
            if (isMountedRef.current) setConnectionState("closed");
          }
        } catch {
          // keep polling
        }
      };

      void poll();
      pollRef.current = setInterval(() => void poll(), POLL_INTERVAL_MS);
    },
    [pushEvent, stopPoll]
  );

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!scanId || !active) {
      stopStream();
      if (!active) setConnectionState("idle");
      return;
    }

    if (streamingRef.current) return;

    setConnectionState("connecting");
    streamingRef.current = true;

    const priorSeq = lastSeqRef.current >= 0 ? lastSeqRef.current : null;
    const streamUrl =
      priorSeq != null
        ? `/api/v1/scans/${scanId}/stream?last_event_id=${priorSeq}`
        : `/api/v1/scans/${scanId}/stream`;

    const ac = new AbortController();
    streamAbortRef.current = ac;

    const run = async () => {
      try {
        const res = await fetch(streamUrl, {
          method: "GET",
          headers: {
            Accept: "text/event-stream",
            ...getAuthHeaders(),
          },
          signal: ac.signal,
        });
        if (!res.ok || !res.body) {
          throw new Error(`stream_http_${res.status}`);
        }
        if (!isMountedRef.current) return;
        setConnectionState("open");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";
          for (const chunk of chunks) {
            const dataLines = chunk
              .split("\n")
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trimStart());
            if (dataLines.length === 0) continue;
            const raw = dataLines.join("\n");
            let parsed: ScanStatusEvent;
            try {
              parsed = JSON.parse(raw) as ScanStatusEvent;
            } catch {
              continue;
            }
            pushEvent(parsed);
            if (TERMINAL.includes(parsed.status)) {
              ac.abort();
              streamingRef.current = false;
              if (isMountedRef.current) setConnectionState("closed");
              return;
            }
          }
        }
        streamingRef.current = false;
        if (isMountedRef.current && activeRef.current) {
          startPolling(scanId);
        }
      } catch (err) {
        if (ac.signal.aborted) return;
        streamingRef.current = false;
        if (isMountedRef.current && activeRef.current) {
          startPolling(scanId);
        }
      }
    };

    void run();

    return () => {
      stopStream();
    };
  }, [scanId, active, pushEvent, stopStream, startPolling]);

  return { latestEvent, eventLog, connectionState, lastGoodStatus };
}
