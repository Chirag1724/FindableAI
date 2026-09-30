"use client";

import { useState } from "react";
import {
  RadialBarChart, RadialBar, ResponsiveContainer,
} from "recharts";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { FScoreBreakdown } from "@/types/scan";
import { useCountUp } from "@/hooks/useCountUp";
import { normalizeWeight } from "@/lib/normalize";
import { gradeColor } from "@/lib/format";

interface ScoreGaugeProps {
  fScore: FScoreBreakdown;
}

interface SubScoreRowProps {
  name: string;
  weight: number;
  score: number;
  details: string;
  strengths: string[];
  gaps: string[];
  color: string;
}

function SubScoreRow({ name, weight, score, details, strengths, gaps, color }: SubScoreRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg bg-[#191919] overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset"
      >
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        <span className="flex-1 text-xs text-[#EDEDED] truncate">{name}</span>
        <span className="font-mono text-xs text-[#A1A1A1]">
          {weight}% &middot; {score.toFixed(1)}
        </span>
        {expanded ? (
          <ChevronUp size={12} className="text-[#A1A1A1] shrink-0" aria-hidden="true" />
        ) : (
          <ChevronDown size={12} className="text-[#A1A1A1] shrink-0" aria-hidden="true" />
        )}
      </button>
      {expanded && (
        <div className="px-4 pb-3 pt-1 space-y-2 text-xs">
          <p className="text-[#A1A1A1]">{details}</p>
          {strengths.length > 0 && (
            <div>
              <p className="font-medium text-emerald-400 mb-1">Strengths</p>
              <ul className="space-y-0.5 list-disc list-inside text-[#A1A1A1]">
                {strengths.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
          {gaps.length > 0 && (
            <div>
              <p className="font-medium text-rose-400 mb-1">Gaps</p>
              <ul className="space-y-0.5 list-disc list-inside text-[#A1A1A1]">
                {gaps.map((g, i) => <li key={i}>{g}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const ARC_COLORS = {
  coverage: "#7c3aed",       // violet-700
  entailment: "#059669",      // emerald-600
  contradiction: "#e11d48",   // rose-600
  structure: "#0284c7",       // sky-600
};

export function ScoreGauge({ fScore }: ScoreGaugeProps) {
  const { value: animatedScore, ref: scoreRef } = useCountUp(
    fScore.overall_score,
    1
  );

  const subScores = [
    {
      name: fScore.coverage.name,
      weight: normalizeWeight(fScore.coverage.weight),
      score: fScore.coverage.score,
      details: fScore.coverage.details,
      strengths: fScore.coverage.strengths,
      gaps: fScore.coverage.gaps,
      color: ARC_COLORS.coverage,
      fill: ARC_COLORS.coverage,
      value: fScore.coverage.score,
    },
    {
      name: fScore.entailment.name,
      weight: normalizeWeight(fScore.entailment.weight),
      score: fScore.entailment.score,
      details: fScore.entailment.details,
      strengths: fScore.entailment.strengths,
      gaps: fScore.entailment.gaps,
      color: ARC_COLORS.entailment,
      fill: ARC_COLORS.entailment,
      value: fScore.entailment.score,
    },
    {
      name: fScore.contradiction_penalty.name,
      weight: normalizeWeight(fScore.contradiction_penalty.weight),
      score: fScore.contradiction_penalty.score,
      details: fScore.contradiction_penalty.details,
      strengths: fScore.contradiction_penalty.strengths,
      gaps: fScore.contradiction_penalty.gaps,
      color: ARC_COLORS.contradiction,
      fill: ARC_COLORS.contradiction,
      // Invert for display in chart (penalty, so lower value = worse)
      value: Math.max(0, 100 - fScore.contradiction_penalty.score),
    },
    {
      name: fScore.structural_clarity.name,
      weight: normalizeWeight(fScore.structural_clarity.weight),
      score: fScore.structural_clarity.score,
      details: fScore.structural_clarity.details,
      strengths: fScore.structural_clarity.strengths,
      gaps: fScore.structural_clarity.gaps,
      color: ARC_COLORS.structure,
      fill: ARC_COLORS.structure,
      value: fScore.structural_clarity.score,
    },
  ];

  return (
    <div
      className="rounded-2xl bg-[#141414] p-5 sm:p-8"
      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
    >
      <h2 className="mb-3 sm:mb-4 text-sm font-semibold uppercase tracking-wider text-[#A1A1A1]">
        Findability F-Score
      </h2>

      {/* Radial chart + center score */}
      <div className="relative mx-auto mb-4 sm:mb-6 h-40 w-40 sm:h-56 sm:w-56">
        <ResponsiveContainer width="100%" height="100%">
          <RadialBarChart
            innerRadius="40%"
            outerRadius="100%"
            startAngle={90}
            endAngle={-270}
            data={subScores}
            barSize={10}
          >
            <RadialBar
              dataKey="value"
              cornerRadius={5}
              background={{ fill: "rgba(255,255,255,0.04)" }}
            />
          </RadialBarChart>
        </ResponsiveContainer>

        {/* Center F-Score */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span
            ref={scoreRef}
            data-testid="f-score-value"
            className="text-4xl font-black text-[#EDEDED] tabular-nums"
          >
            {animatedScore}
          </span>
          <span
            className={`text-lg font-bold ${gradeColor(fScore.grade)}`}
          >
            {fScore.grade}
          </span>
        </div>
      </div>

      {/* Sub-score legend rows */}
      <div className="space-y-2">
        {subScores.map((s) => (
          <SubScoreRow key={s.name} {...s} />
        ))}
      </div>

      {/* Contradiction penalty note */}
      <p className="mt-3 sm:mt-4 text-[10px] text-[#A1A1A1]">
        Contradiction penalty shown as -{fScore.contradiction_penalty.score.toFixed(1)} pts (lower = more contradictions)
      </p>
    </div>
  );
}