"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowRight,
  ArrowUpRight,
  Plus,
  Globe,
  Bot,
  ShieldCheck,
  Activity,
  GitPullRequest,
  Menu,
  X,
  Zap,
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
    weight: 0.4,
    score: 79.0,
    details: "Answers 11 of 14 simulated high-intent queries.",
    strengths: ["Clear pricing and specs", "Detailed architecture docs"],
    gaps: ["Missing security compliance microdata"],
  },
  entailment: {
    name: "Evidence Grounding",
    weight: 0.35,
    score: 72.5,
    details: "Most claims are factually grounded in crawled content.",
    strengths: ["Specific benchmark numbers"],
    gaps: ["Vague SLA terms"],
  },
  contradiction_penalty: {
    name: "Contradiction Penalty",
    weight: 0.15,
    score: 8.0,
    details: "One conflict detected between homepage and docs.",
    strengths: [],
    gaps: ["Pricing table contradicts FAQ terms"],
  },
  structural_clarity: {
    name: "DOM Structure",
    weight: 0.1,
    score: 82.0,
    details: "Good heading hierarchy, missing JSON-LD.",
    strengths: ["Semantic HTML5 elements"],
    gaps: ["No Schema.org microdata"],
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
];

const TRUST_ENGINES = [
  "Perplexity",
  "SearchGPT",
  "Gemini Pro",
  "Claude 3.5",
  "Mistral Large",
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
                href="/audit"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                Audit Engine
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
              <a
                href={DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-muted transition-colors duration-150 hover:text-text-primary"
              >
                API Docs
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
                  href="/audit"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-between px-3.5 py-2.5 rounded-lg text-text-primary bg-surface-secondary shadow-border font-medium"
                >
                  <span>Audit Engine</span>
                  <ArrowRight className="h-3.5 w-3.5 text-text-muted" />
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
                <a
                  href={DOCS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-between px-3.5 py-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-white/[0.04] transition-colors duration-150"
                >
                  <span>API Docs</span>
                  <ArrowUpRight className="h-3.5 w-3.5 text-text-muted" />
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
          className="relative min-h-[calc(100vh-4rem)] min-h-[calc(100dvh-4rem)] flex flex-col justify-center items-center text-center max-w-4xl mx-auto py-12 sm:py-16"
        >
          {/* Ambient Grid & Glow Layer */}
          <div className="pointer-events-none absolute inset-0 -top-20 flex items-center justify-center overflow-hidden">
            <div className="hero-grid-bg absolute inset-0 opacity-70" />
            <div className="hero-glow absolute inset-0 opacity-60" />
          </div>

          {/* Eyebrow Pill */}
          <div
            data-hero-reveal
            className="relative z-10 inline-flex items-center gap-2 px-3 sm:px-3.5 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] sm:text-[11px] font-medium tracking-wider text-text-muted uppercase mb-5 sm:mb-6"
          >
            <Zap className="h-3 w-3 shrink-0 text-white" />
            <span className="truncate">Machine Discoverability Optimization</span>
          </div>

          {/* Headline */}
          <h1
            data-hero-reveal
            className="relative z-10 text-3xl sm:text-5xl lg:text-6xl leading-[1.12] sm:leading-[1.08] tracking-tight text-white font-semibold mb-4 sm:mb-6"
          >
            Discoverability, engineered with precision.
          </h1>

          {/* Subhead */}
          <p
            data-hero-reveal
            className="relative z-10 text-sm sm:text-base md:text-lg text-text-muted leading-relaxed max-w-2xl mx-auto mb-8 sm:mb-10 px-2 sm:px-0"
          >
            Audit answer engine citation rates, detect factual contradictions, and dispatch autonomous code fixes.
          </p>

          {/* Hero CTAs + Subtle telemetry badge */}
          <div
            data-hero-reveal
            className="relative z-10 flex flex-col items-center justify-center gap-4 w-full sm:w-auto px-4 sm:px-0"
          >
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 w-full sm:w-auto">
              <Link
                href="/audit"
                className="group inline-flex items-center justify-center gap-2.5 px-6 py-3 rounded-lg bg-white text-black font-semibold text-xs tracking-wider uppercase transition-all duration-150 hover:bg-neutral-200 active:scale-95 w-full sm:w-auto max-w-xs sm:max-w-none"
              >
                <span>Test Your Site</span>
                <ArrowRight className="h-4 w-4 transition-transform duration-150 group-hover:translate-x-1" />
              </Link>

              <a
                href="#crawl"
                className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-surface-secondary shadow-border-interactive text-text-primary hover:bg-surface-tertiary transition-all duration-150 text-xs font-medium tracking-wider uppercase active:scale-95 w-full sm:w-auto max-w-xs sm:max-w-none"
              >
                <span>Explore Architecture ↓</span>
              </a>
            </div>

            {/* Subtle floating telemetry badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-secondary shadow-border text-[11px] font-mono text-text-muted mt-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>Telemetry: 148 DOM nodes · 0 ungrounded claims</span>
            </div>
          </div>
        </section>

        {/* Section 2: Feature 1 - Crawl & DOM Extraction */}
        <section id="crawl" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-5xl mx-auto w-full">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] font-mono tracking-wider text-text-muted uppercase mb-3">
              <Globe className="h-3 w-3 text-white" />
              <span>Stage 01</span>
            </div>
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-2.5">
              See what AI engines see
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0 leading-relaxed">
              Headless crawlers extract semantic trees while preserving precise CSS selector paths for code attribution.
            </p>
          </div>

          {/* Focused UI Artifact: Live DOM Extraction & Chunking Inspector */}
          <CrawlInspector />

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Every text claim and structural node remains anchored to an exact CSS selector in your source templates.
          </p>
        </section>

        {/* Section 3: Feature 2 - Synthetic Intent Simulation */}
        <section id="intent" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-5xl mx-auto w-full">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] font-mono tracking-wider text-text-muted uppercase mb-3">
              <Bot className="h-3 w-3 text-white" />
              <span>Stage 02</span>
            </div>
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-2.5">
              Questions buyers actually ask
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0 leading-relaxed">
              Simulate multi-persona buyer queries across technical, security, and pricing search vectors.
            </p>
          </div>

          {/* Focused UI Artifact: Live Synthetic Buyer Intent Simulator */}
          <IntentSimulator />

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Evaluates 30 synthetic queries across CTO, developer, and procurement buyer personas to locate answer blindspots.
          </p>
        </section>

        {/* Section 4: Architecture Pillars (Visual 3-Card Grid) */}
        <ArchitecturePillars />

        {/* Section 5: Feature 3 - Contradiction Detection */}
        <section id="contradictions" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-5xl mx-auto w-full">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] font-mono tracking-wider text-text-muted uppercase mb-3">
              <ShieldCheck className="h-3 w-3 text-white" />
              <span>Stage 03</span>
            </div>
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-2.5">
              Catch cross-page conflicts
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0 leading-relaxed">
              Natural language inference judges cross-reference claims between product pages, documentation, and pricing terms.
            </p>
          </div>

          {/* Focused UI Artifact: Live NLI Cross-Page Contradiction Inspector */}
          <ContradictionInspector />

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Identifies conflicting factual claims across your domain before answer engines cite inconsistent data.
          </p>
        </section>

        {/* Section 6: Feature 4 - Deterministic F-Score */}
        <section id="fscore" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-5xl mx-auto w-full">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] font-mono tracking-wider text-text-muted uppercase mb-3">
              <Activity className="h-3 w-3 text-white" />
              <span>Stage 04</span>
            </div>
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-2.5">
              One score, four pillars
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0 leading-relaxed">
              A single 0 to 100 benchmark balancing query coverage, evidence consistency, DOM structure, and accessibility.
            </p>
          </div>

          {/* Focused UI Artifact: 3-Card Bento + 4-Column Diagnostic Grid */}
          <div className="w-full">
            <ScoreGauge fScore={SAMPLE_FSCORE} />
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-6 sm:mt-8 px-4">
            Calculated deterministically using the canonical formula: 40% Coverage, 30% Consistency, 20% Structure, and 10% Extractability.
          </p>
        </section>

        {/* Section 7: Feature 5 - Autonomous Remediation */}
        <section id="remediation" data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-32 pt-4 max-w-5xl mx-auto w-full">
          <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-10">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] font-mono tracking-wider text-text-muted uppercase mb-3">
              <GitPullRequest className="h-3 w-3 text-white" />
              <span>Stage 05</span>
            </div>
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-2.5">
              From gap to pull request
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0 leading-relaxed">
              Generate unified diffs and Schema.org microdata ready for review in your codebase.
            </p>
          </div>

          {/* Focused UI Artifact: Compact Syntax-Highlighted Diff Preview */}
          <div className="rounded-xl bg-surface shadow-border p-5 sm:p-6 font-mono text-xs space-y-3">
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08] text-text-muted text-[11px]">
              <span>patch/schema-org-metadata.diff</span>
              <span className="text-emerald-400">+4 lines</span>
            </div>
            <div className="bg-background rounded-lg p-4 shadow-border space-y-1 overflow-x-auto">
              <p className="text-text-muted">@@ -14,3 +14,7 @@</p>
              <p className="text-text-muted">&nbsp;&nbsp;&lt;meta name=&quot;description&quot; content=&quot;AI Discoverability Platform&quot; /&gt;</p>
              <p className="text-emerald-400 bg-emerald-950/30 px-1 rounded">+ &lt;script type=&quot;application/ld+json&quot;&gt;</p>
              <p className="text-emerald-400 bg-emerald-950/30 px-1 rounded">+ &nbsp;&nbsp;&#123; &quot;@context&quot;: &quot;https://schema.org&quot;, &quot;@type&quot;: &quot;SoftwareApplication&quot;, &quot;name&quot;: &quot;FindableAI&quot; &#125;</p>
              <p className="text-emerald-400 bg-emerald-950/30 px-1 rounded">+ &lt;/script&gt;</p>
              <p className="text-text-muted">&nbsp;&nbsp;&lt;/head&gt;</p>
            </div>
          </div>

          {/* Bolded single-sentence caption */}
          <p className="text-center text-xs font-semibold text-text-primary mt-4 sm:mt-5 px-4">
            Proposes targeted pull requests with DOM-anchored fixes for your engineering team to review and merge.
          </p>
        </section>

        {/* Answer Engine Trust Strip */}
        <section data-reveal-section className="mb-20 sm:mb-24 lg:mb-32 text-center max-w-5xl mx-auto w-full">
          <p className="text-[10px] sm:text-[11px] font-mono tracking-wider text-text-muted uppercase mb-6 sm:mb-8 font-medium">
            Engineered to maximize citation rates across
          </p>
          <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-12 opacity-80">
            {TRUST_ENGINES.map((engine) => (
              <span
                key={engine}
                className="text-sm sm:text-xl text-text-muted hover:text-text-primary transition-colors duration-150 cursor-default font-medium"
              >
                {engine}
              </span>
            ))}
          </div>
        </section>

        {/* Section 8: FAQ Accordion */}
        <section id="faq" data-reveal-section className="mx-auto max-w-3xl mb-20 sm:mb-24 lg:mb-32">
          <div className="text-center mb-10 sm:mb-12">
            <h2 className="text-2xl sm:text-4xl text-white font-semibold tracking-tight mb-3">
              Questions, answered
            </h2>
            <p className="text-xs sm:text-sm text-text-muted px-2 sm:px-0">
              Everything you need to understand about machine discoverability, F-Scores, and automated fixes.
            </p>
          </div>

          <div className="divide-y divide-white/[0.08] border-y border-white/[0.08]">
            {FAQS.map((faq, index) => (
              <details
                key={index}
                className="group py-4 sm:py-5 transition-colors duration-150"
                open={faq.defaultOpen}
              >
                <summary className="flex items-center justify-between cursor-pointer text-left focus:outline-none gap-4">
                  <span className="text-sm sm:text-base text-white font-medium group-hover:text-text-primary transition-colors duration-150 pr-2">
                    {faq.question}
                  </span>
                  <div className="h-6 w-6 rounded-md shadow-border flex items-center justify-center text-text-muted shrink-0 transition-transform duration-150 group-open:rotate-45">
                    <Plus className="h-3.5 w-3.5" />
                  </div>
                </summary>
                <div className="pt-3 pb-1 pr-6 sm:pr-12 text-xs sm:text-sm text-text-muted leading-relaxed">
                  <p>{faq.answer}</p>
                </div>
              </details>
            ))}
          </div>

          {/* Support Note */}
          <div className="text-center mt-6 sm:mt-8">
            <p className="text-xs text-text-muted">
              Have a question not listed here?{" "}
              <a
                href="https://github.com/Chirag1724/FindableAI"
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-primary hover:underline underline-offset-4 font-medium"
              >
                Check the repo or open an issue on GitHub.
              </a>
            </p>
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