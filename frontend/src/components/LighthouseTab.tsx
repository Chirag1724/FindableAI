"use client";

import { useEffect, useState, useCallback } from "react";
import { Bot, FileCode2, Search, ShieldCheck, RefreshCw, AlertTriangle } from "lucide-react";
import type { LighthouseResponse } from "@/types/lighthouse";
import { getLighthouse } from "@/lib/api";
import { MOCK_LIGHTHOUSE_RESPONSE } from "@/lib/mockLighthouseData";
import { LighthouseGauge } from "./LighthouseGauge";
import { CrawlerGovernancePanel } from "./CrawlerGovernancePanel";
import { AuditChecklist } from "./AuditChecklist";

interface LighthouseTabProps {
  scanId: string;
}

export function LighthouseTab({ scanId }: LighthouseTabProps) {
  const [data, setData] = useState<LighthouseResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isUsingMock, setIsUsingMock] = useState<boolean>(false);

  const fetchLighthouse = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);

      try {
        const response = await getLighthouse(scanId, signal);
        setData(response);
        setIsUsingMock(false);
      } catch (err) {
        // ============================================================================
        // [MOCK_FALLBACK] Temporary Mock Fallback pending Backend Endpoint H-8.
        // When GET /api/v1/scans/{scan_id}/lighthouse is live in backend, this try/catch
        // fallback block can be removed and replaced with setError(err.message).
        // ============================================================================
        if (signal?.aborted) return;
        console.warn(
          `[FindableAI Lighthouse] Backend endpoint pending (H-8). Rendering against mock fixture for scan: ${scanId}`,
          err
        );
        setData(MOCK_LIGHTHOUSE_RESPONSE);
        setIsUsingMock(true);
        // ============================================================================
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [scanId]
  );

  useEffect(() => {
    const controller = new AbortController();
    void fetchLighthouse(controller.signal);
    return () => controller.abort();
  }, [fetchLighthouse]);

  if (loading && !data) {
    return (
      <div data-testid="lighthouse-tab-loading" className="space-y-6 animate-pulse">
        {/* Skeleton Gauges */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-64 rounded-xl bg-surface-secondary/40 shadow-border p-5 flex flex-col items-center justify-between"
            >
              <div className="h-5 w-24 rounded bg-white/5" />
              <div className="h-32 w-32 rounded-full bg-white/5" />
              <div className="h-5 w-16 rounded-full bg-white/5" />
            </div>
          ))}
        </div>

        {/* Skeleton Governance */}
        <div className="h-72 rounded-xl bg-surface-secondary/40 shadow-border p-6" />

        {/* Skeleton Audits */}
        <div className="h-96 rounded-xl bg-surface-secondary/40 shadow-border p-6" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div
        data-testid="lighthouse-tab-error"
        className="rounded-xl border border-rose-900/30 bg-rose-950/20 p-8 text-center space-y-4"
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
          <AlertTriangle size={24} aria-hidden="true" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-white">
            Failed to Load AI Lighthouse Data
          </h3>
          <p className="text-xs text-text-muted">{error}</p>
        </div>
        <button
          type="button"
          onClick={() => void fetchLighthouse()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-white/10 px-4 py-2 text-xs font-semibold text-white hover:bg-white/20 transition-colors"
        >
          <RefreshCw size={14} aria-hidden="true" />
          <span>Retry Assessment</span>
        </button>
      </div>
    );
  }

  if (!data) return null;

  const engines = data.engines;

  return (
    <div data-testid="lighthouse-tab" className="space-y-6 sm:space-y-8">
      {/* Mock Data Demo Banner (Only visible when fallback active) */}
      {isUsingMock && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-900/40 bg-amber-950/30 px-4 py-2.5 text-xs text-amber-300">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
            <span>
              <strong>AI Lighthouse Preview Mode:</strong> Rendering deterministic engine readiness models and governance rules.
            </span>
          </div>
          <span className="font-mono text-[11px] text-amber-400/80 hidden md:inline">
            API: /api/v1/scans/{scanId}/lighthouse
          </span>
        </div>
      )}

      {/* Row of 4 Per-Engine Gauges */}
      <section aria-labelledby="engine-scores-heading">
        <h2 id="engine-scores-heading" className="sr-only">
          Per-Engine AI Readiness Scores
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <LighthouseGauge
            label="ChatGPT"
            engineKey="chatgpt"
            score={engines.chatgpt?.score ?? 0}
            icon={Bot}
            accentColorClass="text-emerald-400"
            criteria={engines.chatgpt?.criteria}
          />
          <LighthouseGauge
            label="Gemini"
            engineKey="gemini"
            score={engines.gemini?.score ?? 0}
            icon={FileCode2}
            accentColorClass="text-sky-400"
            criteria={engines.gemini?.criteria}
          />
          <LighthouseGauge
            label="Perplexity"
            engineKey="perplexity"
            score={engines.perplexity?.score ?? 0}
            icon={Search}
            accentColorClass="text-amber-400"
            criteria={engines.perplexity?.criteria}
          />
          <LighthouseGauge
            label="Claude"
            engineKey="claude"
            score={engines.claude?.score ?? 0}
            icon={ShieldCheck}
            accentColorClass="text-violet-400"
            criteria={engines.claude?.criteria}
          />
        </div>
      </section>

      {/* ML Crawler Governance Panel */}
      <section aria-labelledby="crawler-governance-heading">
        <CrawlerGovernancePanel governance={data.crawler_governance} />
      </section>

      {/* Recommendations and Audit Checklist */}
      <section aria-labelledby="audit-checklist-heading">
        <AuditChecklist audits={data.audits} />
      </section>
    </div>
  );
}
