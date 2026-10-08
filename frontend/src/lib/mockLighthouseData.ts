// Mock fixture mirroring spec section 4.4 verbatim
// Used for UI development and fallback when backend endpoint GET /api/v1/scans/{id}/lighthouse is unavailable.

import type { LighthouseResponse } from "@/types/lighthouse";

export const MOCK_LIGHTHOUSE_RESPONSE: LighthouseResponse = {
  scan_id: "scan_abc123",
  computed_at: "2026-10-07T22:00:00Z",
  engines: {
    chatgpt: {
      score: 92,
      tier: "good",
      criteria: {
        bot_access: {
          score: 100,
          detail: "GPTBot, OAI-SearchBot, ChatGPT-User: all allowed",
        },
        schema_coverage: {
          score: 85,
          detail: "Organization, FAQPage found. Missing: Product",
        },
        answerability: {
          score: 94,
          detail: "28/30 intents answered (SUPPORTED)",
        },
        structural_clarity: {
          score: 90,
          detail: "Clean h1 -> h2 -> h3 hierarchy",
        },
        consistency: {
          score: 100,
          detail: "Zero cross-page contradictions",
        },
      },
    },
    gemini: {
      score: 86,
      tier: "good",
      criteria: {
        bot_access: {
          score: 100,
          detail: "Google-Extended and Googlebot allowed",
        },
        schema_coverage: {
          score: 85,
          detail: "Nested JSON-LD entity graph detected",
        },
        answerability: {
          score: 90,
          detail: "High entailment ratio on core queries",
        },
        entity_strength: {
          score: 80,
          detail: "OpenGraph tags present, description length optimal",
        },
        freshness: {
          score: 75,
          detail: "dateModified signal present on recent pages",
        },
      },
    },
    perplexity: {
      score: 64,
      tier: "needs_improvement",
      criteria: {
        bot_access: {
          score: 0,
          detail: "PerplexityBot is blocked in robots.txt",
        },
        schema_coverage: {
          score: 80,
          detail: "Basic JSON-LD structured data detected",
        },
        chunk_quality: {
          score: 85,
          detail: "Concise DOM chunks with factual summaries",
        },
        anchor_citations: {
          score: 65,
          detail: "Missing section anchor IDs on pricing & features",
        },
        factual_density: {
          score: 90,
          detail: "High density of verifiable metrics and terms",
        },
      },
    },
    claude: {
      score: 78,
      tier: "good",
      criteria: {
        bot_access: {
          score: 100,
          detail: "ClaudeBot and Claude-SearchBot allowed",
        },
        schema_coverage: {
          score: 80,
          detail: "Valid Schema.org microdata verified",
        },
        answerability: {
          score: 88,
          detail: "Direct answers available for evaluation intents",
        },
        consistency: {
          score: 70,
          detail: "1 minor soft inconsistency detected in FAQ",
        },
        policy_docs: {
          score: 52,
          detail: "Privacy policy present, refund policy missing",
        },
      },
    },
  },
  crawler_governance: {
    ai_visibility_index: 88,
    scraping_risk: "low",
    bot_matrix: [
      { bot: "GPTBot", category: "training", status: "allowed" },
      {
        bot: "PerplexityBot",
        category: "search",
        status: "blocked",
        impact: "critical",
      },
      {
        bot: "Bytespider",
        category: "scraper",
        status: "blocked",
        impact: "positive",
      },
      { bot: "OAI-SearchBot", category: "search", status: "allowed" },
      { bot: "Claude-SearchBot", category: "search", status: "allowed" },
      { bot: "ClaudeBot", category: "training", status: "allowed" },
      { bot: "Google-Extended", category: "training", status: "allowed" },
      {
        bot: "CCBot",
        category: "scraper",
        status: "blocked",
        impact: "positive",
      },
    ],
    llms_txt_present: false,
  },
  audits: {
    opportunities: [
      {
        id: "unblock-perplexitybot",
        title: "Unblock PerplexityBot in robots.txt",
        score_lift: 18,
        engine: "perplexity",
        severity: "critical",
      },
      {
        id: "add-product-schema",
        title: "Add Product Schema.org JSON-LD to Pricing Page",
        score_lift: 14,
        engine: "chatgpt",
        severity: "high",
      },
      {
        id: "add-heading-anchors",
        title: "Add DOM anchor IDs to Key Section Headings",
        score_lift: 9,
        engine: "perplexity",
        severity: "medium",
      },
      {
        id: "generate-llms-txt",
        title: "Generate and publish /llms.txt manifest",
        score_lift: 6,
        engine: "all",
        severity: "low",
      },
    ],
    diagnostics: [
      {
        id: "heading-skip",
        title: "Heading hierarchy skips h2 level (h1 -> h3)",
        engines_affected: ["gemini", "chatgpt"],
      },
      {
        id: "missing-datemodified",
        title: "Missing dateModified freshness signal in Schema.org",
        engines_affected: ["gemini"],
      },
      {
        id: "soft-pricing-contradiction",
        title: "Soft inconsistency in FAQ pricing note vs tier matrix",
        engines_affected: ["claude"],
      },
    ],
    passed: [
      {
        id: "gptbot-allowed",
        title: "GPTBot explicitly allowed in robots.txt",
      },
      {
        id: "faqpage-schema",
        title: "Valid FAQPage Schema.org JSON-LD detected",
      },
      {
        id: "https-active",
        title: "Valid SSL / HTTPS transport enforced",
      },
      {
        id: "zero-security-contradictions",
        title: "Zero contradictions detected on security & compliance claims",
      },
      {
        id: "semantic-html5",
        title: "Semantic HTML5 landmarks (header, main, nav, section) verified",
      },
    ],
  },
};
