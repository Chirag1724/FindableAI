"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowRight,
  ArrowUpRight,
  Plus,
  Menu,
  X,
  Zap,
  FileCode2,
  Search,
  Bot,
  ShieldCheck,
  Check,
  Code2,
  Shield,
  Scale,
  GitPullRequest,
} from "lucide-react";
import { getHealth } from "@/lib/api";
import type { FScoreBreakdown } from "@/types/scan";
import dynamic from "next/dynamic";
import { GaugeSkeleton } from "@/components/Skeletons";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

const ScoreGauge = dynamic(
  () => import("@/components/ScoreGauge").then((mod) => mod.ScoreGauge),
  { ssr: false, loading: () => <GaugeSkeleton /> }
);

const LighthouseGauge = dynamic(
  () => import("@/components/LighthouseGauge").then((mod) => mod.LighthouseGauge),
  { ssr: false, loading: () => <div className="h-64 rounded-xl bg-surface animate-pulse" /> }
);

const CrawlInspector = dynamic(
  () => import("@/components/CrawlInspector").then((mod) => mod.CrawlInspector),
  { ssr: false, loading: () => <div className="h-72 rounded-xl bg-surface animate-pulse" /> }
);

const IntentSimulator = dynamic(
  () => import("@/components/IntentSimulator").then((mod) => mod.IntentSimulator),
  { ssr: false, loading: () => <div className="h-72 rounded-xl bg-surface animate-pulse" /> }
);

const ContradictionInspector = dynamic(
  () => import("@/components/ContradictionInspector").then((mod) => mod.ContradictionInspector),
  { ssr: false, loading: () => <div className="h-72 rounded-xl bg-surface animate-pulse" /> }
);

const ArchitecturePillars = dynamic(
  () => import("@/components/ArchitecturePillars").then((mod) => mod.ArchitecturePillars),
  { ssr: false, loading: () => <div className="h-48 rounded-xl bg-surface animate-pulse" /> }
);

const DOCS_URL = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "")}/docs`
  : "/docs";

const SAMPLE_FSCORE: FScoreBreakdown = {
  overall_score: 74.2,
  grade: "B",
  coverage: {
    name: "Query Intent Coverage",
    weight: 0.40,
    score: 79.0,
    details: "Answers 11 of 14 simulated high-intent queries.",
    strengths: ["Clear pricing and specs", "Detailed architecture docs"],
    gaps: ["Missing security compliance microdata"],
  },
  contradiction_penalty: {
    name: "Contradiction Penalty",
    weight: 0.30,
    score: 8.0,
    details: "One conflict detected between homepage and docs.",
    strengths: ["Consistent product positioning across pages"],
    gaps: ["Pricing table contradicts FAQ terms"],
  },
  structural_clarity: {
    name: "DOM & Schema Structure",
    weight: 0.20,
    score: 82.0,
    details: "Good heading hierarchy, missing JSON-LD.",
    strengths: ["Semantic HTML5 elements"],
    gaps: ["No Schema.org microdata"],
  },
  entailment: {
    name: "Extractability & Accessibility",
    weight: 0.10,
    score: 72.5,
    details: "Machine accessibility of core business metadata.",
    strengths: ["Specific benchmark numbers"],
    gaps: ["Vague SLA terms"],
  },
};

const SAMPLE_LIGHTHOUSE_CRITERIA = {
  chatgpt: {
    text_extractability: { score: 96, detail: "Semantic text density verified" },
    schema_markup: { score: 92, detail: "JSON-LD SoftwareApplication active" },
    crawler_governance: { score: 100, detail: "OAI-SearchBot allowed in robots.txt" },
  },
  gemini: {
    google_extended: { score: 94, detail: "Google-Extended indexing allowed" },
    semantic_dom: { score: 86, detail: "Clean heading and article hierarchies" },
    render_speed: { score: 78, detail: "Hydration completed under 1.2s" },
  },
  perplexity: {
    citation_anchoring: { score: 62, detail: "Ambiguous claim selectors in pricing" },
    source_attribution: { score: 68, detail: "Missing factual microdata tags" },
    per_claim_verify: { score: 62, detail: "Unreferenced product specifications" },
  },
  claude: {
    fact_consistency: { score: 78, detail: "Contradiction penalty on pricing terms" },
    claude_bot_access: { score: 85, detail: "ClaudeBot user-agent compliant" },
    context_efficiency: { score: 71, detail: "Excess boilerplate wrapper markup" },
  },
};

const FAQS = [
  {
    question: "How does FindableAI differ from traditional SEO tools?",
    answer:
      "Traditional SEO tools optimize for keyword density, backlinks, and search crawlers. Modern searchers rely on AI answer engines. FindableAI audits machine discoverability: whether an LLM can retrieve, verify, and cite your factual claims without hallucinating.",
    defaultOpen: true,
  },
  {
    question: "What exactly is the Findability F-Score?",
    answer:
      "The F-Score is a deterministic 0 to 100 metric evaluated across four mathematically grounded pillars: Query Intent Coverage (40%), Fact Consistency / Contradiction Penalty (30%), DOM & Schema Structure (20%), and Machine Extractability & Accessibility (10%). It pinpoints exactly where search engines lose confidence in your site.",
  },
  {
    question: "How do autonomous GitHub Pull Requests work?",
    answer:
      "When FindableAI identifies ungrounded queries or structural ambiguities, it traces the exact CSS selector path in your DOM. It then writes unified diffs with content patches and Schema.org JSON-LD microdata, proposing a pull request with these fixes for your team to review and merge.",
  },
  {
    question: "Can I run audits on local or staging URLs?",
    answer:
      "For live public URLs, audits execute immediately. For local or private staging environments, you can run our CLI crawler or provide a private GitHub repository URL to audit source files and templates directly.",
  },
  {
    question: "Do I need to install an SDK or grant write access to production?",
    answer:
      "No. Discoverability scans run non-invasively using headless browsers crawling your public URLs. For automatic code fixes, we only need repository write permissions for the designated remediation branch you authorize.",
  },
  {
    question: "How does cross-page contradiction penalty work?",
    answer:
      "Our Natural Language Inference (NLI) pipeline pairs claims across your pages to detect factual contradictions. Discrepancies between pricing, specs, and docs trigger deterministic deductions from your Consistency pillar score.",
  },
];


function HealthIndicator() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    getHealth(ac.signal)
      .then(() => setOnline(true))
      .catch(() => setOnline(false));
    return () => ac.abort();
  }, []);

  if (online === null) return null;

  return (
    <div className="flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-full bg-surface-secondary shadow-border text-xs shrink-0">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          online ? "bg-emerald-500 animate-pulse" : "bg-rose-500"
        }`}
        aria-hidden="true"
      />
      <span className="text-[10px] font-mono tracking-wider text-text-muted">
        API {online ? "ONLINE" : "OFFLINE"}
      </span>
    </div>
  );
}

export default function HomePage() {
  const [headerScrolled, setHeaderScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const heroRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onScroll = () => setHeaderScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      // 1. Hero Reveal Stagger
      if (heroRef.current) {
        gsap.from("[data-hero-reveal]", {
          y: 20,
          opacity: 0,
          duration: 0.5,
          stagger: 0.08,
          ease: EASING.entrance,
        });
      }

      // 2. ScrollTrigger Section Fade-up Reveals
      const sections = gsap.utils.toArray<HTMLElement>("[data-reveal-section]");
      sections.forEach((sec) => {
        gsap.from(sec, {
          scrollTrigger: {
            trigger: sec,
            start: "top 88%",
            toggleActions: "play none none none",
          },
          y: 28,
          opacity: 0,
          duration: 0.65,
          ease: EASING.entrance,
        });
      });
    });

    return () => ctx.revert();
  }, []);

  return (
    <div className="min-h-screen bg-background text-text-primary font-sans relative overflow-x-hidden">
      {/* Fixed Top Nav */}
      <header
        className={`fixed top-0 left-0 right-0 z-50 w-full transition-all duration-200 ${
          headerScrolled || mobileMenuOpen
            ? "glass border-b border-white/[0.08] py-3 sm:py-3.5"
            : "bg-background/80 backdrop-blur-md border-b border-transparent py-3.5 sm:py-5"
        }`}
      >
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2 sm:gap-3 group">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={36}
                height={36}
                className="h-7 w-7 sm:h-8 sm:w-8 rounded-lg object-contain transition-transform duration-150 group-hover:scale-105"
                priority
              />
              <div className="flex items-baseline gap-1.5">
                <span className="text-base sm:text-lg tracking-tight text-text-primary font-semibold">
                  FindableAI
                </span>
                <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase hidden sm:inline">
                  MDO
                </span>
              </div>
            </Link>

            {/* Navigation links (md+) */}
            <nav className="hidden md:flex items-center gap-8 text-xs font-medium tracking-wide">
              <Link
                href="/"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Home
              </Link>
              <a
                href="#crawl"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Extraction
              </a>
              <a
                href="#intent"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Intent
              </a>
              <a
                href="#contradictions"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Contradictions
              </a>
              <a
                href="#fscore"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                F-Score
              </a>
              <a
                href="#remediation"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Fixes
              </a>
              <a
                href="#faq"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                FAQ
              </a>
            </nav>

            {/* Actions & Mobile Menu Toggle */}
            <div className="flex items-center gap-2 sm:gap-3.5">
              <HealthIndicator />
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-white text-black hover:bg-neutral-200 transition-colors duration-150 active:scale-95"
              >
                <span>Start audit</span>
                <ArrowRight className="h-3 w-3" />
              </Link>

              {/* Hamburger Button (Mobile < md) */}
              <button
                type="button"
                onClick={() => setMobileMenuOpen((o) => !o)}
                aria-label="Toggle navigation menu"
                aria-expanded={mobileMenuOpen}
                className="md:hidden flex items-center justify-center h-8 w-8 rounded-lg shadow-border text-text-primary bg-surface-secondary hover:bg-surface transition-colors duration-150 active:scale-95"
              >
                {mobileMenuOpen ? (
                  <X className="h-4 w-4" />
                ) : (
                  <Menu className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {/* Mobile Dropdown Menu */}
          {mobileMenuOpen && (
            <div className="md:hidden border-t border-white/[0.08] bg-surface/95 backdrop-blur-xl px-2 pt-3 pb-5 space-y-3 mt-3 animate-in fade-in slide-in-from-top-2 duration-150">
              <nav className="flex flex-col space-y-1 text-xs">
                <Link
                  href="/"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2.5 rounded-lg text-text-primary hover:bg-white/[0.04] transition-colors duration-150 font-medium"
                >
                  Home
                </Link>
                <a
                  href="#crawl"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  DOM Extraction
                </a>
                <a
                  href="#intent"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  Intent Simulation
                </a>
                <a
                  href="#contradictions"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  Contradiction Detection
                </a>
                <a
                  href="#fscore"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  F-Score Metric
                </a>
                <a
                  href="#remediation"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  Automated Fixes
                </a>
                <a
                  href="#faq"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  FAQ
                </a>
              </nav>

              <div className="pt-2 border-t border-white/[0.08]">
                <Link
                  href="/audit"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-center gap-2 w-full py-3 rounded-lg bg-white text-black font-semibold text-xs tracking-wider uppercase active:scale-95"
                >
                  <span>Start Machine Audit</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 pt-16 sm:pt-20">
        {/* Section 1: Hero */}
        <section
          ref={heroRef}
          id="hero"
          className="relative min-h-[calc(100vh-4.5rem)] min-h-[calc(100dvh-4.5rem)] flex items-center justify-center py-6 sm:py-8 lg:py-10 w-full"
        >
          {/* Subtle Ambient Engineering Grid (Quiet, refined, non-distracting) */}
          <div className="pointer-events-none absolute -inset-x-4 sm:inset-x-0 inset-y-0 -top-20 flex items-center justify-center overflow-hidden">
            <div className="hero-grid-bg absolute inset-0 opacity-35" />
            <div className="hero-glow absolute inset-0 opacity-40" />
          </div>

          <div className="relative z-10 max-w-4xl mx-auto text-center flex flex-col items-center justify-center w-full">
            {/* Engineering Protocol / Version Link (Replaces generic AI capsule) */}
            <Link
              href="/audit"
              data-hero-reveal
              className="group inline-flex items-center gap-2.5 px-3 py-1 rounded-full bg-surface-secondary/70 hover:bg-surface-secondary border border-white/[0.1] text-xs text-text-muted hover:text-white transition-all duration-150 mb-5 sm:mb-6 shadow-sm active:scale-95"
            >
              <span className="font-mono text-[11px] text-emerald-400 font-medium">v1.4</span>
              <span className="h-3 w-px bg-white/10" aria-hidden="true" />
              <span className="text-text-primary text-xs font-medium">Deterministic DOM AST & Citation Audits</span>
              <ArrowRight className="h-3 w-3 text-text-muted transition-transform duration-150 group-hover:translate-x-0.5" />
            </Link>

            {/* Headline */}
            <h1
              data-hero-reveal
              className="text-3xl sm:text-5xl lg:text-[3.5rem] font-semibold tracking-tight text-white mb-4 sm:mb-5 leading-[1.12] max-w-3xl"
            >
              Discoverability, engineered with precision.
            </h1>

            {/* Subhead */}
            <p
              data-hero-reveal
              className="text-sm sm:text-base lg:text-lg text-text-muted leading-relaxed mb-6 sm:mb-8 max-w-2xl font-normal"
            >
              Audit citation rates across ChatGPT, Perplexity, Gemini, and Claude. Detect cross-page factual contradictions, and dispatch autonomous AST code fixes.
            </p>

            {/* Actions (Clean Natural Case & Subtle Borders) */}
            <div data-hero-reveal className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 mb-8 sm:mb-10">
              <Link
                href="/audit"
                className="group inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-white text-black font-medium text-xs tracking-wide transition-all duration-150 hover:bg-neutral-200 active:scale-95 shadow-sm"
              >
                <span>Start machine audit</span>
                <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-0.5" />
              </Link>

              <a
                href="#crawl"
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-surface-secondary/70 hover:bg-surface-secondary border border-white/[0.1] text-text-primary transition-all duration-150 text-xs font-medium active:scale-95"
              >
                <span>Explore architecture ↓</span>
              </a>
            </div>

            {/* Architectural Guarantees Spec Bar (Structured Engineering Cards) */}
            <div
              data-hero-reveal
              className="w-full max-w-4xl mx-auto pt-6 border-t border-white/[0.08]"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 sm:gap-3 text-left">
                <div className="p-3 rounded-lg bg-surface-secondary/40 border border-white/[0.06] backdrop-blur-sm hover:border-white/10 transition-colors">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-text-muted mb-1 flex items-center justify-between">
                    <span>Score Engine</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  </div>
                  <div className="text-xs font-medium text-white">Deterministic F-Score</div>
                  <div className="text-[10px] text-text-muted mt-0.5">40/30/20/10 formula</div>
                </div>

                <div className="p-3 rounded-lg bg-surface-secondary/40 border border-white/[0.06] backdrop-blur-sm hover:border-white/10 transition-colors">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-text-muted mb-1 flex items-center justify-between">
                    <span>Evidence Anchor</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                  </div>
                  <div className="text-xs font-medium text-white">DOM Selector Pinning</div>
                  <div className="text-[10px] text-text-muted mt-0.5">CSS tree attribution</div>
                </div>

                <div className="p-3 rounded-lg bg-surface-secondary/40 border border-white/[0.06] backdrop-blur-sm hover:border-white/10 transition-colors">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-text-muted mb-1 flex items-center justify-between">
                    <span>Intent Simulation</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                  </div>
                  <div className="text-xs font-medium text-white">3 Buyer Personas</div>
                  <div className="text-[10px] text-text-muted mt-0.5">CTO, Dev, Procurement</div>
                </div>

                <div className="p-3 rounded-lg bg-surface-secondary/40 border border-white/[0.06] backdrop-blur-sm hover:border-white/10 transition-colors">
                  <div className="text-[10px] font-mono uppercase tracking-wider text-text-muted mb-1 flex items-center justify-between">
                    <span>Crawler Safety</span>
                    <span className="h-1.5 w-1.5 rounded-full bg-violet-400" />
                  </div>
                  <div className="text-xs font-medium text-white">SSRF-Hardened</div>
                  <div className="text-[10px] text-text-muted mt-0.5">Zero write permissions</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Section 2: Feature 1 - Crawl & DOM Extraction */}
        <section id="crawl" data-reveal-section className="mb-8 sm:mb-10 lg:mb-12 scroll-mt-20 pt-1 max-w-7xl mx-auto w-full">
          {/* Symmetrical Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-2.5 mb-3 sm:mb-4 pb-3 border-b border-white/[0.08]">
            <div className="max-w-2xl">
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                See what AI engines see.
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1 leading-relaxed">
                Headless crawlers extract semantic trees while preserving precise CSS selector paths for code attribution.
              </p>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <div className="hidden sm:flex items-center gap-2 rounded-lg bg-surface-secondary px-3 py-1.5 shadow-border text-xs font-mono text-text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-white font-medium">Headless Chromium</span>
                <span className="text-text-muted">· DOM Tree Extraction</span>
              </div>
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-secondary shadow-border text-xs font-medium text-text-primary hover:text-white transition-colors duration-150"
              >
                <span>Inspect Target</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Focused UI Artifact: Live DOM Extraction & Chunking Inspector */}
          <div className="w-full">
            <CrawlInspector />
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-3 sm:mt-4 px-4">
            Every text claim and structural node remains anchored to an exact CSS selector in your source templates.
          </p>
        </section>

        {/* Section 3: Feature 2 - Synthetic Intent Simulation */}
        <section id="intent" data-reveal-section className="mb-8 sm:mb-10 lg:mb-12 scroll-mt-20 pt-1 max-w-7xl mx-auto w-full">
          {/* Symmetrical Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-2.5 mb-3 sm:mb-4 pb-3 border-b border-white/[0.08]">
            <div className="max-w-2xl">
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                Questions buyers actually ask.
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1 leading-relaxed">
                Simulate multi-persona buyer queries across technical, security, and pricing search vectors.
              </p>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <div className="hidden sm:flex items-center gap-2 rounded-lg bg-surface-secondary px-3 py-1.5 shadow-border text-xs font-mono text-text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-white font-medium">Synthetic Intent Engine</span>
                <span className="text-text-muted">· 30 Multi-Persona Vectors</span>
              </div>
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-secondary shadow-border text-xs font-medium text-text-primary hover:text-white transition-colors duration-150"
              >
                <span>Simulate Queries</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Focused UI Artifact: Live Synthetic Buyer Intent Simulator */}
          <div className="w-full">
            <IntentSimulator />
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-3 sm:mt-4 px-4">
            Evaluates 30 synthetic queries across CTO, developer, and procurement buyer personas to locate answer blindspots.
          </p>
        </section>

        {/* Section 4: Architecture Pillars (Visual 3-Card Grid) */}
        <ArchitecturePillars />

        {/* Section 5: Feature 3 - Contradiction Detection */}
        <section id="contradictions" data-reveal-section className="mb-10 sm:mb-12 lg:mb-16 scroll-mt-20 pt-1 max-w-7xl mx-auto w-full">
          {/* Symmetrical Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3 mb-4 sm:mb-6 pb-4 border-b border-white/[0.08]">
            <div className="max-w-2xl">
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                Catch cross-page conflicts.
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1 leading-relaxed">
                Natural language inference judges cross-reference claims between product pages, documentation, and pricing terms.
              </p>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <div className="hidden sm:flex items-center gap-2 rounded-lg bg-surface-secondary px-3 py-1.5 shadow-border text-xs font-mono text-text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500 animate-pulse" />
                <span className="text-white font-medium">NLI Entailment</span>
                <span className="text-text-muted">· Contradiction Detection</span>
              </div>
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-secondary shadow-border text-xs font-medium text-text-primary hover:text-white transition-colors duration-150"
              >
                <span>Run Inconsistency Audit</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Focused UI Artifact: Live NLI Cross-Page Contradiction Inspector */}
          <div className="w-full">
            <ContradictionInspector />
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Identifies conflicting factual claims across your domain before answer engines cite inconsistent data.
          </p>
        </section>

        {/* Section 6: Feature 4 - Deterministic F-Score */}
        <section id="fscore" data-reveal-section className="mb-10 sm:mb-12 lg:mb-16 scroll-mt-20 pt-1 max-w-7xl mx-auto w-full">
          {/* Symmetrical Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3 mb-4 sm:mb-6 pb-4 border-b border-white/[0.08]">
            <div className="max-w-2xl">
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                One score, four pillars.
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1 leading-relaxed">
                A single 0 to 100 benchmark balancing query coverage, evidence consistency, DOM structure, and accessibility.
              </p>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <div className="hidden sm:flex items-center gap-2 rounded-lg bg-surface-secondary px-3 py-1.5 shadow-border text-xs font-mono text-text-muted">
                <span className="text-emerald-400 font-semibold">F</span>
                <span>=</span>
                <span>0.40 Ans + 0.30 Con + 0.20 Str + 0.10 Acc</span>
              </div>
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface-secondary shadow-border text-xs font-medium text-text-primary hover:text-white transition-colors duration-150"
              >
                <span>Evaluate Score</span>
                <ArrowRight size={13} aria-hidden="true" />
              </Link>
            </div>
          </div>

          {/* Focused UI Artifact: 3-Card Bento + 4-Column Diagnostic Grid */}
          <div className="w-full">
            <ScoreGauge fScore={SAMPLE_FSCORE} />
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Calculated deterministically using the canonical formula: 40% Coverage, 30% Consistency, 20% Structure, and 10% Extractability.
          </p>
        </section>

        {/* Section 7: Feature 5 - AI Lighthouse Engine */}
        <section id="lighthouse" data-reveal-section className="mb-10 sm:mb-12 lg:mb-16 scroll-mt-20 pt-1 max-w-7xl mx-auto w-full">
          {/* Symmetrical Top Header */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3 mb-4 sm:mb-6 pb-4 border-b border-white/[0.08]">
            <div className="max-w-2xl">
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                See how each AI engine reads your site.
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1 leading-relaxed">
                Dedicated readiness benchmarks tailored to the distinct indexing priorities of ChatGPT, Gemini, Perplexity, and Claude.
              </p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <Link
                href="/audit"
                className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-white text-black font-sans font-medium text-xs hover:bg-neutral-200 transition-colors shadow-sm active:scale-95"
              >
                <span>Run engine readiness test</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>

          {/* Full-Width 4-Engine Lighthouse Console */}
          <div className="rounded-2xl bg-surface/80 border border-white/[0.08] backdrop-blur-md shadow-2xl overflow-hidden text-left">
            {/* Console Top Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 px-4 sm:px-5 py-2.5 border-b border-white/[0.08] bg-surface-secondary/50 font-mono text-xs">
              <div className="flex items-center flex-wrap gap-2.5">
                <span className="font-semibold text-white tracking-wide flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  AI LIGHTHOUSE ENGINE BENCHMARKS
                </span>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white/[0.04] border border-white/[0.08] text-[10px] text-text-muted">
                  Target: <span className="text-white font-mono">example.com</span>
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/[0.04] text-text-muted border border-white/[0.08]">
                  4 Engines Evaluated
                </span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-text-muted font-mono">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                <span>Deterministic DOM AST · 0 LLM Tokens · 142ms</span>
              </div>
            </div>

            {/* 4 Engine Gauges in a Full-Width Row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 p-3 sm:p-4 bg-surface/30">
              <LighthouseGauge
                score={92}
                label="ChatGPT"
                engineKey="chatgpt"
                icon={Bot}
                accentColorClass="text-emerald-400"
                criteria={SAMPLE_LIGHTHOUSE_CRITERIA.chatgpt}
              />
              <LighthouseGauge
                score={86}
                label="Gemini"
                engineKey="gemini"
                icon={FileCode2}
                accentColorClass="text-sky-400"
                criteria={SAMPLE_LIGHTHOUSE_CRITERIA.gemini}
              />
              <LighthouseGauge
                score={64}
                label="Perplexity"
                engineKey="perplexity"
                icon={Search}
                accentColorClass="text-amber-400"
                criteria={SAMPLE_LIGHTHOUSE_CRITERIA.perplexity}
              />
              <LighthouseGauge
                score={78}
                label="Claude"
                engineKey="claude"
                icon={ShieldCheck}
                accentColorClass="text-violet-400"
                criteria={SAMPLE_LIGHTHOUSE_CRITERIA.claude}
              />
            </div>

            {/* Diagnostic Summary Telemetry */}
            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/[0.08] border-t border-white/[0.08] bg-surface-secondary/20 text-xs font-mono">
              <div className="py-2.5 px-4 sm:px-5 flex items-center gap-2.5">
                <div className="h-6 w-6 rounded-md bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold text-xs shrink-0">
                  80
                </div>
                <div>
                  <div className="font-sans font-medium text-white text-xs leading-tight">Mean AI Discoverability</div>
                  <div className="text-[10px] text-text-muted">Weighted composite readiness score</div>
                </div>
              </div>
              <div className="py-2.5 px-4 sm:px-5 flex items-center gap-2.5">
                <div className="h-6 w-6 rounded-md bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 font-bold text-xs shrink-0">
                  !
                </div>
                <div>
                  <div className="font-sans font-medium text-amber-300 text-xs leading-tight">Citation Anchoring Gap</div>
                  <div className="text-[10px] text-text-muted">Perplexity confidence constrained by unreferenced claims</div>
                </div>
              </div>
              <div className="py-2.5 px-4 sm:px-5 flex items-center gap-2.5">
                <div className="h-6 w-6 rounded-md bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400 font-bold text-xs shrink-0">
                  0
                </div>
                <div>
                  <div className="font-sans font-medium text-white text-xs leading-tight">Zero-Token Evaluation</div>
                  <div className="text-[10px] text-text-muted">100% deterministic AST &amp; robots.txt parsing</div>
                </div>
              </div>
            </div>
          </div>

          {/* Single-sentence caption */}
          <p className="text-center text-xs font-medium text-text-muted mt-4 px-4">
            Zero LLM calls, 100% deterministic, and instant — scores are computed directly from DOM AST parsing, robots.txt crawler governance, and verified evidence ratios.
          </p>
        </section>

        {/* Section 8: Feature 6 - Autonomous Remediation (Full-Width Split Layout) */}
        <section id="remediation" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-7xl mx-auto w-full">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center">
            {/* Left Column: Narrative & Technical Pipeline (5 cols) */}
            <div className="lg:col-span-5 text-left space-y-6">
              <div>
                <div className="inline-flex items-center gap-2 text-xs font-mono text-emerald-400 mb-3">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  <span className="uppercase tracking-wider">Autonomous Remediation Engine</span>
                </div>
                <h2 className="text-3xl sm:text-4xl text-white font-semibold tracking-tight mb-3">
                  From gap to pull request.
                </h2>
                <p className="text-xs sm:text-sm text-text-muted leading-relaxed">
                  When answer engines fail to retrieve or ground claims on your site, FindableAI isolates the exact AST node and drafts ready-to-merge patches directly to your repository.
                </p>
              </div>

              {/* Technical 3-Stage Pipeline Cards */}
              <div className="space-y-3 font-mono text-xs">
                <div className="p-3.5 rounded-xl bg-surface-secondary/40 border border-white/[0.07] backdrop-blur-sm">
                  <div className="flex items-center gap-2 text-white font-medium mb-1">
                    <span className="h-4 w-4 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-semibold">1</span>
                    <span className="font-sans font-medium text-xs text-white">DOM AST Isolation</span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-relaxed font-sans">
                    Traces missing JSON-LD schema or conflicting semantic tags to the exact CSS selector path in your markup.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-surface-secondary/40 border border-white/[0.07] backdrop-blur-sm">
                  <div className="flex items-center gap-2 text-white font-medium mb-1">
                    <span className="h-4 w-4 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center text-[10px] font-semibold">2</span>
                    <span className="font-sans font-medium text-xs text-white">Framework-Native Patching</span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-relaxed font-sans">
                    Synthesizes unified diffs tailored to Next.js metadata, Astro layouts, Nuxt, or static HTML templates.
                  </p>
                </div>

                <div className="p-3.5 rounded-xl bg-surface-secondary/40 border border-white/[0.07] backdrop-blur-sm">
                  <div className="flex items-center gap-2 text-white font-medium mb-1">
                    <span className="h-4 w-4 rounded-full bg-purple-500/20 text-purple-400 flex items-center justify-center text-[10px] font-semibold">3</span>
                    <span className="font-sans font-medium text-xs text-white">Non-Destructive PR Dispatch</span>
                  </div>
                  <p className="text-[11px] text-text-muted leading-relaxed font-sans">
                    Opens isolated pull requests on a dedicated review branch without touching main or production pipelines.
                  </p>
                </div>
              </div>

              <div className="pt-2">
                <Link
                  href="/audit"
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white text-black font-medium text-xs hover:bg-neutral-200 transition-colors shadow-sm active:scale-95"
                >
                  <span>Test remediation on your repository</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>

            {/* Right Column: Realistic GitHub Pull Request Diff Console (7 cols) */}
            <div className="lg:col-span-7 w-full">
              <div className="rounded-2xl bg-surface border border-white/[0.1] shadow-2xl overflow-hidden text-left">
                {/* PR Header Bar */}
                <div className="p-4 sm:p-5 border-b border-white/[0.08] bg-surface-secondary/50 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-xs font-mono font-medium">
                        <GitPullRequest className="h-3.5 w-3.5" />
                        <span>Open</span>
                      </span>
                      <span className="font-mono text-xs text-text-muted">#42</span>
                      <span className="text-white text-xs sm:text-sm font-semibold tracking-tight">
                        fix(schema): inject SoftwareApplication JSON-LD microdata
                      </span>
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/20">
                      <Check className="h-3 w-3" />
                      <span>AST Validated</span>
                    </span>
                  </div>

                  {/* Branch & Commit Meta */}
                  <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-text-muted">
                    <span className="text-white">findableai-bot</span>
                    <span>wants to merge 1 commit into</span>
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-white">main</span>
                    <span>from</span>
                    <span className="px-1.5 py-0.5 rounded bg-white/[0.06] text-white">findableai/patch-schema-metadata</span>
                  </div>
                </div>

                {/* File Diff Header */}
                <div className="flex items-center justify-between px-4 sm:px-5 py-2.5 bg-surface-secondary/30 border-b border-white/[0.08] text-xs font-mono text-text-muted">
                  <div className="flex items-center gap-2 text-white">
                    <FileCode2 className="h-3.5 w-3.5 text-text-muted" />
                    <span>src/app/layout.tsx</span>
                  </div>
                  <div className="flex items-center gap-3 text-[11px]">
                    <span className="text-emerald-400 font-semibold">+6 lines</span>
                    <span className="text-rose-400 font-semibold">-0 lines</span>
                  </div>
                </div>

                {/* Diff Viewer Body with Line Numbers */}
                <div className="bg-black/80 font-mono text-xs p-4 sm:p-5 overflow-x-auto leading-relaxed custom-scrollbar text-text-muted">
                  <div className="text-sky-400/80 mb-2 text-[11px]">@@ -14,6 +14,12 @@ export default function RootLayout</div>
                  <div className="space-y-0.5 text-[11px] sm:text-xs">
                    <div className="flex gap-4 opacity-50">
                      <span className="w-6 text-right select-none text-text-muted/60">14</span>
                      <span>&nbsp;&nbsp;&lt;head&gt;</span>
                    </div>
                    <div className="flex gap-4 opacity-50">
                      <span className="w-6 text-right select-none text-text-muted/60">15</span>
                      <span>&nbsp;&nbsp;&nbsp;&nbsp;&lt;title&gt;FindableAI Platform&lt;/title&gt;</span>
                    </div>
                    <div className="flex gap-4 bg-emerald-950/40 text-emerald-300 py-0.5 -mx-4 px-4 border-l-2 border-emerald-400">
                      <span className="w-6 text-right select-none text-emerald-500/70">16</span>
                      <span>+&nbsp;&nbsp;&nbsp;&lt;script type=&quot;application/ld+json&quot;&gt;</span>
                    </div>
                    <div className="flex gap-4 bg-emerald-950/40 text-emerald-300 py-0.5 -mx-4 px-4 border-l-2 border-emerald-400">
                      <span className="w-6 text-right select-none text-emerald-500/70">17</span>
                      <span>+&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&#123;&quot;@context&quot;: &quot;https://schema.org&quot;, &quot;@type&quot;: &quot;SoftwareApplication&quot;,</span>
                    </div>
                    <div className="flex gap-4 bg-emerald-950/40 text-emerald-300 py-0.5 -mx-4 px-4 border-l-2 border-emerald-400">
                      <span className="w-6 text-right select-none text-emerald-500/70">18</span>
                      <span>+&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&quot;name&quot;: &quot;FindableAI&quot;, &quot;applicationCategory&quot;: &quot;DeveloperApplication&quot;&#125;</span>
                    </div>
                    <div className="flex gap-4 bg-emerald-950/40 text-emerald-300 py-0.5 -mx-4 px-4 border-l-2 border-emerald-400">
                      <span className="w-6 text-right select-none text-emerald-500/70">19</span>
                      <span>+&nbsp;&nbsp;&nbsp;&lt;/script&gt;</span>
                    </div>
                    <div className="flex gap-4 opacity-50">
                      <span className="w-6 text-right select-none text-text-muted/60">20</span>
                      <span>&nbsp;&nbsp;&lt;/head&gt;</span>
                    </div>
                  </div>
                </div>

                {/* PR Review Footer */}
                <div className="p-3.5 sm:p-4 bg-surface-secondary/40 border-t border-white/[0.08] flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
                  <div className="flex items-center gap-2 text-text-muted text-[11px]">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                    <span>0 conflicts • Automatic merge eligible</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] text-text-muted hidden sm:inline">gh pr checkout 42</span>
                    <Link
                      href="/audit"
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors flex items-center gap-1.5 active:scale-95"
                    >
                      <GitPullRequest className="h-3 w-3" />
                      <span>Review Patch</span>
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>


        {/* Section 8: FAQ - Minimal Full-Width 2-Column Grid */}
        <section id="faq" data-reveal-section className="max-w-7xl mx-auto w-full mb-20 sm:mb-24 lg:mb-32">
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8 sm:mb-10 pb-6 border-b border-white/[0.08]">
            <div>
              <h2 className="text-2xl sm:text-3xl text-white font-semibold tracking-tight">
                Questions & Answers
              </h2>
              <p className="text-xs sm:text-sm text-text-muted mt-1">
                Everything you need to know about machine discoverability, deterministic scoring, and autonomous PR fixes.
              </p>
            </div>
            <a
              href="https://github.com/Chirag1724/FindableAI"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-text-muted hover:text-white transition-colors flex items-center gap-1 shrink-0"
            >
              <span>Have a question? Open an issue</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-text-muted" />
            </a>
          </div>

          {/* Full-Width 2-Column FAQ Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-5 w-full">
            {FAQS.map((faq, index) => (
              <details
                key={index}
                className="group rounded-xl bg-surface-secondary/40 border border-white/[0.07] hover:border-white/[0.14] transition-all duration-150 p-5 text-left h-fit"
                open={faq.defaultOpen}
              >
                <summary className="flex items-start justify-between cursor-pointer focus:outline-none gap-4">
                  <span className="text-sm sm:text-base text-white font-medium group-hover:text-text-primary transition-colors duration-150 leading-snug">
                    {faq.question}
                  </span>
                  <div className="h-5 w-5 rounded bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-text-muted shrink-0 transition-transform duration-150 group-open:rotate-45 mt-0.5">
                    <Plus className="h-3 w-3" />
                  </div>
                </summary>
                <div className="pt-3.5 text-xs sm:text-sm text-text-muted leading-relaxed border-t border-white/[0.05] mt-3">
                  <p>{faq.answer}</p>
                </div>
              </details>
            ))}
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/[0.08] bg-surface py-10 sm:py-12 text-xs text-text-muted">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6 pb-6 sm:pb-8 border-b border-white/[0.08]">
            {/* Left */}
            <div className="flex items-center gap-3">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={32}
                height={32}
                className="h-7 w-7 rounded-lg object-contain"
              />
              <div>
                <span className="text-sm text-text-primary font-semibold">FindableAI</span>
                <span className="text-[11px] text-text-muted block">
                  Machine Discoverability Optimization Platform
                </span>
              </div>
            </div>

            {/* Right Nav */}
            <div className="flex items-center justify-center sm:justify-end gap-x-6 gap-y-2.5">
              <a
                href={DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-text-primary transition-colors duration-150"
              >
                API Docs
              </a>
              <a
                href="https://github.com/Chirag1724/FindableAI"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-text-primary transition-colors duration-150"
              >
                GitHub
              </a>
            </div>
          </div>

          {/* Bottom Copyright */}
          <div className="pt-5 sm:pt-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left text-[11px]">
            <p>© {new Date().getFullYear()} FindableAI Inc. All rights reserved.</p>
            <p className="text-text-muted">
              Engineered with precision for autonomous web discoverability.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}