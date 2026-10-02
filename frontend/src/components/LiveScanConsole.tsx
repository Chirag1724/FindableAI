"use client";

import { useEffect, useRef, useState } from "react";
import {
  Globe,
  Layers,
  Bot,
  ShieldAlert,
  Activity,
  GitPullRequest,
  Terminal,
  Cpu,
  CheckCircle2,
  Loader2,
  Sparkles,
} from "lucide-react";
import type { ScanStatus, ScanStatusEvent } from "@/types/scan";

interface LiveScanConsoleProps {
  currentStatus: ScanStatus;
  latestEvent: ScanStatusEvent | null;
  events: { message: string; timestamp: string; current_step: string }[];
  targetUrl: string;
}

const PIPELINE_STAGES = [
  {
    id: "observe",
    title: "Headless Crawl & DOM Extraction",
    icon: Globe,
    activeStatuses: ["pending", "crawling", "extracting_dom"],
    doneStatuses: [
      "synthesizing_intents",
      "hybrid_retrieval",
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ],
    detail: "Parsing semantic DOM tree nodes & mapping CSS selector paths.",
    metric: "W3C Semantic Parser",
  },
  {
    id: "plan",
    title: "Synthetic Intent Simulation",
    icon: Bot,
    activeStatuses: ["synthesizing_intents"],
    doneStatuses: [
      "hybrid_retrieval",
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ],
    detail: "Generating 30 multi-persona buyer queries across 10 search vectors.",
    metric: "3 Personas Active",
  },
  {
    id: "verify",
    title: "Cross-Page NLI Consistency",
    icon: ShieldAlert,
    activeStatuses: ["hybrid_retrieval", "nli_evaluation"],
    doneStatuses: ["computing_fscore", "generating_patches", "completed"],
    detail: "Cross-referencing claims across routes for factual contradictions.",
    metric: "NLI Inference Engine",
  },
  {
    id: "reflect",
    title: "F-Score Metric & Patch Synthesis",
    icon: Activity,
    activeStatuses: ["computing_fscore", "generating_patches"],
    doneStatuses: ["completed"],
    detail: "Computing 4-pillar indexability index and AST unified diff patches.",
    metric: "Deterministic Formula",
  },
];

export function LiveScanConsole({
  currentStatus,
  latestEvent,
  events,
  targetUrl,
}: LiveScanConsoleProps) {
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  const defaultLogs = [
    `Connecting to headless browser engine...`,
    `Dispatched Chromium worker to ${targetUrl}`,
    `Extracting semantic HTML5 trees & CSS selector anchors`,
    `Synthesizing buyer intent vectors (CTO, Dev, Procurement)`,
    `Executing hybrid dense embeddings & BM25 sparse retrieval`,
    `Evaluating natural language inference grounding...`,
  ];

  return (
    <div className="space-y-6 sm:space-y-8">
      {/* 1. Four Live Telemetry Pipeline Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PIPELINE_STAGES.map((stage) => {
          const isActive = stage.activeStatuses.includes(currentStatus);
          const isDone = stage.doneStatuses.includes(currentStatus);
          const Icon = stage.icon;

          return (
            <div
              key={stage.id}
              className={`rounded-xl p-5 transition-all duration-300 flex flex-col justify-between space-y-3 relative overflow-hidden ${
                isActive
                  ? "bg-surface ring-1 ring-emerald-500/50 shadow-lg"
                  : isDone
                    ? "bg-surface shadow-border opacity-90"
                    : "bg-surface-secondary/40 shadow-border opacity-50"
              }`}
            >
              {/* Active ambient glow */}
              {isActive && (
                <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />
              )}

              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <div
                    className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 border ${
                      isActive
                        ? "bg-emerald-950/60 border-emerald-500/50 text-emerald-400"
                        : isDone
                          ? "bg-surface-secondary border-white/10 text-emerald-400"
                          : "bg-surface-secondary border-white/5 text-text-muted"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-white font-mono tracking-tight">
                      {stage.title}
                    </h4>
                    <span className="text-[10px] text-text-muted font-mono block">
                      {stage.metric}
                    </span>
                  </div>
                </div>

                <div className="shrink-0">
                  {isActive && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-800 animate-pulse">
                      <Loader2 className="h-2.5 w-2.5 animate-spin" />
                      <span>Active</span>
                    </span>
                  )}
                  {isDone && (
                    <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-emerald-950/40 text-emerald-400 border border-emerald-900/60">
                      <CheckCircle2 className="h-3 w-3" />
                      <span>Done</span>
                    </span>
                  )}
                  {!isActive && !isDone && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono bg-surface-secondary text-text-muted border border-white/[0.06]">
                      Queued
                    </span>
                  )}
                </div>
              </div>

              <p className="text-[11px] text-text-muted leading-relaxed font-sans">
                {stage.detail}
              </p>
            </div>
          );
        })}
      </div>

      {/* 2. Real-Time Telemetry Terminal Stream */}
      <div className="rounded-xl bg-black/90 shadow-border border border-white/[0.08] overflow-hidden">
        {/* Terminal Header */}
        <div className="flex items-center justify-between p-3.5 border-b border-white/[0.08] bg-surface-secondary/40 font-mono text-xs">
          <div className="flex items-center gap-2">
            <Terminal className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-white font-semibold text-[11px] tracking-wide">
              PIPELINE TELEMETRY STREAM
            </span>
            <span className="text-white/[0.2]">&bull;</span>
            <span className="text-emerald-400 text-[10px] animate-pulse">LIVE</span>
          </div>

          <div className="flex items-center gap-3 text-[10px] text-text-muted">
            <span>Elapsed: {elapsedSeconds}s</span>
            <span className="text-white/[0.2]">&bull;</span>
            <span>Target: {targetUrl}</span>
          </div>
        </div>

        {/* Terminal Output Body */}
        <div className="p-4 sm:p-5 font-mono text-xs space-y-2 max-h-64 overflow-y-auto custom-scrollbar select-text bg-[#070707]">
          {events.length > 0 ? (
            events.map((evt, idx) => (
              <div key={idx} className="flex items-start gap-2.5 text-[11px] leading-relaxed">
                <span className="text-text-muted shrink-0 opacity-60">
                  [{new Date(evt.timestamp).toLocaleTimeString()}]
                </span>
                <span className="text-sky-400 shrink-0 uppercase font-semibold">
                  [{evt.current_step}]
                </span>
                <span className="text-text-primary">{evt.message}</span>
              </div>
            ))
          ) : (
            defaultLogs.slice(0, Math.min(defaultLogs.length, Math.floor(elapsedSeconds / 2) + 1)).map((log, idx) => (
              <div key={idx} className="flex items-start gap-2.5 text-[11px] leading-relaxed">
                <span className="text-text-muted shrink-0 opacity-60">
                  [+{(idx * 1.8).toFixed(1)}s]
                </span>
                <span className="text-emerald-400 shrink-0 font-semibold">
                  &gt;
                </span>
                <span className="text-text-primary">{log}</span>
              </div>
            ))
          )}

          {/* Active Terminal Cursor */}
          <div className="flex items-center gap-2 text-emerald-400 text-[11px] pt-1">
            <span className="font-semibold">&gt;</span>
            <span className="text-text-muted">
              {latestEvent?.message || "Running machine audit pipeline..."}
            </span>
            <span className="inline-block h-3.5 w-1.5 bg-emerald-400 animate-pulse" />
          </div>
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
}
