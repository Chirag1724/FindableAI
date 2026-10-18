"use client";

import React from "react";
import { Check, Crosshair, GitPullRequest } from "lucide-react";

export function ArchitecturePillars() {
  return (
    <section
      data-reveal-section
      className="mb-8 sm:mb-10 lg:mb-12 py-6 sm:py-8 border-y border-white/[0.08] max-w-7xl mx-auto w-full"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-5 text-left">
        {/* Pillar 1: DOM-Anchored Precision (Star Graph Network) */}
        <div className="rounded-2xl bg-surface/90 shadow-border border border-white/[0.08] p-4 sm:p-5 flex flex-col justify-between hover:border-white/[0.16] transition-all group">
          {/* Visual Canvas Container */}
          <div className="h-44 sm:h-48 rounded-xl bg-surface-secondary/40 border border-white/[0.06] shadow-inner flex items-center justify-center p-3 relative overflow-hidden">
            {/* Ambient subtle glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

            {/* Corner Badge */}
            <div className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded text-[9px] font-mono bg-surface border border-white/[0.06] text-text-muted flex items-center gap-1">
              <Crosshair className="h-2.5 w-2.5 text-emerald-400" />
              <span>CSS SELECTOR MAP</span>
            </div>

            {/* Star Node Network Visual */}
            <div className="relative w-full h-full flex items-center justify-center">
              <svg
                viewBox="0 0 260 170"
                className="w-full h-full max-w-[240px] max-h-[150px] select-none pointer-events-none"
              >
                {/* Connecting Ray Lines */}
                <g stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="2 2" className="transition-all duration-300 group-hover:stroke-emerald-400/30">
                  <line x1="130" y1="85" x2="35" y2="30" />
                  <line x1="130" y1="85" x2="80" y2="20" />
                  <line x1="130" y1="85" x2="140" y2="15" />
                  <line x1="130" y1="85" x2="195" y2="25" />
                  <line x1="130" y1="85" x2="230" y2="45" />
                  <line x1="130" y1="85" x2="245" y2="95" />
                  <line x1="130" y1="85" x2="225" y2="145" />
                  <line x1="130" y1="85" x2="170" y2="158" />
                  <line x1="130" y1="85" x2="110" y2="160" />
                  <line x1="130" y1="85" x2="55" y2="148" />
                  <line x1="130" y1="85" x2="20" y2="105" />
                  <line x1="130" y1="85" x2="25" y2="65" />
                </g>

                {/* Outer Node Dots */}
                {[
                  { cx: 35, cy: 30 },
                  { cx: 80, cy: 20 },
                  { cx: 140, cy: 15 },
                  { cx: 195, cy: 25 },
                  { cx: 230, cy: 45 },
                  { cx: 245, cy: 95 },
                  { cx: 225, cy: 145 },
                  { cx: 170, cy: 158 },
                  { cx: 110, cy: 160 },
                  { cx: 55, cy: 148 },
                  { cx: 20, cy: 105 },
                  { cx: 25, cy: 65 },
                ].map((pt, idx) => (
                  <circle
                    key={idx}
                    cx={pt.cx}
                    cy={pt.cy}
                    r="2.5"
                    className="fill-neutral-400 transition-all duration-300 group-hover:fill-emerald-400"
                  />
                ))}
              </svg>

              {/* Center Pill */}
              <div className="absolute z-10 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface shadow-border border border-white/[0.14] text-[11px] font-mono text-white ring-2 ring-emerald-500/20">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="tracking-tight font-medium">yoursite.com</span>
                <Check className="h-3 w-3 text-emerald-400 stroke-[2.5]" />
              </div>
            </div>
          </div>

          {/* Integrated Card Caption */}
          <div className="mt-3.5 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono uppercase text-emerald-400 font-semibold tracking-wider">
                Pillar 01 · Grounding
              </span>
            </div>
            <h3 className="text-sm font-semibold text-white tracking-tight">
              DOM-Anchored Precision
            </h3>
            <p className="text-xs text-text-muted leading-relaxed">
              Every audit finding maps to a verifiable CSS selector path in your source markup, preventing LLM hallucination.
            </p>
          </div>
        </div>

        {/* Pillar 2: Deterministic Scoring (Ranked Distribution Bars) */}
        <div className="rounded-2xl bg-surface/90 shadow-border border border-white/[0.08] p-4 sm:p-5 flex flex-col justify-between hover:border-white/[0.16] transition-all group">
          {/* Visual Canvas Container */}
          <div className="h-44 sm:h-48 rounded-xl bg-surface-secondary/40 border border-white/[0.06] shadow-inner flex flex-col justify-center px-4 py-3 relative overflow-hidden">
            {/* Ambient subtle glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

            {/* Corner Badge */}
            <div className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded text-[9px] font-mono bg-surface border border-white/[0.06] text-text-muted">
              ADR-001 CANONICAL
            </div>

            {/* 4 Ranked Distribution Bars */}
            <div className="space-y-2.5 w-full relative z-10">
              {[
                { label: "Answerability", pct: 40, color: "bg-emerald-400", textColor: "text-emerald-400" },
                { label: "Fact Consistency", pct: 30, color: "bg-sky-400", textColor: "text-sky-400" },
                { label: "DOM Structure", pct: 20, color: "bg-violet-400", textColor: "text-violet-400" },
                { label: "Schema Accuracy", pct: 10, color: "bg-amber-400", textColor: "text-amber-400" },
              ].map((item, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-text-primary font-medium">{item.label}</span>
                    <span className={`${item.textColor} font-bold`}>{item.pct}%</span>
                  </div>
                  <div className="w-full bg-white/[0.06] h-1.5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${item.color} transition-all duration-300`}
                      style={{ width: `${item.pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Integrated Card Caption */}
          <div className="mt-3.5 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono uppercase text-sky-400 font-semibold tracking-wider">
                Pillar 02 · Formulation
              </span>
            </div>
            <h3 className="text-sm font-semibold text-white tracking-tight">
              Deterministic Scoring
            </h3>
            <p className="text-xs text-text-muted leading-relaxed">
              F-Scores are calculated mathematically across four weighted, reproducible pillars with zero black-box scoring.
            </p>
          </div>
        </div>

        {/* Pillar 3: Autonomous Remediation (Code Snippet) */}
        <div className="rounded-2xl bg-surface/90 shadow-border border border-white/[0.08] p-4 sm:p-5 flex flex-col justify-between hover:border-white/[0.16] transition-all group">
          {/* Visual Canvas Container */}
          <div className="h-44 sm:h-48 rounded-xl bg-surface-secondary/40 border border-white/[0.06] shadow-inner flex flex-col justify-between p-3 font-mono text-[10px] leading-relaxed relative overflow-hidden">
            {/* Editor Top Bar */}
            <div className="flex items-center justify-between pb-1.5 border-b border-white/[0.06] text-[9px] text-text-muted">
              <div className="flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-red-500/70" />
                <span className="h-2 w-2 rounded-full bg-amber-500/70" />
                <span className="h-2 w-2 rounded-full bg-emerald-500/70" />
                <span className="ml-1 text-text-muted font-medium">schema-patch.tsx</span>
              </div>
              <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[8px] font-semibold">
                UNIFIED DIFF
              </span>
            </div>

            <div className="space-y-0.5 relative z-10 text-neutral-400 text-[10px]">
              <p>
                <span className="text-rose-400">import</span> &#123;{" "}
                <span className="text-neutral-200">Schema</span> &#125;{" "}
                <span className="text-rose-400">from</span>{" "}
                <span className="text-emerald-400">&apos;@findable/seo&apos;</span>;
              </p>
              <p>
                <span className="text-rose-400">export function</span>{" "}
                <span className="text-sky-400">AuditFix</span>() &#123;
              </p>
              {/* Highlighted active code patch line */}
              <div className="my-0.5 pl-2 py-1 bg-emerald-500/10 border-l-2 border-emerald-400 rounded-r text-neutral-200 text-[9.5px]">
                <span className="text-sky-400">&lt;Schema.Microdata</span>
                <span className="text-emerald-400 ml-1.5">type=</span>
                <span className="text-neutral-200">&quot;SoftwareApp&quot;</span>
                <span className="text-emerald-400 ml-1.5">grounded=</span>
                <span className="text-amber-400">&#123;true&#125;</span>
                <span className="text-sky-400 ml-1">/&gt;</span>
              </div>
              <p>&#125;</p>
            </div>

            <div className="flex items-center justify-between pt-1 border-t border-white/[0.04] text-[9px] text-text-muted">
              <span className="flex items-center gap-1 text-emerald-400">
                <GitPullRequest className="h-3 w-3" />
                <span>Ready for Pull Request</span>
              </span>
              <span className="font-mono text-neutral-500">v1.4</span>
            </div>
          </div>

          {/* Integrated Card Caption */}
          <div className="mt-3.5 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono uppercase text-violet-400 font-semibold tracking-wider">
                Pillar 03 · Remediation
              </span>
            </div>
            <h3 className="text-sm font-semibold text-white tracking-tight">
              Autonomous Remediation
            </h3>
            <p className="text-xs text-text-muted leading-relaxed">
              Automated diffs generate unified patches and Schema.org JSON-LD microdata ready for single-click repo injection.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
