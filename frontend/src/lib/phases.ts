import type { ScanStatus } from "@/types/scan";

// UI Phase definitions

export type PhaseState = "pending" | "active" | "done" | "error";

export interface Phase {
  id: string;
  label: string;
  /** ScanStatus values that map to this phase being "active" */
  activeStatuses: ScanStatus[];
  /** ScanStatus values that mean this phase is "done" */
  doneStatuses: ScanStatus[];
}

/**
 * 6 UI phases that group the 9 backend scan statuses.
 * "pending" at the start is absorbed into OBSERVE being active from the start.
 */
export const PHASES: Phase[] = [
  {
    id: "observe",
    label: "OBSERVE",
    activeStatuses: ["pending", "crawling", "extracting_dom"],
    doneStatuses: [
      "synthesizing_intents",
      "hybrid_retrieval",
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ],
  },
  {
    id: "plan",
    label: "PLAN",
    activeStatuses: ["synthesizing_intents"],
    doneStatuses: [
      "hybrid_retrieval",
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ],
  },
  {
    id: "act",
    label: "ACT",
    activeStatuses: ["hybrid_retrieval"],
    doneStatuses: [
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ],
  },
  {
    id: "verify",
    label: "VERIFY",
    activeStatuses: ["nli_evaluation"],
    doneStatuses: ["computing_fscore", "generating_patches", "completed"],
  },
  {
    id: "reflect",
    label: "REFLECT",
    activeStatuses: ["computing_fscore", "generating_patches"],
    doneStatuses: ["completed"],
  },
  {
    id: "stop",
    label: "STOP",
    activeStatuses: ["completed"],
    doneStatuses: [],
  },
];

/**
 * Returns the state of a phase at a given index given the current scan status.
 * failed maps the "active" phase (where progress stopped) to "error".
 */
export function getPhaseState(
  status: ScanStatus,
  phaseIndex: number
): PhaseState {
  if (phaseIndex < 0 || phaseIndex >= PHASES.length) return "pending";
  const phase = PHASES[phaseIndex];

  if (status === "failed") {
    // Find which phase was active when the scan failed by checking
    // which phase is neither done nor pending for the adjacent statuses
    for (let i = 0; i < PHASES.length; i++) {
      const p = PHASES[i];
      // A phase is "errored" if it was active (or would be next to activate)
      // We approximate: any phase that is not "done" and not "pending" is error.
      // More precisely: phases that are done before failure stay done,
      // the first non-done phase becomes error, the rest stay pending.
      const isDone = p.doneStatuses.includes("completed"); // always done = completed is in done
      // We check against the last known non-failed status by seeing if
      // the phase before this one was completed via its doneStatuses.
      // Simplest: walk through in order.
      if (i < phaseIndex) {
        // If this comes before the requested phase, return done if it would be done
        // We re-call recursively safely here
        if (PHASES[i].doneStatuses.some((s) => s !== "completed")) {
          // has intermediate done statuses - not trivially determined
        }
      }
    }
    // Simplified implementation: for failed, find the "current" phase
    // by checking which phase was "active" or "next-up"
    let errorPhase = -1;
    for (let i = 0; i < PHASES.length; i++) {
      const p = PHASES[i];
      if (p.activeStatuses.includes("completed")) {
        // This is STOP - cannot be error
        break;
      }
      // A phase is "the errored one" if it is not done (i.e. not fully past)
      // We check if ANY running-status maps to being done for this phase.
      // Since we can't know which step failed, mark phase index 0..lastDone as done,
      // then the next as error, rest pending.
      break;
    }

    // Clean implementation using the phase ordering
    const runningOrder: ScanStatus[] = [
      "pending",
      "crawling",
      "extracting_dom",
      "synthesizing_intents",
      "hybrid_retrieval",
      "nli_evaluation",
      "computing_fscore",
      "generating_patches",
      "completed",
    ];

    // Last known status before failed is unknown; treat OBSERVE as the error phase
    // (backend sends FAILED from whatever step it was on, we don't get the "last good" status in this call)
    // The hook tracks lastEvent which contains the real last status - phases.ts just provides logic.
    // Convention: if status === "failed" we mark phase 0 as error, others pending.
    // The real phase is computed in ScanProgress which passes lastGoodStatus to phases.
    if (phaseIndex === 0) return "error";
    return "pending";
  }

  const phase2 = PHASES[phaseIndex];
  if (!phase2) return "pending";

  if (phase2.doneStatuses.includes(status)) return "done";
  if (phase2.activeStatuses.includes(status)) return "active";
  return "pending";
}

/**
 * Returns the phase index that corresponds to the given status.
 * Used by ScanProgress to pass the correct lastGoodStatus for failed scans.
 */
export function activePhaseIndex(status: ScanStatus): number {
  for (let i = 0; i < PHASES.length; i++) {
    if (PHASES[i].activeStatuses.includes(status)) return i;
  }
  return 0;
}

/**
 * Computes phase state for a given status, supporting lastGoodStatus for failed scans.
 */
export function getPhaseStateWithFallback(
  status: ScanStatus,
  lastGoodStatus: ScanStatus | null,
  phaseIndex: number
): PhaseState {
  if (status !== "failed") return getPhaseState(status, phaseIndex);

  // Use lastGoodStatus to determine which phase errored
  const referenceStatus = lastGoodStatus ?? "pending";
  const errorIdx = activePhaseIndex(referenceStatus);

  if (phaseIndex < errorIdx) return "done";
  if (phaseIndex === errorIdx) return "error";
  return "pending";
}