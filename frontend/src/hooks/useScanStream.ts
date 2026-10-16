"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { ScanStatusEvent, ScanStatus } from "@/types/scan";
import { getScan } from "@/lib/api";

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
 * Opens an EventSource for a scanId when `active` is true.
 * Parses each event safely (bad JSON does not crash).
 * Closes on completed/failed and on unmount.
 * Falls back to polling GET /api/v1/scans/{id} every 2s on SSE error.
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

  // Refs to hold mutable state without triggering re-renders
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const activeRef = useRef(active);
  const lastSeqRef = useRef<number>(-1);
  activeRef.current = active;

  const pushEvent = useCallback((event: ScanStatusEvent) => {
    if (!isMountedRef.current) return;
    // Ignore stale snapshots (lower seq) so refresh/poll cannot rewind progress.
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
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    stopPoll();
  }, [stopPoll]);

  const startPolling = useCallback(
    (id: string) => {
      if (pollRef.current !== null) return; // already polling
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
          // Prefer durable progress fields from PostgreSQL — never fabricate mid-run %.
          const durablePercent =
            typeof scan.progress_percent === "number"
              ? scan.progress_percent
              : TERMINAL.includes(scan.status)
                ? 100
                : 0;
          const synth: ScanStatusEvent = {
            scan_id: scan.scan_id,
            status: scan.status,
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
          // Network error during poll - keep trying unless unmounted
        }
      };

      // Run immediately, then repeat
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

    // Guard against StrictMode double-invocation: if a stream is already open for this id, skip
    if (esRef.current) return;

    lastSeqRef.current = -1;
    setConnectionState("connecting");

    const es = new EventSource(`/api/v1/scans/${scanId}/stream`);
    esRef.current = es;

    es.onopen = () => {
      if (!isMountedRef.current) return;
      setConnectionState("open");
    };

    es.onmessage = (ev: MessageEvent<string>) => {
      if (!isMountedRef.current) return;
      let parsed: ScanStatusEvent;
      try {
        parsed = JSON.parse(ev.data) as ScanStatusEvent;
      } catch {
        return; // Bad JSON - skip silently
      }
      pushEvent(parsed);
      if (TERMINAL.includes(parsed.status)) {
        // Stream is done - close manually (server also closes but EventSource auto-reconnects)
        es.close();
        esRef.current = null;
        if (isMountedRef.current) setConnectionState("closed");
      }
    };

    es.onerror = () => {
      if (!isMountedRef.current) return;
      es.close();
      esRef.current = null;
      // Fall back to polling
      if (isMountedRef.current && activeRef.current) {
        startPolling(scanId);
      }
    };

    return () => {
      stopStream();
    };
  }, [scanId, active, pushEvent, stopStream, startPolling]);

  return { latestEvent, eventLog, connectionState, lastGoodStatus };
}