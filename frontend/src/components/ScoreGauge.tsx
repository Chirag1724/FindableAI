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
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from "recharts";
import {
  ChevronDown,
  ChevronUp,
  Activity,
  Compass,
  BarChart3,
  PieChart as PieIcon,
  ShieldCheck,
  AlertTriangle,
} from "lucide-react";
import type { FScoreBreakdown } from "@/types/scan";
import { useCountUp } from "@/hooks/useCountUp";
import { normalizeWeight } from "@/lib/normalize";
import { gradeColor } from "@/lib/format";

interface ScoreGaugeProps {
  fScore: FScoreBreakdown;
}

const ARC_COLORS = {
  coverage: "#8b5cf6", // violet-500
  entailment: "#10b981", // emerald-500
  contradiction: "#f43f5e", // rose-500
  structure: "#38bdf8", // sky-400
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
    <div className="rounded-lg bg-[#1c1c1c] px-3 py-2 text-xs text-[#EDEDED] shadow-xl border border-white/10">
      <div className="font-medium text-white mb-0.5">
        {p?.fullName ?? p?.dimension ?? p?.name ?? item.name}
      </div>
      {p?.earned !== undefined && p?.max !== undefined ? (
        <div className="text-[#A1A1A1]">
          Earned: <span className="font-mono text-emerald-400 font-semibold">{p.earned}</span> / {p.max} pts
        </div>
      ) : (
        <div className="text-[#A1A1A1]">
          Score: <span className="font-mono text-emerald-400 font-semibold">{item.value?.toFixed(1)}</span> / 100
        </div>
      )}
    </div>
  );
}

export function ScoreGauge({ fScore }: ScoreGaugeProps) {
  const { value: animatedScore, ref: scoreRef } = useCountUp(fScore.overall_score, 1);
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  const subScores = [
    {
      name: fScore.coverage.name,
      shortName: "Coverage",
      weight: normalizeWeight(fScore.coverage.weight),
      score: fScore.coverage.score,
      details: fScore.coverage.details,
      strengths: fScore.coverage.strengths,
      gaps: fScore.coverage.gaps,
      color: ARC_COLORS.coverage,
      fill: ARC_COLORS.coverage,
      value: fScore.coverage.score,
      maxPts: 40,
      earnedPts: +(fScore.coverage.score * 0.4).toFixed(1),
    },
    {
      name: fScore.contradiction_penalty.name,
      shortName: "Consistency",
      weight: normalizeWeight(fScore.contradiction_penalty.weight),
      score: fScore.contradiction_penalty.score,
      details: fScore.contradiction_penalty.details,
      strengths: fScore.contradiction_penalty.strengths,
      gaps: fScore.contradiction_penalty.gaps,
      color: ARC_COLORS.contradiction,
      fill: ARC_COLORS.contradiction,
      value: Math.max(0, 100 - fScore.contradiction_penalty.score),
      maxPts: 30,
      earnedPts: +(Math.max(0, 100 - fScore.contradiction_penalty.score) * 0.3).toFixed(1),
    },
    {
      name: fScore.structural_clarity.name,
      shortName: "Structure",
      weight: normalizeWeight(fScore.structural_clarity.weight),
      score: fScore.structural_clarity.score,
      details: fScore.structural_clarity.details,
      strengths: fScore.structural_clarity.strengths,
      gaps: fScore.structural_clarity.gaps,
      color: ARC_COLORS.structure,
      fill: ARC_COLORS.structure,
      value: fScore.structural_clarity.score,
      maxPts: 20,
      earnedPts: +(fScore.structural_clarity.score * 0.2).toFixed(1),
    },
    {
      name: fScore.entailment.name,
      shortName: "Extract",
      weight: normalizeWeight(fScore.entailment.weight),
      score: fScore.entailment.score,
      details: fScore.entailment.details,
      strengths: fScore.entailment.strengths,
      gaps: fScore.entailment.gaps,
      color: ARC_COLORS.entailment,
      fill: ARC_COLORS.entailment,
      value: fScore.entailment.score,
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
      fullName: "Query Intent Coverage",
      earned: +(fScore.coverage.score * 0.4).toFixed(1),
      max: 40,
      fill: ARC_COLORS.coverage,
    },
    {
      name: "Consistency",
      fullName: "Fact Consistency",
      earned: +(Math.max(0, 100 - fScore.contradiction_penalty.score) * 0.3).toFixed(1),
      max: 30,
      fill: ARC_COLORS.contradiction,
    },
    {
      name: "Structure",
      fullName: "DOM & Schema Structure",
      earned: +(fScore.structural_clarity.score * 0.2).toFixed(1),
      max: 20,
      fill: ARC_COLORS.structure,
    },
    {
      name: "Extract",
      fullName: "Machine Extractability",
      earned: +(fScore.entailment.score * 0.1).toFixed(1),
      max: 10,
      fill: ARC_COLORS.entailment,
    },
  ];

  // Pie / Donut Chart Data
  const pieData = [
    {
      name: "Query Coverage",
      value: Math.max(1, +(fScore.coverage.score * 0.4).toFixed(1)),
      color: ARC_COLORS.coverage,
    },
    {
      name: "Fact Consistency",
      value: Math.max(1, +(Math.max(0, 100 - fScore.contradiction_penalty.score) * 0.3).toFixed(1)),
      color: ARC_COLORS.contradiction,
    },
    {
      name: "Schema Structure",
      value: Math.max(1, +(fScore.structural_clarity.score * 0.2).toFixed(1)),
      color: ARC_COLORS.structure,
    },
    {
      name: "Extractability",
      value: Math.max(1, +(fScore.entailment.score * 0.1).toFixed(1)),
      color: ARC_COLORS.entailment,
    },
  ];

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Section Title */}
      <div className="flex items-center justify-between">
        <h2 className="text-xs sm:text-sm font-semibold uppercase tracking-wider text-[#A1A1A1] flex items-center gap-2">
          <Activity size={14} className="text-emerald-400" />
          Findability Analytics Matrix (2&times;2)
        </h2>
        <span className="text-xs text-[#A1A1A1] font-mono">
          Formula: <span className="text-emerald-400">0.40S_ans + 0.30S_con + 0.20S_str + 0.10S_acc</span>
        </span>
      </div>

      {/* 2x2 Analytics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        {/* CARD 1: RADIAL GAUGE & AUDIT GRADE */}
        <div
          className="rounded-2xl bg-[#141414] p-5 sm:p-6 flex flex-col justify-between"
          style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Activity size={14} className="text-purple-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#EDEDED]">
                Findability F-Score
              </span>
            </div>
            <span
              className={`px-2.5 py-0.5 rounded text-xs font-black ${gradeColor(fScore.grade)} bg-white/5 border border-white/10`}
            >
              Grade {fScore.grade}
            </span>
          </div>

          {/* Radial Center Graphic */}
          <div className="relative mx-auto my-2 h-44 w-44 sm:h-52 sm:w-52">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="40%"
                outerRadius="100%"
                startAngle={90}
                endAngle={-270}
                data={subScores}
                barSize={9}
              >
                <RadialBar
                  dataKey="value"
                  cornerRadius={5}
                  background={{ fill: "rgba(255,255,255,0.04)" }}
                />
              </RadialBarChart>
            </ResponsiveContainer>

            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span
                ref={scoreRef}
                data-testid="f-score-value"
                className="text-4xl font-black text-[#EDEDED] tabular-nums"
              >
                {animatedScore}
              </span>
              <span className={`text-base font-bold ${gradeColor(fScore.grade)}`}>
                {fScore.grade}
              </span>
            </div>
          </div>

          {/* Quick Subscore Status Pills */}
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/5">
            {subScores.map((s) => (
              <div key={s.name} className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-[#191919] text-xs">
                <span className="flex items-center gap-1.5 truncate text-[#A1A1A1]">
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                  {s.shortName}
                </span>
                <span className="font-mono text-[#EDEDED] font-semibold">{s.score.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* CARD 2: AEO DISCOVERABILITY RADAR */}
        <div
          className="rounded-2xl bg-[#141414] p-5 sm:p-6 flex flex-col justify-between"
          style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Compass size={14} className="text-emerald-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#EDEDED]">
                AEO Discoverability Radar
              </span>
            </div>
            <span className="text-[11px] text-[#A1A1A1]">4-Axis Polygon</span>
          </div>

          <div className="relative mx-auto my-1 h-48 w-full sm:h-56">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData} outerRadius="75%">
                <PolarGrid stroke="rgba(255,255,255,0.1)" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: "#A1A1A1", fontSize: 11 }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={false}
                  axisLine={false}
                />
                <Radar
                  name="Findability"
                  dataKey="score"
                  stroke="#8b5cf6"
                  fill="#8b5cf6"
                  fillOpacity={0.4}
                />
                <Tooltip content={<DarkTooltip />} />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          <p className="text-[11px] text-[#A1A1A1] pt-2 border-t border-white/5">
            Evaluates machine indexability across simulated search intents, consistency, and DOM schema coverage.
          </p>
        </div>

        {/* CARD 3: WEIGHTED CONTRIBUTION BARS */}
        <div
          className="rounded-2xl bg-[#141414] p-5 sm:p-6 flex flex-col justify-between"
          style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <BarChart3 size={14} className="text-sky-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#EDEDED]">
                Weighted Component Contribution
              </span>
            </div>
            <span className="text-[11px] font-mono text-[#A1A1A1]">Max 100 Pts</span>
          </div>

          <div className="space-y-3.5 my-auto py-2">
            {barData.map((item) => {
              const pct = Math.min(100, Math.round((item.earned / item.max) * 100));
              return (
                <div key={item.name} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-[#EDEDED] font-medium">{item.fullName}</span>
                    <span className="font-mono text-[#A1A1A1]">
                      <span className="text-emerald-400 font-semibold">{item.earned}</span> / {item.max} pts ({pct}%)
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, backgroundColor: item.fill }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <p className="text-[11px] text-[#A1A1A1] pt-2 border-t border-white/5">
            Query coverage (40%) and consistency (30%) drive 70% of total discoverability score.
          </p>
        </div>

        {/* CARD 4: POINTS ALLOCATION DONUT & PENALTIES */}
        <div
          className="rounded-2xl bg-[#141414] p-5 sm:p-6 flex flex-col justify-between"
          style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <PieIcon size={14} className="text-rose-400" />
              <span className="text-xs font-bold uppercase tracking-wider text-[#EDEDED]">
                Points Share &amp; Gap Distribution
              </span>
            </div>
            <span className="text-[11px] text-rose-400 font-mono">
              -{fScore.contradiction_penalty.score.toFixed(1)} pts penalty
            </span>
          </div>

          <div className="relative mx-auto my-1 h-44 w-full sm:h-52 flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={74}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                  ))}
                </Pie>
                <Tooltip content={<DarkTooltip />} />
              </PieChart>
            </ResponsiveContainer>

            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-2xl font-black text-[#EDEDED] tabular-nums">
                {animatedScore}
              </span>
              <span className="text-[9px] text-[#A1A1A1] uppercase font-bold tracking-wider">
                Earned Pts
              </span>
            </div>
          </div>

          <p className="text-[11px] text-[#A1A1A1] pt-2 border-t border-white/5 flex items-center justify-between">
            <span>Contradiction Deduction:</span>
            <span className="font-mono text-rose-400 font-semibold">
              -{fScore.contradiction_penalty.score.toFixed(1)} pts
            </span>
          </p>
        </div>
      </div>

      {/* Expandable Diagnostic Evidence Accordion (Strengths & Gaps) */}
      <div
        className="rounded-xl bg-[#141414] overflow-hidden"
        style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
      >
        <button
          type="button"
          onClick={() => setDetailsExpanded((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-white/5"
        >
          <span className="text-xs font-semibold text-[#EDEDED] flex items-center gap-2">
            <ShieldCheck size={14} className="text-emerald-400" />
            Detailed Sub-Score Diagnostics, Strengths &amp; Gaps
          </span>
          <div className="flex items-center gap-2 text-xs text-[#A1A1A1]">
            <span>{detailsExpanded ? "Hide" : "Show"} Diagnostics</span>
            {detailsExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </div>
        </button>

        {detailsExpanded && (
          <div className="border-t border-white/5 p-4 sm:p-5 grid grid-cols-1 md:grid-cols-2 gap-4">
            {subScores.map((s) => (
              <div key={s.name} className="rounded-lg bg-[#191919] p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                    <span className="font-semibold text-[#EDEDED]">{s.name}</span>
                  </div>
                  <span className="font-mono text-[#A1A1A1]">{s.weight}% &bull; {s.score.toFixed(1)}</span>
                </div>
                <p className="text-[#A1A1A1]">{s.details}</p>
                {s.strengths.length > 0 && (
                  <div className="pt-1">
                    <p className="font-medium text-emerald-400 flex items-center gap-1 mb-1">
                      <ShieldCheck size={12} /> Strengths
                    </p>
                    <ul className="space-y-0.5 list-disc list-inside text-[#A1A1A1]">
                      {s.strengths.map((str, i) => (
                        <li key={i}>{str}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {s.gaps.length > 0 && (
                  <div className="pt-1">
                    <p className="font-medium text-rose-400 flex items-center gap-1 mb-1">
                      <AlertTriangle size={12} /> Gaps
                    </p>
                    <ul className="space-y-0.5 list-disc list-inside text-[#A1A1A1]">
                      {s.gaps.map((gap, i) => (
                        <li key={i}>{gap}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}