import { describe, it, expect } from "vitest";
import {
  PHASES,
  getPhaseState,
  getPhaseStateWithFallback,
  activePhaseIndex,
} from "@/lib/phases";
import type { ScanStatus } from "@/types/scan";

// Pipeline order: one status per logical step
const PIPELINE_ORDER: ScanStatus[] = [
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

// --- PHASES structure sanity ---

describe("PHASES constant", () => {
  it("has exactly 6 phases", () => {
    expect(PHASES).toHaveLength(6);
  });

  it("phases are named OBSERVE, PLAN, ACT, VERIFY, REFLECT, STOP", () => {
    const labels = PHASES.map((p) => p.label);
    expect(labels).toEqual(["OBSERVE", "PLAN", "ACT", "VERIFY", "REFLECT", "STOP"]);
  });
});

// --- getPhaseState for each status ---

describe("getPhaseState - OBSERVE (index 0)", () => {
  it("is 'active' for pending", () => expect(getPhaseState("pending", 0)).toBe("active"));
  it("is 'active' for crawling", () => expect(getPhaseState("crawling", 0)).toBe("active"));
  it("is 'active' for extracting_dom", () => expect(getPhaseState("extracting_dom", 0)).toBe("active"));
  it("is 'done' for synthesizing_intents", () => expect(getPhaseState("synthesizing_intents", 0)).toBe("done"));
  it("is 'done' for completed", () => expect(getPhaseState("completed", 0)).toBe("done"));
  it("is 'error' for failed (no lastGoodStatus)", () => expect(getPhaseState("failed", 0)).toBe("error"));
});

describe("getPhaseState - PLAN (index 1)", () => {
  it("is 'active' for synthesizing_intents", () => expect(getPhaseState("synthesizing_intents", 1)).toBe("active"));
  it("is 'done' for hybrid_retrieval", () => expect(getPhaseState("hybrid_retrieval", 1)).toBe("done"));
  it("is 'pending' for pending", () => expect(getPhaseState("pending", 1)).toBe("pending"));
  it("is 'pending' for failed (default to observe as error)", () => expect(getPhaseState("failed", 1)).toBe("pending"));
});

describe("getPhaseState - ACT (index 2)", () => {
  it("is 'active' for hybrid_retrieval", () => expect(getPhaseState("hybrid_retrieval", 2)).toBe("active"));
  it("is 'done' for nli_evaluation", () => expect(getPhaseState("nli_evaluation", 2)).toBe("done"));
  it("is 'pending' for pending", () => expect(getPhaseState("pending", 2)).toBe("pending"));
});

describe("getPhaseState - VERIFY (index 3)", () => {
  it("is 'active' for nli_evaluation", () => expect(getPhaseState("nli_evaluation", 3)).toBe("active"));
  it("is 'done' for computing_fscore", () => expect(getPhaseState("computing_fscore", 3)).toBe("done"));
  it("is 'pending' for crawling", () => expect(getPhaseState("crawling", 3)).toBe("pending"));
});

describe("getPhaseState - REFLECT (index 4)", () => {
  it("is 'active' for computing_fscore", () => expect(getPhaseState("computing_fscore", 4)).toBe("active"));
  it("is 'active' for generating_patches", () => expect(getPhaseState("generating_patches", 4)).toBe("active"));
  it("is 'done' for completed", () => expect(getPhaseState("completed", 4)).toBe("done"));
  it("is 'pending' for crawling", () => expect(getPhaseState("crawling", 4)).toBe("pending"));
});

describe("getPhaseState - STOP (index 5)", () => {
  it("is 'active' for completed", () => expect(getPhaseState("completed", 5)).toBe("active"));
  it("is 'pending' for generating_patches", () => expect(getPhaseState("generating_patches", 5)).toBe("pending"));
  it("is 'pending' for failed", () => expect(getPhaseState("failed", 5)).toBe("pending"));
});

describe("getPhaseState - out-of-bounds index", () => {
  it("returns pending for index -1", () => expect(getPhaseState("completed", -1)).toBe("pending"));
  it("returns pending for index 6", () => expect(getPhaseState("completed", 6)).toBe("pending"));
});

// --- getPhaseStateWithFallback - failed with known lastGoodStatus ---

describe("getPhaseStateWithFallback - failed scan", () => {
  it("marks OBSERVE as done and PLAN as error when lastGoodStatus=synthesizing_intents", () => {
    // synthesizing_intents is active in PLAN (index 1), so OBSERVE (0) must be done
    expect(getPhaseStateWithFallback("failed", "synthesizing_intents", 0)).toBe("done");
    expect(getPhaseStateWithFallback("failed", "synthesizing_intents", 1)).toBe("error");
    expect(getPhaseStateWithFallback("failed", "synthesizing_intents", 2)).toBe("pending");
  });

  it("marks phases 0-1 done and ACT as error when lastGoodStatus=hybrid_retrieval", () => {
    expect(getPhaseStateWithFallback("failed", "hybrid_retrieval", 0)).toBe("done");
    expect(getPhaseStateWithFallback("failed", "hybrid_retrieval", 1)).toBe("done");
    expect(getPhaseStateWithFallback("failed", "hybrid_retrieval", 2)).toBe("error");
    expect(getPhaseStateWithFallback("failed", "hybrid_retrieval", 3)).toBe("pending");
  });

  it("marks phases 0-2 done and VERIFY as error when lastGoodStatus=nli_evaluation", () => {
    expect(getPhaseStateWithFallback("failed", "nli_evaluation", 3)).toBe("error");
    expect(getPhaseStateWithFallback("failed", "nli_evaluation", 4)).toBe("pending");
  });

  it("defaults to OBSERVE error when lastGoodStatus=null", () => {
    expect(getPhaseStateWithFallback("failed", null, 0)).toBe("error");
    expect(getPhaseStateWithFallback("failed", null, 1)).toBe("pending");
  });

  it("delegates to getPhaseState when status is not failed", () => {
    expect(getPhaseStateWithFallback("completed", null, 0)).toBe(getPhaseState("completed", 0));
    expect(getPhaseStateWithFallback("crawling", "pending", 2)).toBe(getPhaseState("crawling", 2));
  });
});

// --- activePhaseIndex ---

describe("activePhaseIndex", () => {
  it("pending maps to index 0 (OBSERVE)", () => expect(activePhaseIndex("pending")).toBe(0));
  it("crawling maps to index 0 (OBSERVE)", () => expect(activePhaseIndex("crawling")).toBe(0));
  it("synthesizing_intents maps to index 1 (PLAN)", () => expect(activePhaseIndex("synthesizing_intents")).toBe(1));
  it("hybrid_retrieval maps to index 2 (ACT)", () => expect(activePhaseIndex("hybrid_retrieval")).toBe(2));
  it("nli_evaluation maps to index 3 (VERIFY)", () => expect(activePhaseIndex("nli_evaluation")).toBe(3));
  it("computing_fscore maps to index 4 (REFLECT)", () => expect(activePhaseIndex("computing_fscore")).toBe(4));
  it("completed maps to index 5 (STOP)", () => expect(activePhaseIndex("completed")).toBe(5));
  it("failed falls back to 0", () => expect(activePhaseIndex("failed")).toBe(0));
});
