import type {
  IntentEvaluation,
  IntentCategory,
  EntailmentStatus,
  EvidenceReference,
  Contradiction,
  ContradictionSeverity,
} from "@/types/scan";

// Weight normalizer

/** Accepts weight as fraction (0.40) or percent (40) and returns percent. */
export function normalizeWeight(weight: unknown): number {
  const n = typeof weight === "number" ? weight : parseFloat(String(weight));
  if (!isFinite(n)) return 0;
  // If value is <= 1 treat it as a fraction, otherwise already a percent
  return n <= 1 ? Math.round(n * 100) : Math.round(n);
}

// Entailment status normalizer

const ENTAILMENT_MAP: Record<string, EntailmentStatus> = {
  supported: "SUPPORTED",
  SUPPORTED: "SUPPORTED",
  partially_supported: "PARTIALLY_SUPPORTED",
  PARTIALLY_SUPPORTED: "PARTIALLY_SUPPORTED",
  partial: "PARTIALLY_SUPPORTED",
  contradicted: "CONTRADICTED",
  CONTRADICTED: "CONTRADICTED",
  unknown: "UNKNOWN",
  UNKNOWN: "UNKNOWN",
};

function toEntailmentStatus(raw: unknown): EntailmentStatus {
  if (typeof raw === "string" && raw in ENTAILMENT_MAP) {
    return ENTAILMENT_MAP[raw] as EntailmentStatus;
  }
  return "UNKNOWN";
}

// Category normalizer

const VALID_CATEGORIES = new Set<IntentCategory>([
  "eligibility",
  "policy",
  "availability",
  "pricing",
  "accessibility",
  "commercial",
  "local",
  "transactional",
  "trust",
  "edge_cases",
]);

function toCategory(raw: unknown): IntentCategory {
  if (typeof raw === "string" && VALID_CATEGORIES.has(raw as IntentCategory)) {
    return raw as IntentCategory;
  }
  return "uncategorized";
}

// Severity normalizer

const SEVERITY_MAP: Record<string, ContradictionSeverity> = {
  hard_contradiction: "HARD_CONTRADICTION",
  HARD_CONTRADICTION: "HARD_CONTRADICTION",
  soft_inconsistency: "SOFT_INCONSISTENCY",
  SOFT_INCONSISTENCY: "SOFT_INCONSISTENCY",
};

function toSeverity(raw: unknown): ContradictionSeverity {
  if (typeof raw === "string" && raw in SEVERITY_MAP) {
    return SEVERITY_MAP[raw] as ContradictionSeverity;
  }
  return "SOFT_INCONSISTENCY";
}

// Intent normalizer - handles BOTH loose mock shape and strict real shape

let _intentCounter = 0;

/**
 * Normalizes a single raw intent object from either the mock or real backend shape.
 * Never throws. Returns null if the input is not an object.
 */
export function normalizeIntent(raw: unknown): IntentEvaluation | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;

  // Derive stable id
  const intent_id =
    typeof r["intent_id"] === "string" && r["intent_id"]
      ? r["intent_id"]
      : `intent_${++_intentCounter}`;

  const query =
    typeof r["query"] === "string" ? r["query"].trim() : "Unknown query";

  const status = toEntailmentStatus(r["status"]);
  const category = toCategory(r["category"]);
  const confidence =
    typeof r["confidence"] === "number"
      ? Math.min(1, Math.max(0, r["confidence"]))
      : 0;

  const reasoning =
    typeof r["reasoning"] === "string"
      ? r["reasoning"]
      : status === "SUPPORTED"
        ? "Claim is directly supported by retrieved evidence."
        : status === "CONTRADICTED"
          ? "A conflicting claim was detected in the crawled content."
          : "Insufficient evidence to determine entailment.";

  // Build evidence array - loose shape has "citation" (a DOM path string)
  let evidence: EvidenceReference[] = [];
  if (Array.isArray(r["evidence"])) {
    evidence = (r["evidence"] as unknown[])
      .map((e, i): EvidenceReference | null => {
        if (!e || typeof e !== "object") return null;
        const ev = e as Record<string, unknown>;
        const chunk_id =
          typeof ev["chunk_id"] === "string" ? ev["chunk_id"] : `chunk_${i}`;
        const dom_path =
          typeof ev["dom_path"] === "string" ? ev["dom_path"] : "";
        return {
          chunk_id,
          dom_path,
          url: typeof ev["url"] === "string" ? ev["url"] : undefined,
          rank: typeof ev["rank"] === "number" ? ev["rank"] : undefined,
          rrf_score:
            typeof ev["rrf_score"] === "number" ? ev["rrf_score"] : undefined,
          excerpt:
            typeof ev["excerpt"] === "string" ? ev["excerpt"] : undefined,
        };
      })
      .filter((e): e is EvidenceReference => e !== null);
  } else if (typeof r["citation"] === "string" && r["citation"]) {
    // Loose mock shape: single citation string -> one evidence entry
    evidence = [{ chunk_id: "mock_0", dom_path: r["citation"] as string }];
  }

  const difficulty = (() => {
    const d = r["difficulty"];
    if (d === "easy" || d === "medium" || d === "hard") return d;
    return undefined;
  })();

  return {
    intent_id,
    query,
    category,
    status,
    reasoning,
    evidence,
    confidence,
    difficulty,
  };
}

/** Normalizes an array of raw intents, skipping any that fail. */
export function normalizeIntents(raw: unknown[]): IntentEvaluation[] {
  return raw.map(normalizeIntent).filter((i): i is IntentEvaluation => i !== null);
}

// Contradiction normalizer - handles BOTH loose mock shape and strict real shape

let _contradictionCounter = 0;

/**
 * Normalizes a single raw contradiction from either the mock or real backend shape.
 * Never throws. Returns null if input is not an object.
 */
export function normalizeContradiction(raw: unknown): Contradiction | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;

  const contradiction_id =
    typeof r["contradiction_id"] === "string" && r["contradiction_id"]
      ? r["contradiction_id"]
      : `con_${++_contradictionCounter}`;

  // Strict shape has "entity"; loose mock shape doesn't - derive from claim text
  const entity =
    typeof r["entity"] === "string" && r["entity"]
      ? r["entity"]
      : "detected_conflict";

  // Build conflict text from strict "conflict" OR loose "rationale"
  const conflict =
    typeof r["conflict"] === "string" && r["conflict"]
      ? r["conflict"]
      : typeof r["rationale"] === "string" && r["rationale"]
        ? r["rationale"]
        : "Conflicting claims detected across crawled pages.";

  // Build values array: strict has "values[]", loose has "claim_a" + "claim_b"
  let values: unknown[];
  if (Array.isArray(r["values"]) && r["values"].length >= 2) {
    values = r["values"] as unknown[];
  } else {
    const a = typeof r["claim_a"] === "string" ? r["claim_a"] : null;
    const b = typeof r["claim_b"] === "string" ? r["claim_b"] : null;
    values = [a, b].filter(Boolean);
    if (values.length < 2) values = ["(value A)", "(value B)"];
  }

  const severity = toSeverity(r["severity"]);

  const source_urls = Array.isArray(r["source_urls"])
    ? (r["source_urls"] as unknown[]).filter(
      (u): u is string => typeof u === "string"
    )
    : [];

  const dom_paths = Array.isArray(r["dom_paths"])
    ? (r["dom_paths"] as unknown[]).filter(
      (p): p is string => typeof p === "string"
    )
    : [];

  return { contradiction_id, entity, conflict, values, severity, source_urls, dom_paths };
}

/** Normalizes an array of raw contradictions, skipping any that fail. */
export function normalizeContradictions(raw: unknown[]): Contradiction[] {
  return raw
    .map(normalizeContradiction)
    .filter((c): c is Contradiction => c !== null);
}