"use client";

import { useId } from "react";
import type { LucideIcon } from "lucide-react";
import type { EngineKey, CriterionDetail } from "@/types/lighthouse";
import { useCountUp } from "@/hooks/useCountUp";
import {
  lighthouseTier,
  lighthouseTierColor,
  lighthouseTierStroke,
  lighthouseTierLabel,
} from "@/lib/format";

interface LighthouseGaugeProps {
  score: number;
  label: string;
  engineKey: EngineKey | string;
  icon: LucideIcon;
  accentColorClass: string;
  criteria?: Record<string, CriterionDetail>;
}

export function LighthouseGauge({
  score,
  label,
  engineKey,
  icon: Icon,
  accentColorClass,
  criteria,
}: LighthouseGaugeProps) {
  const gradientId = useId();
  const clampedScore = Math.min(100, Math.max(0, Math.round(score)));
  const { value: animatedScore, ref: scoreRef } = useCountUp(clampedScore, 0);
  const tier = lighthouseTier(clampedScore);
  const strokeColor = lighthouseTierStroke(clampedScore);
  const tierColor = lighthouseTierColor(clampedScore);

  // SVG circular arc geometry
  const size = 98;
  const strokeWidth = 7;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const progressOffset = circumference - (clampedScore / 100) * circumference;

  return (
    <div
      data-testid={`lighthouse-gauge-${engineKey}`}
      className="group relative flex flex-col items-center rounded-xl bg-surface-secondary/70 p-3 sm:p-3.5 shadow-border transition-all duration-200 hover:bg-surface-secondary"
    >
      {/* Engine Header */}
      <div className="mb-2 flex items-center gap-1.5">
        <div
          className={`flex h-4.5 w-4.5 items-center justify-center rounded-md bg-white/[0.04] shadow-border ${accentColorClass}`}
        >
          <Icon size={11} aria-hidden="true" />
        </div>
        <span className="text-xs font-semibold tracking-tight text-white">
          {label}
        </span>
      </div>

      {/* Circular Gauge Arc */}
      <div className="relative flex items-center justify-center">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-90 transform"
          aria-label={`${label} Readiness Score: ${clampedScore} out of 100`}
          role="img"
        >
          <defs>
            <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.9" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="1" />
            </linearGradient>
          </defs>

          {/* Background track circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="rgba(255, 255, 255, 0.07)"
            strokeWidth={strokeWidth}
          />

          {/* Value Progress Arc */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={`url(#${gradientId})`}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={progressOffset}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        </svg>

        {/* Center Score Readout */}
        <div className="absolute flex flex-col items-center justify-center text-center">
          <span ref={scoreRef} className={`font-mono text-xl font-bold tracking-tight ${tierColor}`}>
            {animatedScore}
          </span>
          <span className="text-[8px] font-medium uppercase tracking-wider text-text-muted">
            / 100
          </span>
        </div>
      </div>

      {/* Tier Badge */}
      <div className="mt-1.5 flex items-center gap-1.5">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[9.5px] font-medium border border-white/[0.08] ${
            tier === "good"
              ? "bg-emerald-950/60 text-emerald-300"
              : tier === "needs_improvement"
              ? "bg-amber-950/60 text-amber-300"
              : "bg-rose-950/60 text-rose-300"
          }`}
        >
          {lighthouseTierLabel(tier)}
        </span>
      </div>

      {/* Criteria Breakdown mini list if provided */}
      {criteria && Object.keys(criteria).length > 0 && (
        <div className="mt-2.5 w-full border-t border-white/[0.06] pt-2 text-[10px]">
          <div className="space-y-0.5">
            {Object.entries(criteria).slice(0, 3).map(([key, item]) => {
              const formattedName = key
                .replace(/_/g, " ")
                .replace(/\b\w/g, (l) => l.toUpperCase());
              return (
                <div
                  key={key}
                  className="flex items-center justify-between text-text-muted"
                >
                  <span className="truncate pr-1 text-[9.5px]">{formattedName}</span>
                  <span className="font-mono font-medium text-text-primary text-[9.5px]">
                    {item.score}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

