"use client";

import { useState } from "react";
import {
  RadialBarChart,
  RadialBar,
  ResponsiveContainer,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Tooltip,
} from "recharts";
import {
  Activity,
  Compass,
  BarChart3,
  ShieldCheck,
  AlertTriangle,
  ChevronDown,
} from "lucide-react";
import type { FScoreBreakdown } from "@/types/scan";
import { useCountUp } from "@/hooks/useCountUp";
import { normalizeWeight } from "@/lib/normalize";
import { gradeColor } from "@/lib/format";

interface ScoreGaugeProps {
  fScore: FScoreBreakdown;
}

const ARC_COLORS = {
  coverage: "#10b981", // emerald-500 (40% weight - query coverage)
  contradiction: "#2dd4bf", // teal-400 (30% weight - fact consistency)
  structure: "#38bdf8", // sky-400 (20% weight - DOM structure)
  entailment: "#94a3b8", // slate-400 (10% weight - machine extractability)
};

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name?: string;
    value?: number;
    payload?: {
      earned?: number;
      max?: number;
      dimension?: string;
      fullName?: string;
      name?: string;
    };
  }>;
}

function DarkTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || !payload.length) return null;
  const item = payload[0];
  const p = item.payload;

  return (
    <div className="rounded-lg bg-surface-secondary px-3 py-2 text-xs text-text-primary shadow-xl shadow-border">
      <div className="font-medium text-white mb-0.5">
        {p?.fullName ?? p?.dimension ?? p?.name ?? item.name}
      </div>
      {p?.earned !== undefined && p?.max !== undefined ? (
        <div className="text-text-muted">
          Earned: <span className="font-mono text-emerald-400 font-semibold">{p.earned}</span> / {p.max} pts
        </div>
      ) : (
        <div className="text-text-muted">
          Score: <span className="font-mono text-emerald-400 font-semibold">{item.value?.toFixed(1)}</span> / 100
        </div>
      )}
    </div>
  );
}

export function ScoreGauge({ fScore }: ScoreGaugeProps) {
  const [openDiagnostics, setOpenDiagnostics] = useState(false);
  const { value: animatedScore, ref: scoreRef } = useCountUp(fScore.overall_score, 1);

  const subScores = [
    {
      name: fScore.coverage.name,
      shortName: "Coverage",
      weight: normalizeWeight(fScore.coverage.weight),
      score: fScore.coverage.score,
      displayScore: fScore.coverage.score,
      details: fScore.coverage.details,
      strengths: fScore.coverage.strengths,
      gaps: fScore.coverage.gaps,
      color: ARC_COLORS.coverage,
      maxPts: 40,
      earnedPts: +(fScore.coverage.score * 0.4).toFixed(1),
    },
    {
      name: fScore.contradiction_penalty.name,
      shortName: "Consistency",
      weight: normalizeWeight(fScore.contradiction_penalty.weight),
      score: fScore.contradiction_penalty.score,
      displayScore: Math.max(0, 100 - fScore.contradiction_penalty.score),
      details: fScore.contradiction_penalty.details,
      strengths: fScore.contradiction_penalty.strengths,
      gaps: fScore.contradiction_penalty.gaps,
      color: ARC_COLORS.contradiction,
      maxPts: 30,
      earnedPts: +(Math.max(0, 100 - fScore.contradiction_penalty.score) * 0.3).toFixed(1),
    },
    {
      name: fScore.structural_clarity.name,
      shortName: "Structure",
      weight: normalizeWeight(fScore.structural_clarity.weight),
      score: fScore.structural_clarity.score,
      displayScore: fScore.structural_clarity.score,
      details: fScore.structural_clarity.details,
      strengths: fScore.structural_clarity.strengths,
      gaps: fScore.structural_clarity.gaps,
      color: ARC_COLORS.structure,
      maxPts: 20,
      earnedPts: +(fScore.structural_clarity.score * 0.2).toFixed(1),
    },
    {
      name: fScore.entailment.name,
      shortName: "Extract",
      weight: normalizeWeight(fScore.entailment.weight),
      score: fScore.entailment.score,
      displayScore: fScore.entailment.score,
      details: fScore.entailment.details,
      strengths: fScore.entailment.strengths,
      gaps: fScore.entailment.gaps,
      color: ARC_COLORS.entailment,
      maxPts: 10,
      earnedPts: +(fScore.entailment.score * 0.1).toFixed(1),
    },
  ];

  // Radar Data
  const radarData = [
    {
      dimension: "Coverage",
      fullName: "Query Intent Coverage (40%)",
      score: fScore.coverage.score,
      fullMark: 100,
    },
    {
      dimension: "Consistency",
      fullName: "Fact Consistency (30%)",
      score: Math.max(0, 100 - fScore.contradiction_penalty.score),
      fullMark: 100,
    },
    {
      dimension: "Structure",
      fullName: "DOM & Schema Structure (20%)",
      score: fScore.structural_clarity.score,
      fullMark: 100,
    },
    {
      dimension: "Extract",
      fullName: "Machine Extractability (10%)",
      score: fScore.entailment.score,
      fullMark: 100,
    },
  ];

  // Bar Chart Data (Earned vs Max)
  const barData = [
    {
      name: "Coverage",
      fullName: "Intent Coverage (40%)",
      earned: +(fScore.coverage.score * 0.4).toFixed(1),
      max: 40,
      fill: ARC_COLORS.coverage,
    },
    {
      name: "Consistency",
      fullName: "Fact Consistency (30%)",
      earned: +(Math.max(0, 100 - fScore.contradiction_penalty.score) * 0.3).toFixed(1),
      max: 30,
      fill: ARC_COLORS.contradiction,
    },
    {
      name: "Structure",
      fullName: "DOM Structure (20%)",
      earned: +(fScore.structural_clarity.score * 0.2).toFixed(1),
      max: 20,
      fill: ARC_COLORS.structure,
    },
    {
      name: "Extract",
      fullName: "Machine Extractability (10%)",
      earned: +(fScore.entailment.score * 0.1).toFixed(1),
      max: 10,
      fill: ARC_COLORS.entailment,
    },
  ];

  const radialData = [
    { name: "Extract", score: fScore.entailment.score, fill: ARC_COLORS.entailment },
    { name: "Structure", score: fScore.structural_clarity.score, fill: ARC_COLORS.structure },
    {
      name: "Consistency",
      score: Math.max(0, 100 - fScore.contradiction_penalty.score),
      fill: ARC_COLORS.contradiction,
    },
    { name: "Coverage", score: fScore.coverage.score, fill: ARC_COLORS.coverage },
  ];

  return (
    <div className="space-y-4 sm:space-y-5 w-full">
      {/* Upper Grid: 3 balanced analytics cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5 items-stretch">
        {/* CARD 1: OVERALL F-SCORE + RADIAL BREAKDOWN */}
        <div className="h-full rounded-2xl bg-surface/90 backdrop-blur-md shadow-border p-5 lg:p-6 flex flex-col justify-between hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Activity size={15} className="text-emerald-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-text-primary">
                Overall Findability Score
              </span>
            </div>
            <span
              className={`rounded-md px-2.5 py-0.5 text-xs font-bold font-mono ${gradeColor(
                fScore.grade
              )}`}
            >
              Grade {fScore.grade}
            </span>
          </div>

          <div className="relative mx-auto my-1.5 h-48 w-48 sm:h-52 sm:w-52 flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                cx="50%"
                cy="50%"
                innerRadius="58%"
                outerRadius="98%"
                barSize={5}
                data={radialData}
                startAngle={90}
                endAngle={-270}
              >
                <RadialBar
                  background={{ fill: "rgba(255, 255, 255, 0.04)" }}
                  dataKey="score"
                  cornerRadius={4}
                />
              </RadialBarChart>
            </ResponsiveContainer>

            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span
                ref={scoreRef}
                className="text-3xl sm:text-[34px] font-bold text-white tracking-tight leading-none"
              >
                {animatedScore}
              </span>
              <span className="text-[9px] font-mono tracking-wider text-text-muted uppercase mt-1.5 font-medium">
                OUT OF 100
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 pt-3.5 border-t border-white/[0.06] text-xs">
            {subScores.map((s) => (
              <div key={s.name} className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5 text-text-muted text-xs">
                  <span
                    className="h-2 w-2 rounded-full shrink-0"
                    style={{ backgroundColor: s.color }}
                  />
                  <span>{s.shortName}</span>
                </span>
                <span className="font-mono font-bold text-white text-xs shrink-0">
                  {s.displayScore.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* CARD 2: WEIGHTED COMPONENT CONTRIBUTION */}
        <div className="h-full rounded-2xl bg-surface/90 backdrop-blur-md shadow-border p-5 lg:p-6 flex flex-col justify-between hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <BarChart3 size={15} className="text-sky-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-text-primary">
                Weighted Contribution
              </span>
            </div>
            <span className="text-[11px] font-mono text-text-muted">Max 100 Pts</span>
          </div>

          <div className="space-y-3.5 my-auto py-2">
            {barData.map((item) => {
              const pct = Math.min(100, Math.round((item.earned / item.max) * 100));
              return (
                <div key={item.name} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-text-primary font-medium text-[11px]">{item.fullName}</span>
                    <span className="font-mono text-text-muted text-[11px]">
                      <span className="text-emerald-400 font-semibold">{item.earned}</span> / {item.max} pts ({pct}%)
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-300"
                      style={{ width: `${pct}%`, backgroundColor: item.fill }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <p className="text-[11px] text-text-muted pt-3 border-t border-white/[0.06]">
            Query coverage (40%) and consistency (30%) drive 70% of total score.
          </p>
        </div>

        {/* CARD 3: RADAR INDEXABILITY PROFILE (NON-CLIPPED) */}
        <div className="h-full rounded-2xl bg-surface/90 backdrop-blur-md shadow-border p-5 lg:p-6 flex flex-col justify-between md:col-span-2 lg:col-span-1 hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Compass size={15} className="text-emerald-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-text-primary">
                Multi-Pillar Radar Profile
              </span>
            </div>
            <span className="text-[11px] font-mono text-text-muted">4-Factor Web</span>
          </div>

          <div className="relative mx-auto my-1 h-44 sm:h-48 w-full flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart
                cx="50%"
                cy="50%"
                outerRadius="68%"
                data={radarData}
                margin={{ top: 8, right: 28, bottom: 8, left: 28 }}
              >
                <PolarGrid stroke="rgba(255,255,255,0.08)" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: "#A1A1A1", fontSize: 11, fontWeight: 500 }}
                />
                <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                <Radar
                  name="Score"
                  dataKey="score"
                  stroke="#10b981"
                  fill="#10b981"
                  fillOpacity={0.25}
                />
                <Tooltip content={<DarkTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <p className="text-[11px] text-text-muted pt-3 border-t border-white/[0.06]">
            Evaluates machine indexability across simulated search intents and consistency.
          </p>
        </div>
      </div>

      {/* LOWER SECTION: COLLAPSIBLE DETAILED SUB-SCORE DIAGNOSTICS */}
      <div className="rounded-xl bg-surface/90 backdrop-blur-md shadow-border overflow-hidden transition-all duration-200">
        <button
          type="button"
          onClick={() => setOpenDiagnostics((prev) => !prev)}
          className="flex w-full items-center justify-between p-3.5 sm:p-4 text-left transition-colors duration-150 hover:bg-surface-secondary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          aria-expanded={openDiagnostics}
        >
          <div className="flex items-center gap-2.5">
            <ShieldCheck size={16} className="text-emerald-400 shrink-0" />
            <span className="text-xs sm:text-sm font-semibold text-text-primary uppercase tracking-wider">
              Detailed Sub-Score Diagnostics, Strengths &amp; Gaps
            </span>
          </div>

          <div className="flex items-center gap-3">
            <span className="rounded-full bg-surface-secondary px-2.5 py-0.5 text-[11px] font-mono text-text-muted shadow-border hidden sm:inline">
              4 Verified Pillars
            </span>
            <div
              className={`flex h-6 w-6 items-center justify-center rounded-md bg-white/[0.04] text-text-muted transition-transform duration-200 ${
                openDiagnostics ? "rotate-180" : ""
              }`}
            >
              <ChevronDown size={14} aria-hidden="true" />
            </div>
          </div>
        </button>

        {openDiagnostics && (
          <div className="p-4 sm:p-5 pt-0 border-t border-white/[0.06] mt-1 space-y-4 animate-fade-in">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 pt-3">
              {subScores.map((s) => (
                <div
                  key={s.name}
                  className="rounded-xl bg-surface-secondary/80 shadow-border p-3.5 space-y-2.5 text-xs flex flex-col justify-between transition-all duration-150 hover:bg-surface-secondary hover:border-white/[0.12]"
                >
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2 truncate">
                        <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                        <span className="font-semibold text-text-primary truncate">{s.shortName}</span>
                      </div>
                      <span className="font-mono text-text-muted shrink-0 text-[11px]">
                        {s.weight}% &bull; {s.score.toFixed(0)}
                      </span>
                    </div>
                    <p className="text-text-muted text-[11px] leading-relaxed">{s.details}</p>
                  </div>

                  <div className="space-y-2 pt-2 border-t border-white/[0.06]">
                    {s.strengths.length > 0 && (
                      <div>
                        <p className="font-medium text-emerald-400 flex items-center gap-1 text-[10px] uppercase tracking-wider mb-1">
                          <ShieldCheck size={11} /> Strengths
                        </p>
                        <ul className="space-y-0.5 text-text-muted text-[11px]">
                          {s.strengths.map((str, i) => (
                            <li key={i} className="flex items-start gap-1">
                              <span className="text-emerald-400">&bull;</span>
                              <span>{str}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {s.gaps.length > 0 && (
                      <div>
                        <p className="font-medium text-rose-400 flex items-center gap-1 text-[10px] uppercase tracking-wider mb-1">
                          <AlertTriangle size={11} /> Gaps
                        </p>
                        <ul className="space-y-0.5 text-text-muted text-[11px]">
                          {s.gaps.map((gap, i) => (
                            <li key={i} className="flex items-start gap-1">
                              <span className="text-rose-400">&bull;</span>
                              <span>{gap}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}