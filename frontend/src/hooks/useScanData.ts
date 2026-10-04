"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  ScanResponse, IntentEvaluation, Contradiction, PatchProposal,
} from "@/types/scan";
import { getScan, getIntents, getContradictions, getPatches } from "@/lib/api";
import { normalizeIntents, normalizeContradictions } from "@/lib/normalize";

export interface ResourceState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  retry: () => void;
}

export interface ScanDataResult {
  scan: ResourceState<ScanResponse>;
  intents: ResourceState<IntentEvaluation[]>;
  contradictions: ResourceState<Contradiction[]>;
  patches: ResourceState<PatchProposal[]>;
}

/**
 * Once a scanId is provided:
 * 1. Fetches scan metadata immediately.
 * 2. If status is completed, fetches intents/contradictions/patches in parallel.
 * Uses Promise.allSettled so one failing endpoint does not blank the rest.
 * Aborts in-flight requests on unmount or scanId change.
 */
export function useScanData(
  scanId: string | null,
  triggerFetch: boolean
): ScanDataResult {
  const [scan, setScan] = useState<ResourceState<ScanResponse>>({
    data: null,
    loading: false,
    error: null,
    retry: () => { },
  });
  const [intents, setIntents] = useState<ResourceState<IntentEvaluation[]>>({
    data: null,
    loading: false,
    error: null,
    retry: () => { },
  });
  const [contradictions, setContradictions] = useState<
    ResourceState<Contradiction[]>
  >({
    data: null,
    loading: false,
    error: null,
    retry: () => { },
  });
  const [patches, setPatches] = useState<ResourceState<PatchProposal[]>>({
    data: null,
    loading: false,
    error: null,
    retry: () => { },
  });

  const abortRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const fetchAll = useCallback(
    async (id: string) => {
      // Abort any previous in-flight requests
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      if (!isMountedRef.current) return;

      // Step 1: fetch scan
      setScan((s) => ({ ...s, loading: true, error: null }));
      let scanData: ScanResponse | null = null;
      try {
        scanData = await getScan(id, ac.signal);
        if (!isMountedRef.current) return;
        setScan({ data: scanData, loading: false, error: null, retry: () => void fetchAll(id) });
      } catch (err) {
        if (!isMountedRef.current) return;
        const msg = err instanceof Error ? err.message : String(err);
        setScan((s) => ({ ...s, loading: false, error: msg }));
        return;
      }

      // Step 2: if completed, fetch the rest in parallel
      if (scanData?.status !== "completed") return;

      setIntents((s) => ({ ...s, loading: true, error: null }));
      setContradictions((s) => ({ ...s, loading: true, error: null }));
      setPatches((s) => ({ ...s, loading: true, error: null }));

      const scanRepo = scanData?.repo_url || scanData?.github_repo_url || undefined;
      const [intentsResult, contradictionsResult, patchesResult] =
        await Promise.allSettled([
          getIntents(id, ac.signal),
          getContradictions(id, ac.signal),
          scanRepo ? getPatches(id, scanRepo, ac.signal) : getPatches(id, ac.signal),
        ]);

      if (!isMountedRef.current) return;

      if (intentsResult.status === "fulfilled") {
        const normalized = normalizeIntents(intentsResult.value);
        setIntents({
          data: normalized,
          loading: false,
          error: null,
          retry: () => void fetchAll(id),
        });
      } else {
        const msg =
          intentsResult.reason instanceof Error
            ? intentsResult.reason.message
            : String(intentsResult.reason);
        setIntents((s) => ({ ...s, loading: false, error: msg }));
      }

      if (contradictionsResult.status === "fulfilled") {
        const normalized = normalizeContradictions(contradictionsResult.value);
        setContradictions({
          data: normalized,
          loading: false,
          error: null,
          retry: () => void fetchAll(id),
        });
      } else {
        const msg =
          contradictionsResult.reason instanceof Error
            ? contradictionsResult.reason.message
            : String(contradictionsResult.reason);
        setContradictions((s) => ({ ...s, loading: false, error: msg }));
      }

      if (patchesResult.status === "fulfilled") {
        setPatches({
          data: patchesResult.value,
          loading: false,
          error: null,
          retry: () => void fetchAll(id),
        });
      } else {
        const msg =
          patchesResult.reason instanceof Error
            ? patchesResult.reason.message
            : String(patchesResult.reason);
        setPatches((s) => ({ ...s, loading: false, error: msg }));
      }
    },
    // fetchAll is stable except for id which is passed as param
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    if (!scanId || !triggerFetch) return;
    void fetchAll(scanId);
  }, [scanId, triggerFetch, fetchAll]);

  return { scan, intents, contradictions, patches };
}