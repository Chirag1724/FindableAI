import { describe, it, expect } from "vitest";
import {
  normalizeIntent,
  normalizeIntents,
  normalizeContradiction,
  normalizeContradictions,
  normalizeWeight,
} from "@/lib/normalize";

// --- normalizeWeight ---

describe("normalizeWeight", () => {
  it("converts fraction 0.40 to 40", () => {
    expect(normalizeWeight(0.40)).toBe(40);
  });

  it("converts fraction 0.35 to 35", () => {
    expect(normalizeWeight(0.35)).toBe(35);
  });

  it("passes through whole percent 40", () => {
    expect(normalizeWeight(40)).toBe(40);
  });

  it("passes through whole percent 100", () => {
    expect(normalizeWeight(100)).toBe(100);
  });

  it("handles 0", () => {
    expect(normalizeWeight(0)).toBe(0);
  });

  it("handles 1 as a fraction (1 = 100%)", () => {
    expect(normalizeWeight(1)).toBe(100);
  });

  it("returns 0 for non-finite string", () => {
    expect(normalizeWeight("banana")).toBe(0);
  });

  it("returns 0 for null", () => {
    expect(normalizeWeight(null)).toBe(0);
  });

  it("returns 0 for undefined", () => {
    expect(normalizeWeight(undefined)).toBe(0);
  });
});

// --- normalizeIntent - legacy flat shape ---

const LOOSE_INTENT = {
  query: "Does Bistro 2026 offer vegan options?",
  category: "pricing",
  status: "supported",
  citation: "body > main > section#menu > p.item-vegan",
  confidence: 0.94,
};

const STRICT_INTENT = {
  intent_id: "int_abc123",
  query: "What are the opening hours on weekends?",
  category: "availability",
  status: "CONTRADICTED",
  reasoning: "Conflicting hours detected.",
  evidence: [
    { chunk_id: "chunk_1", dom_path: "body > footer > p.hours", url: "https://example.com", rank: 1, rrf_score: 0.87 },
  ],
  confidence: 0.88,
  difficulty: "hard",
};

describe("normalizeIntent - loose shape", () => {
  it("maps status 'supported' to SUPPORTED", () => {
    const r = normalizeIntent(LOOSE_INTENT);
    expect(r?.status).toBe("SUPPORTED");
  });

  it("converts citation string to a single evidence entry", () => {
    const r = normalizeIntent(LOOSE_INTENT);
    expect(r?.evidence).toHaveLength(1);
    expect(r?.evidence[0]?.dom_path).toBe("body > main > section#menu > p.item-vegan");
  });

  it("assigns a generated intent_id when missing", () => {
    const r = normalizeIntent(LOOSE_INTENT);
    expect(r?.intent_id).toMatch(/^intent_\d+$/);
  });

  it("clamps confidence to [0, 1]", () => {
    const r = normalizeIntent({ ...LOOSE_INTENT, confidence: 1.5 });
    expect(r?.confidence).toBe(1);
  });

  it("fills in reasoning when missing", () => {
    const r = normalizeIntent(LOOSE_INTENT);
    expect(typeof r?.reasoning).toBe("string");
    expect(r?.reasoning.length).toBeGreaterThan(0);
  });
});

describe("normalizeIntent - strict real shape", () => {
  it("uses the provided intent_id", () => {
    const r = normalizeIntent(STRICT_INTENT);
    expect(r?.intent_id).toBe("int_abc123");
  });

  it("maps status CONTRADICTED correctly", () => {
    const r = normalizeIntent(STRICT_INTENT);
    expect(r?.status).toBe("CONTRADICTED");
  });

  it("preserves evidence array", () => {
    const r = normalizeIntent(STRICT_INTENT);
    expect(r?.evidence).toHaveLength(1);
    expect(r?.evidence[0]?.chunk_id).toBe("chunk_1");
    expect(r?.evidence[0]?.rrf_score).toBe(0.87);
  });

  it("preserves difficulty", () => {
    const r = normalizeIntent(STRICT_INTENT);
    expect(r?.difficulty).toBe("hard");
  });

  it("maps unknown category to 'uncategorized'", () => {
    const r = normalizeIntent({ ...STRICT_INTENT, category: "something_new" });
    expect(r?.category).toBe("uncategorized");
  });
});

describe("normalizeIntent - malformed inputs", () => {
  it("returns null for null", () => {
    expect(normalizeIntent(null)).toBeNull();
  });

  it("returns null for a string", () => {
    expect(normalizeIntent("bad")).toBeNull();
  });

  it("returns null for a number", () => {
    expect(normalizeIntent(42)).toBeNull();
  });

  it("does not throw for an empty object", () => {
    expect(() => normalizeIntent({})).not.toThrow();
    const r = normalizeIntent({});
    expect(r?.query).toBe("Unknown query");
    expect(r?.status).toBe("UNKNOWN");
  });

  it("handles PARTIALLY_SUPPORTED alias 'partial'", () => {
    const r = normalizeIntent({ ...LOOSE_INTENT, status: "partial" });
    expect(r?.status).toBe("PARTIALLY_SUPPORTED");
  });

  it("defaults unknown status to UNKNOWN", () => {
    const r = normalizeIntent({ ...LOOSE_INTENT, status: "garbage" });
    expect(r?.status).toBe("UNKNOWN");
  });
});

describe("normalizeIntents", () => {
  it("skips null items in batch", () => {
    const result = normalizeIntents([LOOSE_INTENT, null, STRICT_INTENT] as unknown[]);
    expect(result).toHaveLength(2);
  });
});

// --- normalizeContradiction - legacy flat shape ---

const LOOSE_CONTRADICTION = {
  contradiction_id: "con_abc",
  claim_a: "Open daily until 10:00 PM (Home Page)",
  claim_b: "Open daily until 9:00 PM (About Page)",
  severity: "hard_contradiction",
  rationale: "Conflicting closing hours.",
};

const STRICT_CONTRADICTION = {
  contradiction_id: "con_xyz",
  entity: "opening_hours",
  conflict: "Landing page says 10 PM, About says 9 PM.",
  values: ["10:00 PM", "9:00 PM"],
  severity: "HARD_CONTRADICTION",
  source_urls: ["https://example.com/", "https://example.com/about"],
  dom_paths: ["body > .hours", "body > footer > p"],
};

describe("normalizeContradiction - loose shape", () => {
  it("maps severity 'hard_contradiction' to HARD_CONTRADICTION", () => {
    const r = normalizeContradiction(LOOSE_CONTRADICTION);
    expect(r?.severity).toBe("HARD_CONTRADICTION");
  });

  it("builds values from claim_a and claim_b when values array missing", () => {
    const r = normalizeContradiction(LOOSE_CONTRADICTION);
    expect(r?.values).toHaveLength(2);
    expect(r?.values[0]).toBe(LOOSE_CONTRADICTION.claim_a);
  });

  it("uses rationale as conflict text when conflict field missing", () => {
    const r = normalizeContradiction(LOOSE_CONTRADICTION);
    expect(r?.conflict).toBe(LOOSE_CONTRADICTION.rationale);
  });

  it("defaults entity to 'detected_conflict' when missing", () => {
    const r = normalizeContradiction(LOOSE_CONTRADICTION);
    expect(r?.entity).toBe("detected_conflict");
  });
});

describe("normalizeContradiction - strict real shape", () => {
  it("uses the entity field", () => {
    const r = normalizeContradiction(STRICT_CONTRADICTION);
    expect(r?.entity).toBe("opening_hours");
  });

  it("uses the conflict field", () => {
    const r = normalizeContradiction(STRICT_CONTRADICTION);
    expect(r?.conflict).toBe(STRICT_CONTRADICTION.conflict);
  });

  it("preserves values array", () => {
    const r = normalizeContradiction(STRICT_CONTRADICTION);
    expect(r?.values).toEqual(["10:00 PM", "9:00 PM"]);
  });

  it("preserves source_urls", () => {
    const r = normalizeContradiction(STRICT_CONTRADICTION);
    expect(r?.source_urls).toHaveLength(2);
  });

  it("preserves dom_paths", () => {
    const r = normalizeContradiction(STRICT_CONTRADICTION);
    expect(r?.dom_paths).toHaveLength(2);
  });

  it("maps SOFT_INCONSISTENCY", () => {
    const r = normalizeContradiction({ ...STRICT_CONTRADICTION, severity: "SOFT_INCONSISTENCY" });
    expect(r?.severity).toBe("SOFT_INCONSISTENCY");
  });
});

describe("normalizeContradiction - malformed inputs", () => {
  it("returns null for null", () => {
    expect(normalizeContradiction(null)).toBeNull();
  });

  it("does not throw for an empty object", () => {
    expect(() => normalizeContradiction({})).not.toThrow();
  });

  it("defaults severity to SOFT_INCONSISTENCY for unknown string", () => {
    const r = normalizeContradiction({ ...STRICT_CONTRADICTION, severity: "weird" });
    expect(r?.severity).toBe("SOFT_INCONSISTENCY");
  });
});

describe("normalizeContradictions", () => {
  it("skips null items", () => {
    const result = normalizeContradictions([LOOSE_CONTRADICTION, null] as unknown[]);
    expect(result).toHaveLength(1);
  });
});
