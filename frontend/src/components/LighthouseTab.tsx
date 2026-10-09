"use client";

import { useEffect, useState, useCallback } from "react";
import { Bot, FileCode2, Search, ShieldCheck } from "lucide-react";
import type { LighthouseResponse } from "@/types/lighthouse";
import { getLighthouse } from "@/lib/api";
import { LighthouseGauge } from "./LighthouseGauge";
import { CrawlerGovernancePanel } from "./CrawlerGovernancePanel";
import { AuditChecklist } from "./AuditChecklist";
import { ErrorState } from "./ErrorState";

interface LighthouseTabProps {
  scanId: string;
}

export function LighthouseTab({ scanId }: LighthouseTabProps) {
  const [data, setData] = useState<LighthouseResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isInProgress, setIsInProgress] = useState<boolean>(false);

  const fetchLighthouse = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      setIsInProgress(false);

      try {
        const response = await getLighthouse(scanId, signal);
        setData(response);
      } catch (err) {
        if (signal?.aborted) return;
        const apiErr = err as { status?: number; message?: string; detail?: string };
        if (apiErr?.status === 404) {
          setIsInProgress(true);
          setError(
            apiErr.detail || "Lighthouse data not yet available for this scan (scan may still be processing)."
          );
        } else {
          setIsInProgress(false);
          const msg = err instanceof Error ? err.message : apiErr?.message;
          setError(msg || "Failed to load AI Lighthouse assessment.");
        }
        setData(null);
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
      <div data-testid="lighthouse-tab-error" className="py-4">
        <ErrorState
          title={isInProgress ? "Assessment in Progress" : "Failed to Load AI Lighthouse"}
          message={error}
          onRetry={() => void fetchLighthouse()}
          retryLabel="Retry Assessment"
        />
      </div>
    );
  }

  if (!data) return null;

  const engines = data.engines;

  return (
    <div data-testid="lighthouse-tab" className="space-y-6 sm:space-y-8">
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
