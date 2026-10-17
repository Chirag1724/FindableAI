"use client";

import { useState } from "react";
import {
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Users,
  Search,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";

interface QueryItem {
  id: string;
  query: string;
  persona: "Enterprise CTO" | "Tech Lead" | "Procurement" | "Security Lead";
  category: string;
  entailment: "Entailed" | "Uncovered";
  score: number;
  evidenceAnchor: string;
  extractedSnippet: string;
}

const SIMULATED_QUERIES: QueryItem[] = [
  {
    id: "q1",
    query: "Does Acme Cloud support SOC2 Type II compliance reports and audit logs?",
    persona: "Enterprise CTO",
    category: "Compliance & Security",
    entailment: "Entailed",
    score: 0.94,
    evidenceAnchor: "section.compliance-trust > p.certifications",
    extractedSnippet: "Acme Cloud: SOC2 Type II certified with real-time audit logging and tamper-proof trails.",
  },
  {
    id: "q2",
    query: "How does reciprocal rank fusion combine dense embeddings and BM25 rankings?",
    persona: "Tech Lead",
    category: "Architecture & Retrieval",
    entailment: "Entailed",
    score: 0.88,
    evidenceAnchor: "article.docs-content > section#algorithms",
    extractedSnippet: "Uses 60/(60+rank) RRF weighting to fuse sparse BM25 and vector semantic embeddings.",
  },
  {
    id: "q3",
    query: "Where is enterprise SLA uptime guarantee defined in standard contract terms?",
    persona: "Procurement",
    category: "Legal & SLA",
    entailment: "Uncovered",
    score: 0.32,
    evidenceAnchor: "section#terms > p:nth-child(4)",
    extractedSnippet: "Contractual uptime SLAs mentioned informally but omitted from formal microdata table.",
  },
  {
    id: "q4",
    query: "What is the token overhead for real-time CSS selector DOM tracing?",
    persona: "Tech Lead",
    category: "Performance",
    entailment: "Entailed",
    score: 0.91,
    evidenceAnchor: "article.docs-content > table.benchmarks",
    extractedSnippet: "< 4.2ms parsing latency per 100 DOM chunks with zero client runtime overhead.",
  },
];

const PERSONA_STATS = [
  { label: "CTO / Architecture", coverage: 94, queries: "10/10 Entailed", status: "Optimal" },
  { label: "Lead Developer", coverage: 89, queries: "11/12 Entailed", status: "High" },
  { label: "Procurement / Legal", coverage: 62, queries: "5/8 Entailed", status: "Gap Found" },
];

export function IntentSimulator() {
  const [selectedPersona, setSelectedPersona] = useState<string>("All");
  const [activeQueryId, setActiveQueryId] = useState<string>("q1");

  const filteredQueries =
    selectedPersona === "All"
      ? SIMULATED_QUERIES
      : SIMULATED_QUERIES.filter((q) => q.persona.includes(selectedPersona));

  const activeQuery =
    SIMULATED_QUERIES.find((q) => q.id === activeQueryId) || SIMULATED_QUERIES[0];

  return (
    <div className="rounded-2xl bg-surface/90 backdrop-blur-md shadow-border overflow-hidden text-left">
      {/* 1. Header Toolbar with Status & Persona Filter */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 px-4 py-2.5 sm:px-5 sm:py-3 border-b border-white/[0.08] bg-surface-secondary/40">
        <div className="flex items-center flex-wrap gap-2.5">
          <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-mono text-xs font-semibold text-white tracking-wide">
            SYNTHETIC BUYER INTENT SIMULATION
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            30 Evaluated Vectors
          </span>
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 sm:pb-0 scrollbar-none no-scrollbar shrink-0">
          {["All", "CTO", "Tech Lead", "Procurement"].map((p) => (
            <button
              key={p}
              onClick={() => setSelectedPersona(p)}
              className={`px-2.5 py-1 rounded-md text-xs font-mono tracking-tight transition-all duration-150 shrink-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
                selectedPersona === p
                  ? "bg-white text-black font-semibold shadow-sm"
                  : "bg-surface-secondary text-text-muted hover:text-white hover:bg-white/[0.06] shadow-border"
              }`}
            >
              {p === "All" ? "All Personas" : p}
            </button>
          ))}
        </div>
      </div>

      {/* 2. Persona Coverage Distribution Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 sm:gap-3 p-3 sm:p-3.5 bg-surface-secondary/20 border-b border-white/[0.08]">
        {PERSONA_STATS.map((stat) => (
          <div
            key={stat.label}
            className="px-3.5 py-2 rounded-xl bg-surface/80 border border-white/[0.06] shadow-border flex items-center justify-between hover:border-white/[0.12] transition-colors"
          >
            <div className="min-w-0 flex-1 mr-3">
              <div className="flex items-center justify-between text-xs font-mono mb-1">
                <span className="text-[11px] font-medium text-text-primary truncate">{stat.label}</span>
                <span className={`text-[10px] font-bold font-mono ${stat.coverage >= 80 ? "text-emerald-400" : "text-amber-400"}`}>
                  {stat.coverage}%
                </span>
              </div>
              <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-300 ${stat.coverage >= 80 ? "bg-emerald-500" : "bg-amber-500"}`}
                  style={{ width: `${stat.coverage}%` }}
                />
              </div>
            </div>
            <div className="text-right shrink-0">
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border block ${
                stat.coverage >= 80
                  ? "bg-emerald-950/50 text-emerald-400 border-emerald-800/60"
                  : "bg-amber-950/50 text-amber-400 border-amber-800/60"
              }`}>
                {stat.status}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* 3. Interactive Query List & Live Grounding Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 sm:gap-3.5 p-3 sm:p-3.5 bg-surface-secondary/10">
        {/* Queries List (7 cols) */}
        <div className="lg:col-span-7 rounded-xl bg-surface/90 border border-white/[0.08] p-3 shadow-border space-y-1">
          {filteredQueries.map((item) => {
            const isSelected = item.id === activeQueryId;
            return (
              <div
                key={item.id}
                onClick={() => setActiveQueryId(item.id)}
                className={`p-2.5 rounded-lg cursor-pointer transition-all duration-150 space-y-1 ${
                  isSelected
                    ? "bg-surface-secondary ring-1 ring-emerald-500/40 shadow-sm"
                    : "hover:bg-surface-secondary/60"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-surface text-text-muted uppercase border border-white/[0.06]">
                      {item.persona}
                    </span>
                    <span className="text-[10px] font-mono text-text-muted hidden sm:inline">
                      {item.category}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {item.entailment === "Entailed" ? (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-950/50 text-emerald-400 ring-1 ring-inset ring-emerald-800">
                        <CheckCircle2 className="h-3 w-3" />
                        <span>Entailed ({Math.round(item.score * 100)}%)</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono bg-rose-950/50 text-rose-400 ring-1 ring-inset ring-rose-800">
                        <AlertCircle className="h-3 w-3" />
                        <span>Uncovered ({Math.round(item.score * 100)}%)</span>
                      </span>
                    )}
                  </div>
                </div>

                <p className="text-xs text-text-primary font-medium leading-snug line-clamp-2">
                  &ldquo;{item.query}&rdquo;
                </p>
              </div>
            );
          })}
        </div>

        {/* Grounding Inspector Panel (5 cols) */}
        <div className="lg:col-span-5 rounded-xl bg-surface/90 border border-white/[0.08] p-3.5 shadow-border flex flex-col justify-between space-y-2.5">
          <div className="space-y-2.5">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
              <span className="font-mono text-xs font-semibold text-white tracking-wide uppercase flex items-center gap-1.5">
                <Search className="h-3.5 w-3.5 text-emerald-400" />
                Grounding Verification
              </span>
              <span className="text-[10px] font-mono text-text-muted">
                Confidence: {Math.round(activeQuery.score * 100)}%
              </span>
            </div>

            <div className="space-y-1 font-mono text-[11px]">
              <div className="text-[10px] text-text-muted">Target DOM Anchor:</div>
              <div className="p-2 rounded bg-surface-secondary border border-white/[0.06] text-sky-400 truncate text-[11px]">
                {activeQuery.evidenceAnchor}
              </div>
            </div>

            <div className="space-y-1">
              <span className="text-[10px] font-mono text-text-muted">Extracted Grounding Evidence:</span>
              <div className="p-2.5 rounded-lg bg-black/40 border border-white/[0.06] text-xs text-text-primary leading-relaxed line-clamp-2">
                &ldquo;{activeQuery.extractedSnippet}&rdquo;
              </div>
            </div>
          </div>

          <div className="px-3 py-1.5 rounded-lg bg-surface-secondary/40 border border-white/[0.06] font-mono text-[11px] text-text-muted flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5 text-text-muted" />
              Target Buyer Persona:
            </span>
            <span className="text-white font-semibold">{activeQuery.persona}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
