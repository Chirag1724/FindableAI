"use client";

import type { AuditSummary } from "@/types/scan";
import { useCountUp } from "@/hooks/useCountUp";
import { formatDuration } from "@/lib/format";

interface StatCardProps {
  label: string;
  value: number;
  suffix?: string;
  decimals?: number;
  isDuration?: boolean;
  className?: string;
}

function StatCard({ label, value, suffix = "", decimals = 0, isDuration = false, className = "" }: StatCardProps) {
  const { value: animatedValue, ref } = useCountUp(value, isDuration ? 1 : decimals);

  return (
    <div
      className={`rounded-xl bg-surface shadow-border shadow-border-interactive px-4 py-4 sm:px-5 sm:py-5 ${className}`}
    >
      <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </p>
      <p className="text-2xl font-bold text-text-primary tabular-nums">
        <span ref={ref}>
          {isDuration ? formatDuration(value) : `${animatedValue}${suffix}`}
        </span>
      </p>
    </div>
  );
}

export function SummaryStats({ summary }: { summary: AuditSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 sm:grid-cols-3 lg:grid-cols-5">
      <StatCard label="Pages crawled" value={summary.pages_crawled} />
      <StatCard label="DOM chunks" value={summary.dom_chunks_extracted} />
      <StatCard label="Intents tested" value={summary.intents_generated} />
      <StatCard label="Contradictions" value={summary.contradictions_detected} />
      <StatCard
        label="Duration"
        value={summary.execution_time_seconds}
        isDuration
        className="col-span-2 sm:col-span-1"
      />
    </div>
  );
}