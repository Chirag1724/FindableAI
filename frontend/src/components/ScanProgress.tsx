"use client";

import { CheckCircle, AlertTriangle, Circle } from "lucide-react";
import type { ScanStatusEvent, ScanStatus } from "@/types/scan";
import { PHASES, getPhaseStateWithFallback } from "@/lib/phases";
import type { PhaseState } from "@/lib/phases";

interface ScanProgressProps {
  currentStatus: ScanStatus;
  latestEvent: ScanStatusEvent | null;
  lastGoodStatus: ScanStatus | null;
}

function PhaseIndicator({ state, label, id }: { state: PhaseState; label: string; id: string }) {
  const baseStep = `relative flex flex-col items-center gap-2 min-w-[72px]`;
  return (
    <div
      data-testid={`phase-step-${id}`}
      className={baseStep}
      aria-current={state === "active" ? "step" : undefined}
    >
      {/* Icon */}
      <div
        className={`relative z-10 flex h-8 w-8 items-center justify-center rounded-full transition-all duration-300 ${
          state === "done"
            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
            : state === "active"
              ? "bg-violet-500/20 text-violet-300 ring-2 ring-violet-500/50"
              : state === "error"
                ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                : "bg-surface-secondary shadow-border text-text-muted"
        }`}
      >
        {state === "done" && <CheckCircle size={15} aria-hidden="true" />}
        {state === "active" && (
          <span
            className="absolute inset-0 rounded-full animate-ping bg-violet-500/30"
            aria-hidden="true"
          />
        )}
        {state === "active" && (
          <Circle size={9} fill="currentColor" aria-hidden="true" />
        )}
        {state === "error" && <AlertTriangle size={15} aria-hidden="true" />}
        {state === "pending" && <Circle size={7} fill="currentColor" aria-hidden="true" />}
      </div>

      {/* Label */}
      <span
        className={`text-[10px] font-semibold tracking-wider uppercase transition-colors duration-200 ${
          state === "active"
            ? "text-violet-300"
            : state === "done"
              ? "text-emerald-400"
              : state === "error"
                ? "text-rose-400"
                : "text-text-muted"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

export function ScanProgress({
  currentStatus,
  latestEvent,
  lastGoodStatus,
}: ScanProgressProps) {
  const progressPercent = latestEvent?.progress_percent ?? 0;
  const currentStep = latestEvent?.current_step ?? "";
  const message = latestEvent?.message ?? "";

  return (
    <div className="rounded-xl bg-surface shadow-border p-5">
      {/* Phase stepper - horizontal scroll on small screens */}
      <div className="overflow-x-auto pb-2 -mx-1 px-1 custom-scrollbar">
        <ol
          role="list"
          className="flex items-start gap-0 min-w-max"
          aria-label="Scan pipeline phases"
        >
          {PHASES.map((phase, i) => {
            const state = getPhaseStateWithFallback(
              currentStatus,
              lastGoodStatus,
              i
            );
            return (
              <li key={phase.id} className="flex items-start">
                <PhaseIndicator state={state} label={phase.label} id={phase.id} />
                {/* Connector line between phases */}
                {i < PHASES.length - 1 && (
                  <div
                    aria-hidden="true"
                    className={`mt-4 h-px w-8 transition-colors duration-300 ${
                      state === "done" ? "bg-emerald-500/40" : "bg-white/[0.08]"
                    }`}
                  />
                )}
              </li>
            );
          })}
        </ol>
      </div>

      {/* Progress bar */}
      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-text-muted">{currentStep}</span>
          <span className="font-mono text-xs text-text-muted">{progressPercent}%</span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-surface-secondary shadow-border"
          role="progressbar"
          aria-valuenow={progressPercent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Scan progress"
        >
          <div
            className="h-full rounded-full bg-violet-500 transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Live message */}
      {message && (
        <p
          className="mt-3 font-mono text-xs text-text-muted"
          aria-live="polite"
          aria-atomic="true"
        >
          {message}
        </p>
      )}
    </div>
  );
}