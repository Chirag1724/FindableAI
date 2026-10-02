"use client";

import React from "react";
import { Check } from "lucide-react";

export function ArchitecturePillars() {
  return (
    <section data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 py-8 sm:py-12 border-y border-white/[0.08] max-w-5xl mx-auto w-full">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8 text-left">
        {/* Pillar 1: DOM-Anchored Precision (Star Graph Network) */}
        <div className="flex flex-col">
          <div className="h-48 sm:h-56 rounded-xl bg-surface shadow-border flex items-center justify-center p-4 relative overflow-hidden group">
            {/* Ambient subtle glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

            {/* Star Node Network Visual */}
            <div className="relative w-full h-full flex items-center justify-center">
              <svg
                viewBox="0 0 260 180"
                className="w-full h-full max-w-[240px] max-h-[160px] select-none pointer-events-none"
              >
                {/* Connecting Ray Lines */}
                <g stroke="rgba(255,255,255,0.18)" strokeWidth="1" strokeDasharray="2 2">
                  <line x1="130" y1="90" x2="35" y2="35" />
                  <line x1="130" y1="90" x2="80" y2="25" />
                  <line x1="130" y1="90" x2="140" y2="20" />
                  <line x1="130" y1="90" x2="195" y2="30" />
                  <line x1="130" y1="90" x2="230" y2="50" />
                  <line x1="130" y1="90" x2="245" y2="100" />
                  <line x1="130" y1="90" x2="225" y2="150" />
                  <line x1="130" y1="90" x2="170" y2="165" />
                  <line x1="130" y1="90" x2="110" y2="168" />
                  <line x1="130" y1="90" x2="55" y2="155" />
                  <line x1="130" y1="90" x2="20" y2="110" />
                  <line x1="130" y1="90" x2="25" y2="70" />
                </g>

                {/* Outer Node Dots */}
                {[
                  { cx: 35, cy: 35 },
                  { cx: 80, cy: 25 },
                  { cx: 140, cy: 20 },
                  { cx: 195, cy: 30 },
                  { cx: 230, cy: 50 },
                  { cx: 245, cy: 100 },
                  { cx: 225, cy: 150 },
                  { cx: 170, cy: 165 },
                  { cx: 110, cy: 168 },
                  { cx: 55, cy: 155 },
                  { cx: 20, cy: 110 },
                  { cx: 25, cy: 70 },
                ].map((pt, idx) => (
                  <circle
                    key={idx}
                    cx={pt.cx}
                    cy={pt.cy}
                    r="2.5"
                    className="fill-neutral-300 transition-all duration-300 group-hover:fill-emerald-400"
                  />
                ))}
              </svg>

              {/* Center Pill */}
              <div className="absolute z-10 inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border border border-white/[0.12] text-[11px] font-mono text-white">
                <span className="tracking-tight">yoursite.com</span>
                <Check className="h-3 w-3 text-emerald-400 stroke-[2.5]" />
              </div>
            </div>
          </div>

          <div className="mt-3.5 space-y-1">
            <p className="text-xs sm:text-sm text-text-muted leading-relaxed">
              <strong className="text-white font-semibold sm:inline block sm:mr-1.5">
                DOM-Anchored Precision
              </strong>
              Every audit finding maps to a verifiable CSS selector path in your markup.
            </p>
          </div>
        </div>

        {/* Pillar 2: Deterministic Scoring (Ranked Distribution Bars) */}
        <div className="flex flex-col">
          <div className="h-48 sm:h-56 rounded-xl bg-surface shadow-border flex flex-col justify-center p-4 sm:p-5 relative overflow-hidden group">
            {/* Ambient subtle glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

            {/* 4 Ranked Distribution Bars */}
            <div className="space-y-2.5 w-full relative z-10">
              {[
                { icon: "◎", label: "Intent Coverage", pct: "40%", width: "w-full", active: true },
                { icon: "◷", label: "Fact Consistency", pct: "30%", width: "w-[75%]", active: false },
                { icon: "⛭", label: "DOM Structure", pct: "20%", width: "w-[50%]", active: false },
                { icon: "◒", label: "Extractability", pct: "10%", width: "w-[25%]", active: false },
              ].map((item, idx) => (
                <div key={idx} className="flex items-center gap-2.5">
                  <div className="h-6 w-6 rounded-md bg-surface-secondary shadow-border border border-white/[0.08] flex items-center justify-center text-[11px] text-text-muted shrink-0 font-mono">
                    {item.icon}
                  </div>
                  <div className="h-6 flex-1 bg-surface-secondary/70 rounded-md border border-white/[0.06] overflow-hidden p-0.5 relative flex items-center">
                    <div
                      className={`h-full rounded ${item.width} bg-white/[0.08] group-hover:bg-white/[0.14] transition-all duration-300 flex items-center justify-between px-2`}
                    >
                      <span className="text-[10px] font-mono text-text-primary truncate">
                        {item.label}
                      </span>
                      <span className="text-[10px] font-mono text-text-muted shrink-0">
                        {item.pct}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-3.5 space-y-1">
            <p className="text-xs sm:text-sm text-text-muted leading-relaxed">
              <strong className="text-white font-semibold sm:inline block sm:mr-1.5">
                Deterministic Scoring
              </strong>
              F-Scores are calculated mathematically across four weighted, reproducible pillars.
            </p>
          </div>
        </div>

        {/* Pillar 3: Autonomous Remediation (Code Snippet) */}
        <div className="flex flex-col">
          <div className="h-48 sm:h-56 rounded-xl bg-surface shadow-border flex flex-col justify-center p-4 font-mono text-[10px] leading-relaxed relative overflow-hidden group">
            {/* Ambient subtle glow */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/[0.02] to-transparent pointer-events-none" />

            <div className="space-y-1 relative z-10 text-neutral-400">
              <p>
                <span className="text-rose-400">import</span> &#123;{" "}
                <span className="text-neutral-200">Schema</span> &#125;{" "}
                <span className="text-rose-400">from</span>{" "}
                <span className="text-emerald-400">&apos;@findable/seo&apos;</span>
              </p>
              <div className="h-1" />
              <p>
                <span className="text-rose-400">export function</span>{" "}
                <span className="text-sky-400">AuditFix</span>() &#123;
              </p>
              <p className="pl-2">
                <span className="text-rose-400">return</span> (
              </p>
              {/* Highlighted active code patch line */}
              <div className="pl-4 py-0.5 -mx-2 px-2 bg-white/[0.04] border-l-2 border-emerald-400 rounded-r text-neutral-200">
                <span className="text-sky-400">&lt;Schema.Microdata</span>
                <div className="pl-2 text-emerald-400">
                  type=<span className="text-neutral-200">&quot;SoftwareApp&quot;</span>
                </div>
                <div className="pl-2 text-emerald-400">
                  grounded=&#123;<span className="text-amber-400">true</span>&#125;
                </div>
                <span className="text-sky-400">/&gt;</span>
              </div>
              <p className="pl-2">);</p>
              <p>&#125;</p>
            </div>
          </div>

          <div className="mt-3.5 space-y-1">
            <p className="text-xs sm:text-sm text-text-muted leading-relaxed">
              <strong className="text-white font-semibold sm:inline block sm:mr-1.5">
                Autonomous Remediation
              </strong>
              Automated diffs generate unified patches and Schema.org JSON-LD microdata.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
