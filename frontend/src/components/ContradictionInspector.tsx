"use client";

import { useState } from "react";
import {
  AlertCircle,
  ShieldCheck,
  CheckCircle2,
  GitCompare,
  ArrowRight,
  FileCode2,
  Zap,
} from "lucide-react";

interface ContradictionItem {
  id: string;
  title: string;
  severity: "High" | "Medium";
  confidence: number;
  sourceRoute: string;
  sourceSelector: string;
  sourceText: string;
  conflictRoute: string;
  conflictSelector: string;
  conflictText: string;
  fixRecommendation: string;
}

const CONTRADICTIONS_DATA: ContradictionItem[] = [
  {
    id: "c1",
    title: "SLA Rate Limit & Seat Conflict",
    severity: "High",
    confidence: 94.8,
    sourceRoute: "/ (Landing Page)",
    sourceSelector: "main > header.hero > p",
    sourceText: "Unlimited free audits with no rate limits or seat restrictions.",
    conflictRoute: "/pricing (Terms & Conditions)",
    conflictSelector: "section#terms > p:nth-child(4)",
    conflictText: "Free tier is strictly limited to 10 audits per calendar month.",
    fixRecommendation:
      "Align marketing claim to state '10 free audits/month included' and attach Enterprise unlimited tier microdata to clarify terms.",
  },
  {
    id: "c2",
    title: "SOC2 Compliance Type Mismatch",
    severity: "Medium",
    confidence: 89.2,
    sourceRoute: "/features",
    sourceSelector: "section#security > h3",
    sourceText: "SOC2 Type II certified infrastructure with continuous penetration testing.",
    conflictRoute: "/security/compliance",
    conflictSelector: "table.certifications > tr:nth-child(2)",
    conflictText: "SOC2 Type I verified (Type II report scheduled for Q4 2026).",
    fixRecommendation:
      "Update feature claim to specify 'SOC2 Type I certified, Type II in audit' to prevent answer engine hallucination.",
  },
];

export function ContradictionInspector() {
  const [activeConflictId, setActiveConflictId] = useState<string>("c1");

  const activeConflict =
    CONTRADICTIONS_DATA.find((c) => c.id === activeConflictId) ||
    CONTRADICTIONS_DATA[0];

  return (
    <div className="rounded-xl bg-surface shadow-border overflow-hidden text-left">
      {/* 1. Header Toolbar with Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 sm:p-5 border-b border-white/[0.08] bg-surface-secondary/40">
        <div className="flex items-center flex-wrap gap-2 sm:gap-2.5">
          <span className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
          <span className="font-mono text-xs font-semibold text-white tracking-wide">
            CROSS-PAGE NLI INFERENCE ENGINE
          </span>
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-surface shadow-border text-[10px] font-mono text-text-muted">
            Sample Preview
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950/50 text-rose-400 border border-rose-800/60">
            {CONTRADICTIONS_DATA.length} Conflicts Detected
          </span>
        </div>

        {/* Tab Switcher */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
          {CONTRADICTIONS_DATA.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveConflictId(c.id)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-mono tracking-tight transition-all duration-150 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 ${
                activeConflictId === c.id
                  ? "bg-white text-black font-semibold shadow-sm"
                  : "bg-surface-secondary text-text-muted hover:text-white hover:bg-white/[0.06]"
              }`}
            >
              {c.title}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Top Conflict Telemetry Summary */}
      <div className="p-4 sm:p-5 border-b border-white/[0.08] bg-surface flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-mono uppercase ${
              activeConflict.severity === "High"
                ? "bg-rose-950/50 text-rose-400 ring-1 ring-inset ring-rose-800"
                : "bg-amber-950/50 text-amber-400 ring-1 ring-inset ring-amber-800"
            }`}
          >
            <AlertCircle className="h-3 w-3" />
            <span>{activeConflict.severity} Severity Contradiction</span>
          </span>
          <span className="text-xs font-semibold text-white font-mono">
            {activeConflict.title}
          </span>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="text-text-muted">NLI Confidence:</span>
          <div className="flex items-center gap-1.5">
            <div className="w-20 bg-surface-secondary h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-rose-500 h-full rounded-full"
                style={{ width: `${activeConflict.confidence}%` }}
              />
            </div>
            <span className="text-rose-400 font-semibold">
              {activeConflict.confidence}%
            </span>
          </div>
        </div>
      </div>

      {/* 3. Side-by-Side Contradiction Matrix */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-white/[0.08]">
        {/* Source Claim */}
        <div className="p-5 sm:p-6 bg-surface space-y-3">
          <div className="flex items-center justify-between text-xs pb-2 border-b border-white/[0.06]">
            <span className="font-mono text-[11px] uppercase tracking-wider text-emerald-400 font-semibold flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5" />
              Source Marketing Claim
            </span>
            <span className="text-[10px] font-mono text-text-muted">
              {activeConflict.sourceRoute}
            </span>
          </div>

          <div className="p-2.5 rounded bg-surface-secondary text-[11px] font-mono text-text-muted truncate border border-white/[0.06]">
            CSS: <span className="text-emerald-400">{activeConflict.sourceSelector}</span>
          </div>

          <p className="text-xs sm:text-sm text-text-primary leading-relaxed bg-black/30 p-3.5 rounded-lg border border-white/[0.06]">
            &quot;{activeConflict.sourceText}&quot;
          </p>
        </div>

        {/* Conflicting Claim */}
        <div className="p-5 sm:p-6 bg-surface space-y-3">
          <div className="flex items-center justify-between text-xs pb-2 border-b border-white/[0.06]">
            <span className="font-mono text-[11px] uppercase tracking-wider text-rose-400 font-semibold flex items-center gap-1.5">
              <AlertCircle className="h-3.5 w-3.5" />
              Conflicting Factual Claim
            </span>
            <span className="text-[10px] font-mono text-text-muted">
              {activeConflict.conflictRoute}
            </span>
          </div>

          <div className="p-2.5 rounded bg-surface-secondary text-[11px] font-mono text-text-muted truncate border border-white/[0.06]">
            CSS: <span className="text-rose-400">{activeConflict.conflictSelector}</span>
          </div>

          <p className="text-xs sm:text-sm text-text-primary leading-relaxed bg-black/30 p-3.5 rounded-lg border border-white/[0.06]">
            &quot;{activeConflict.conflictText}&quot;
          </p>
        </div>
      </div>

      {/* 4. Automated Resolution Diff Proposal */}
      <div className="p-4 sm:p-5 bg-background border-t border-white/[0.08] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Zap className="h-4 w-4 text-emerald-400 shrink-0" />
          <div className="text-xs space-y-0.5">
            <span className="font-mono text-[10px] uppercase text-emerald-400 font-semibold tracking-wider block">
              Autonomous Recommendation
            </span>
            <p className="text-text-muted text-[11px]">
              {activeConflict.fixRecommendation}
            </p>
          </div>
        </div>

        <span className="px-3 py-1 rounded bg-surface-secondary text-[10px] font-mono text-text-muted shrink-0 border border-white/[0.08]">
          Patch Ready
        </span>
      </div>
    </div>
  );
}
