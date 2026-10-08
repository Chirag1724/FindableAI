"use client";

import { useState, useRef, useEffect } from "react";
import {
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  TrendingUp,
} from "lucide-react";
import type {
  AuditSummary,
  AuditOpportunity,
  AuditDiagnostic,
  AuditPassed,
} from "@/types/lighthouse";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

interface AuditChecklistProps {
  audits: AuditSummary;
}

function getEngineBadgeClass(engine: string): string {
  switch (engine.toLowerCase()) {
    case "chatgpt":
      return "bg-emerald-950/60 text-emerald-300 border-emerald-800/40";
    case "gemini":
      return "bg-sky-950/60 text-sky-300 border-sky-800/40";
    case "perplexity":
      return "bg-amber-950/60 text-amber-300 border-amber-800/40";
    case "claude":
      return "bg-violet-950/60 text-violet-300 border-violet-800/40";
    default:
      return "bg-white/[0.06] text-text-muted border-white/[0.08]";
  }
}

function formatEngineLabel(engine: string): string {
  switch (engine.toLowerCase()) {
    case "chatgpt":
      return "ChatGPT";
    case "gemini":
      return "Gemini";
    case "perplexity":
      return "Perplexity";
    case "claude":
      return "Claude";
    case "all":
      return "All Engines";
    default:
      return engine;
  }
}

function getSeverityBadge(severity: AuditOpportunity["severity"]) {
  switch (severity) {
    case "critical":
      return (
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-rose-950/60 text-rose-300 border border-rose-800/50">
          Critical
        </span>
      );
    case "high":
      return (
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-amber-950/60 text-amber-300 border border-amber-800/50">
          High Priority
        </span>
      );
    case "medium":
      return (
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-sky-950/60 text-sky-300 border border-sky-800/50">
          Medium
        </span>
      );
    case "low":
      return (
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-white/[0.04] text-text-muted border border-white/[0.08]">
          Low
        </span>
      );
  }
}

export function AuditChecklist({ audits }: AuditChecklistProps) {
  const [opportunitiesOpen, setOpportunitiesOpen] = useState(true);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(true);
  const [passedOpen, setPassedOpen] = useState(false);

  const oppContentRef = useRef<HTMLDivElement>(null);
  const diagContentRef = useRef<HTMLDivElement>(null);
  const passedContentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (oppContentRef.current && !prefersReducedMotion() && opportunitiesOpen) {
      gsap.fromTo(
        oppContentRef.current,
        { opacity: 0, height: 0 },
        { opacity: 1, height: "auto", duration: 0.2, ease: EASING.expand }
      );
    }
  }, [opportunitiesOpen]);

  return (
    <div
      data-testid="audit-checklist"
      className="rounded-xl bg-surface-secondary/70 p-5 sm:p-6 shadow-border space-y-6"
    >
      {/* Header */}
      <div className="border-b border-white/[0.08] pb-4">
        <h2 className="text-base font-semibold text-white tracking-tight">
          Lighthouse Audit Recommendations & Diagnostics
        </h2>
        <p className="text-xs text-text-muted mt-0.5">
          Deterministic recommendations to optimize machine discoverability and knowledge graph grounding.
        </p>
      </div>

      {/* 1. Opportunities Section */}
      <div className="rounded-lg border border-rose-900/30 bg-rose-950/10 overflow-hidden">
        <button
          type="button"
          onClick={() => setOpportunitiesOpen((prev) => !prev)}
          className="flex w-full items-center justify-between p-4 text-left hover:bg-white/[0.02] transition-colors focus:outline-none focus:ring-1 focus:ring-white/20"
          aria-expanded={opportunitiesOpen}
        >
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-rose-500/10 text-rose-400">
              <AlertTriangle size={14} aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold text-white">
              Opportunities ({audits.opportunities.length})
            </span>
            <span className="text-xs text-text-muted hidden sm:inline">
              - Actionable fixes with projected score lift
            </span>
          </div>
          {opportunitiesOpen ? (
            <ChevronUp size={16} className="text-text-muted" aria-hidden="true" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" aria-hidden="true" />
          )}
        </button>

        {opportunitiesOpen && (
          <div ref={oppContentRef} className="border-t border-rose-900/20 p-4 space-y-2.5">
            {audits.opportunities.length === 0 ? (
              <div className="py-4 text-center text-xs text-text-muted">
                No critical opportunities detected. All core citation paths are open.
              </div>
            ) : (
              audits.opportunities.map((opp: AuditOpportunity) => (
                <div
                  key={opp.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 rounded-lg bg-black/40 border border-white/[0.06] p-3.5 hover:border-white/[0.12] transition-all"
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <span className="mt-0.5 flex h-2 w-2 shrink-0 rounded-full bg-rose-400" />
                    <div className="space-y-1 min-w-0">
                      <p className="text-xs font-medium text-white leading-snug">
                        {opp.title}
                      </p>
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span
                          className={`inline-flex items-center rounded-md border px-2 py-0.5 font-medium ${getEngineBadgeClass(
                            opp.engine
                          )}`}
                        >
                          {formatEngineLabel(opp.engine)}
                        </span>
                        {getSeverityBadge(opp.severity)}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0 self-start sm:self-center">
                    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 text-xs font-mono font-bold text-emerald-300">
                      <TrendingUp size={12} aria-hidden="true" />
                      +{opp.score_lift} pts
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 2. Diagnostics Section */}
      <div className="rounded-lg border border-amber-900/30 bg-amber-950/10 overflow-hidden">
        <button
          type="button"
          onClick={() => setDiagnosticsOpen((prev) => !prev)}
          className="flex w-full items-center justify-between p-4 text-left hover:bg-white/[0.02] transition-colors focus:outline-none focus:ring-1 focus:ring-white/20"
          aria-expanded={diagnosticsOpen}
        >
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-amber-500/10 text-amber-400">
              <AlertCircle size={14} aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold text-white">
              Diagnostics ({audits.diagnostics.length})
            </span>
            <span className="text-xs text-text-muted hidden sm:inline">
              - Structural and semantic warnings
            </span>
          </div>
          {diagnosticsOpen ? (
            <ChevronUp size={16} className="text-text-muted" aria-hidden="true" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" aria-hidden="true" />
          )}
        </button>

        {diagnosticsOpen && (
          <div ref={diagContentRef} className="border-t border-amber-900/20 p-4 space-y-2.5">
            {audits.diagnostics.length === 0 ? (
              <div className="py-4 text-center text-xs text-text-muted">
                Zero diagnostic warnings. Semantic structure is fully verified.
              </div>
            ) : (
              audits.diagnostics.map((diag: AuditDiagnostic) => (
                <div
                  key={diag.id}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 rounded-lg bg-black/40 border border-white/[0.06] p-3.5 hover:border-white/[0.12] transition-all"
                >
                  <div className="flex items-start gap-2.5 min-w-0">
                    <span className="mt-0.5 flex h-2 w-2 shrink-0 rounded-full bg-amber-400" />
                    <p className="text-xs font-medium text-white leading-snug">
                      {diag.title}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                    {diag.engines_affected.map((eng) => (
                      <span
                        key={eng}
                        className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${getEngineBadgeClass(
                          eng
                        )}`}
                      >
                        {formatEngineLabel(eng)}
                      </span>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* 3. Passed Audits Section */}
      <div className="rounded-lg border border-emerald-900/30 bg-emerald-950/10 overflow-hidden">
        <button
          type="button"
          onClick={() => setPassedOpen((prev) => !prev)}
          className="flex w-full items-center justify-between p-4 text-left hover:bg-white/[0.02] transition-colors focus:outline-none focus:ring-1 focus:ring-white/20"
          aria-expanded={passedOpen}
        >
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 size={14} aria-hidden="true" />
            </div>
            <span className="text-sm font-semibold text-white">
              Passed Audits ({audits.passed.length})
            </span>
            <span className="text-xs text-text-muted hidden sm:inline">
              - Validated compliance criteria
            </span>
          </div>
          {passedOpen ? (
            <ChevronUp size={16} className="text-text-muted" aria-hidden="true" />
          ) : (
            <ChevronDown size={16} className="text-text-muted" aria-hidden="true" />
          )}
        </button>

        {passedOpen && (
          <div ref={passedContentRef} className="border-t border-emerald-900/20 p-4 space-y-2">
            {audits.passed.length === 0 ? (
              <div className="py-4 text-center text-xs text-text-muted">
                No audits passed yet.
              </div>
            ) : (
              audits.passed.map((item: AuditPassed) => (
                <div
                  key={item.id}
                  className="flex items-center gap-2.5 rounded-lg bg-black/40 border border-white/[0.04] p-3 text-xs text-text-primary"
                >
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" aria-hidden="true" />
                  <span className="leading-snug">{item.title}</span>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
