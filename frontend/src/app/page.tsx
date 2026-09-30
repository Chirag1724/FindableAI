"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Sparkles,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Plus,
  Globe,
  Bot,
  ShieldCheck,
  Activity,
  GitPullRequest,
  Cpu,
  Layers,
  Menu,
  X,
} from "lucide-react";
import { getHealth } from "@/lib/api";
import type { FScoreBreakdown } from "@/types/scan";
import dynamic from "next/dynamic";
import { ScanProgress } from "@/components/ScanProgress";
import { GaugeSkeleton } from "@/components/Skeletons";

const ScoreGauge = dynamic(
  () => import("@/components/ScoreGauge").then((mod) => mod.ScoreGauge),
  { ssr: false, loading: () => <GaugeSkeleton /> }
);

// Sample data for the live preview - uses exact backend schema shape
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

const PIPELINE_STAGES = [
  {
    step: "01",
    tag: "DOM EXTRACTION",
    title: "Headless Crawl & CSS Traceability",
    description:
      "Playwright traverses semantic DOM trees (h1–h6, article, table, meta), preserving exact CSS selectors so every discovered knowledge gap maps to an exact line in code.",
    icon: Globe,
    techBadge: "Playwright · CSS Selectors",
  },
  {
    step: "02",
    tag: "INTENT SYNTHESIS",
    title: "Buyer Persona Simulation",
    description:
      "Simulates skeptical CTOs, developer evaluators, and procurement officers, generating realistic high-intent queries that real users prompt into Perplexity and SearchGPT.",
    icon: Bot,
    techBadge: "Multi-Persona LLM Agent",
  },
  {
    step: "03",
    tag: "HYBRID RETRIEVAL",
    title: "Dense & Sparse Hybrid Fusion",
    description:
      "Mirrors LLM search context assembly by fusing pgvector dense embeddings with BM25 lexical keyword ranking using Reciprocal Rank Fusion (RRF).",
    icon: Cpu,
    techBadge: "pgvector + BM25 + RRF",
  },
  {
    step: "04",
    tag: "NLI VERIFICATION",
    title: "Factual Contradiction Detection",
    description:
      "A DeBERTa-v3 cross-encoder and LLM judge evaluate evidence entailment. Claims are classified as entailed, neutral, or conflicting contradictions.",
    icon: ShieldCheck,
    techBadge: "DeBERTa-v3 · NLI Judge",
  },
  {
    step: "05",
    tag: "F-SCORE ENGINE",
    title: "Deterministic 0–100 Scoring",
    description:
      "A mathematical formula balancing Intent Coverage (40%), Evidence Grounding (35%), Contradiction Penalty (15%), and Structural Clarity (10%).",
    icon: Activity,
    techBadge: "4-Factor Mathematical Formula",
  },
  {
    step: "06",
    tag: "AUTONOMOUS REMEDIATION",
    title: "DOM-Anchored GitHub Pull Requests",
    description:
      "Generates unified diffs with precise DOM content enhancements and Schema.org JSON-LD microdata, opening ready-to-merge pull requests directly on your repository.",
    icon: GitPullRequest,
    techBadge: "GitHub API · Zero Hallucination",
  },
];

const FAQS = [
  {
    question: "How does FindableAI differ from traditional SEO tools like Ahrefs or Semrush?",
    answer:
      "Traditional SEO tools optimize for keyword density, backlinks, and search crawlers like Googlebot. Modern searchers rely on AI answer engines like Perplexity, SearchGPT, and Claude. FindableAI audits machine discoverability: whether an LLM can retrieve, verify, and cite your factual claims without hallucinating.",
    defaultOpen: true,
  },
  {
    question: "What exactly is the Findability F-Score?",
    answer:
      "The F-Score is a deterministic 0 to 100 metric evaluated across four mathematically grounded pillars: Query Intent Coverage (40%), Evidence Grounding Entailment (35%), Factual Contradiction Penalty (15%), and DOM Structural Clarity (10%). It pinpoints exactly where AI engines lose confidence in your site.",
  },
  {
    question: "How do autonomous GitHub Pull Requests work?",
    answer:
      "When FindableAI identifies ungrounded queries or structural ambiguities, it traces the exact CSS selector path in your DOM. It then writes zero-hallucination unified diffs with content patches and Schema.org JSON-LD microdata, opening a clean PR directly in your repository for your team to review and merge.",
  },
  {
    question: "Can I run audits on local or staging URLs?",
    answer:
      "For live public URLs, audits execute immediately. For local or private staging environments, you can run our CLI crawler or provide a private GitHub repository URL to audit source files and templates directly.",
  },
  {
    question: "Do I need to install an SDK or grant write access to production?",
    answer:
      "No. Discoverability scans run non-invasively using headless Playwright browsers crawling your public URLs. For automatic code fixes, we only need GitHub repository write permissions for the designated remediation branch you authorize.",
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
    <div className="flex items-center gap-1.5 px-2 sm:px-2.5 py-1 rounded-full bg-atelier-coal border border-atelier-hairline text-xs shrink-0">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          online ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
        }`}
        aria-hidden="true"
      />
      <span className="text-[10px] font-mono tracking-wider text-atelier-fog">
        API {online ? "ONLINE" : "OFFLINE"}
      </span>
    </div>
  );
}

export default function HomePage() {
  const [headerScrolled, setHeaderScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setHeaderScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="min-h-screen bg-atelier-ink text-white font-sans selection:bg-atelier-gold selection:text-atelier-ink relative overflow-x-hidden">
      {/* Soft Gold Radial Ambient Glow at Top */}
      <div
        className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[900px] rounded-full opacity-20 blur-[130px]"
        style={{
          background:
            "radial-gradient(ellipse at center, #d4af72 0%, rgba(212, 175, 114, 0.05) 60%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* Sticky Top Nav */}
      <header
        className={`sticky top-0 z-50 transition-all duration-300 ${
          headerScrolled || mobileMenuOpen
            ? "backdrop-blur-md bg-atelier-ink/90 border-b border-atelier-hairline py-3 sm:py-3.5"
            : "bg-transparent border-b border-white/[0.06] py-3.5 sm:py-5"
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
                className="h-7 w-7 sm:h-9 sm:w-9 rounded-lg object-contain transition-transform group-hover:scale-105"
                priority
              />
              <div className="flex items-baseline gap-1.5">
                <span className="font-serif text-base sm:text-lg tracking-tight text-atelier-champagne font-medium">
                  FindableAI
                </span>
                <span className="text-[10px] font-mono tracking-widest text-atelier-fog uppercase hidden sm:inline">
                  MDO
                </span>
              </div>
            </Link>

            {/* Navigation links (md+) */}
            <nav className="hidden md:flex items-center gap-8 text-xs font-medium tracking-wide">
              <Link
                href="/audit"
                className="text-atelier-fog transition-colors hover:text-atelier-champagne"
              >
                Audit Engine
              </Link>
              <a
                href="#architecture"
                className="text-atelier-fog transition-colors hover:text-atelier-champagne"
              >
                Architecture
              </a>
              <a
                href="#preview"
                className="text-atelier-fog transition-colors hover:text-atelier-champagne"
              >
                F-Score Metric
              </a>
              <a
                href="#faq"
                className="text-atelier-fog transition-colors hover:text-atelier-champagne"
              >
                FAQ
              </a>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="text-atelier-fog transition-colors hover:text-atelier-champagne"
              >
                API Docs
              </a>
            </nav>

            {/* Actions & Mobile Menu Toggle */}
            <div className="flex items-center gap-2 sm:gap-3.5">
              <HealthIndicator />
              <Link
                href="/audit"
                className="hidden sm:inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-medium border border-atelier-gold/40 text-atelier-champagne bg-atelier-gold/5 hover:bg-atelier-gold/15 transition-all hover:border-atelier-gold active:scale-95"
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
                className="md:hidden flex items-center justify-center h-8 w-8 rounded-lg border border-atelier-hairline text-atelier-champagne bg-atelier-coal/80 hover:bg-atelier-panel transition-colors active:scale-95"
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
            <div className="md:hidden border-t border-atelier-hairline/60 bg-atelier-ink/95 backdrop-blur-xl px-2 pt-3 pb-5 space-y-3 mt-3 animate-in fade-in slide-in-from-top-2 duration-200">
              <nav className="flex flex-col space-y-1 text-xs">
                <Link
                  href="/audit"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-between px-3.5 py-2.5 rounded-lg text-atelier-champagne bg-atelier-coal/70 hover:bg-atelier-panel border border-atelier-hairline transition-colors font-medium"
                >
                  <span>Audit Engine</span>
                  <ArrowRight className="h-3.5 w-3.5 text-atelier-gold" />
                </Link>
                <a
                  href="#architecture"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-atelier-fog hover:text-atelier-champagne hover:bg-white/[0.04] transition-colors"
                >
                  Architecture Pipeline
                </a>
                <a
                  href="#preview"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-atelier-fog hover:text-atelier-champagne hover:bg-white/[0.04] transition-colors"
                >
                  F-Score Metric
                </a>
                <a
                  href="#faq"
                  onClick={() => setMobileMenuOpen(false)}
                  className="px-3.5 py-2 rounded-lg text-atelier-fog hover:text-atelier-champagne hover:bg-white/[0.04] transition-colors"
                >
                  FAQ
                </a>
                <a
                  href="http://localhost:8000/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-between px-3.5 py-2 rounded-lg text-atelier-fog hover:text-atelier-champagne hover:bg-white/[0.04] transition-colors"
                >
                  <span>API Docs</span>
                  <ArrowUpRight className="h-3.5 w-3.5 text-atelier-fog" />
                </a>
              </nav>

              <div className="pt-2 border-t border-atelier-hairline/50">
                <Link
                  href="/audit"
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center justify-center gap-2 w-full py-3 rounded-full bg-gold-gradient text-atelier-ink font-semibold text-xs tracking-wider uppercase shadow-md active:scale-95"
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
      <main className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Hero Section - Full Viewport First Fold */}
        <section
          id="audit"
          className="min-h-[calc(100vh-4rem)] min-h-[calc(100dvh-4rem)] flex flex-col justify-center items-center text-center max-w-3xl mx-auto py-8 sm:py-12"
        >
          {/* Eyebrow Pill */}
          <div className="inline-flex items-center gap-2 px-3 sm:px-3.5 py-1 rounded-full bg-atelier-coal border border-atelier-hairline text-[10px] sm:text-[11px] font-semibold tracking-[0.16em] sm:tracking-[0.22em] text-atelier-soft-gold uppercase mb-5 sm:mb-6 shadow-sm max-w-full">
            <Sparkles className="h-3 w-3 shrink-0 text-atelier-gold" />
            <span className="truncate">The Machine Discoverability Platform</span>
          </div>

          {/* Headline */}
          <h1 className="font-serif text-3xl sm:text-5xl lg:text-[4.2rem] leading-[1.12] sm:leading-[1.08] tracking-tight text-white mb-4 sm:mb-6">
            Discoverability, engineered with{" "}
            <span className="italic font-normal text-gold-gradient">precision</span>.
          </h1>

          {/* Subhead */}
          <p className="text-sm sm:text-base md:text-lg text-atelier-fog leading-relaxed max-w-2xl mx-auto mb-8 sm:mb-10 px-2 sm:px-0">
            Can AI search engines reliably cite your site? Audit Perplexity and SearchGPT citation rates, detect factual contradictions, and dispatch autonomous code fixes.
          </p>

          {/* Hero CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 w-full sm:w-auto px-4 sm:px-0">
            <Link
              href="/audit"
              className="group inline-flex items-center justify-center gap-2.5 px-8 py-3.5 sm:py-4 rounded-full bg-gold-gradient text-atelier-ink font-semibold text-xs tracking-wider uppercase transition-all duration-200 hover:brightness-105 active:scale-95 shadow-lg w-full sm:w-auto max-w-xs sm:max-w-none"
            >
              <span>Test Your Site</span>
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </Link>

            <a
              href="#architecture"
              className="inline-flex items-center justify-center gap-2 px-7 py-3.5 sm:py-4 rounded-full border border-atelier-gold/35 text-atelier-champagne bg-atelier-gold/5 hover:bg-atelier-gold/15 transition-all text-xs font-semibold tracking-wider uppercase hover:border-atelier-gold active:scale-95 w-full sm:w-auto max-w-xs sm:max-w-none"
            >
              <span>Explore Architecture ↓</span>
            </a>
          </div>
        </section>

        {/* How It Works / Architecture Pipeline Section (#architecture) */}
        <section id="architecture" className="mb-20 sm:mb-24 lg:mb-32 scroll-mt-24">
          <div className="text-center max-w-3xl mx-auto mb-12 sm:mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-atelier-coal border border-atelier-hairline text-[10px] sm:text-[11px] font-semibold tracking-[0.16em] sm:tracking-[0.22em] text-atelier-soft-gold uppercase mb-3 shadow-sm">
              <Layers className="h-3 w-3 text-atelier-gold" />
              <span>The Verification Loop</span>
            </div>
            <h2 className="font-serif text-2xl sm:text-4xl lg:text-5xl text-white font-normal mb-3 sm:mb-4">
              How machine discoverability is{" "}
              <span className="italic font-normal text-gold-gradient">computed</span>.
            </h2>
            <p className="text-xs sm:text-sm text-atelier-fog max-w-xl mx-auto leading-relaxed px-2 sm:px-0">
              From headless DOM extraction to natural language inference and automated pull requests. A deterministic 6-stage architecture.
            </p>
          </div>

          {/* 6-Stage Pipeline Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6 lg:gap-8">
            {PIPELINE_STAGES.map((stage) => {
              const IconComponent = stage.icon;
              return (
                <div
                  key={stage.step}
                  className="group relative rounded-2xl bg-atelier-coal/70 border border-atelier-hairline p-5 sm:p-7 transition-all duration-300 hover:border-atelier-gold/40 hover:bg-atelier-panel hover:shadow-gold-subtle flex flex-col justify-between"
                >
                  <div>
                    {/* Header: Step Number & Icon */}
                    <div className="flex items-center justify-between mb-4 sm:mb-5">
                      <span className="font-serif text-xl sm:text-2xl text-atelier-soft-gold/60 font-light group-hover:text-atelier-gold transition-colors">
                        {stage.step}
                      </span>
                      <div className="h-8 w-8 sm:h-9 sm:w-9 rounded-xl bg-atelier-ink border border-atelier-hairline flex items-center justify-center text-atelier-champagne group-hover:border-atelier-gold/40 transition-colors">
                        <IconComponent className="h-4 w-4" />
                      </div>
                    </div>

                    {/* Tag & Title */}
                    <p className="text-[10px] font-mono tracking-[0.2em] text-atelier-soft-gold uppercase mb-1.5">
                      {stage.tag}
                    </p>
                    <h3 className="font-serif text-base sm:text-lg text-white font-medium mb-2.5 sm:mb-3">
                      {stage.title}
                    </h3>

                    {/* Description */}
                    <p className="text-xs text-atelier-fog leading-relaxed">
                      {stage.description}
                    </p>
                  </div>

                  {/* Tech Badge Footer */}
                  <div className="mt-5 sm:mt-6 pt-3.5 sm:pt-4 border-t border-atelier-hairline/60 flex items-center justify-between text-[11px]">
                    <span className="font-mono text-atelier-fog/80 text-[10px]">
                      {stage.techBadge}
                    </span>
                    <span className="text-atelier-soft-gold text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                      →
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Deterministic Formula Callout */}
          <div className="mt-6 sm:mt-8 rounded-2xl bg-gradient-to-r from-atelier-coal via-atelier-panel to-atelier-coal border border-atelier-hairline p-4 sm:p-6 text-center overflow-x-auto">
            <p className="text-[10px] sm:text-[11px] font-mono text-atelier-soft-gold tracking-widest uppercase mb-1.5">
              THE MATHEMATICAL INVARIANT
            </p>
            <p className="font-mono text-[11px] sm:text-xs md:text-sm text-atelier-champagne leading-relaxed break-words sm:whitespace-nowrap">
              F-Score = (0.40 × Coverage) + (0.35 × Entailment) − (0.15 × Contradiction) + (0.10 × Structural DOM)
            </p>
          </div>
        </section>

        {/* Live Preview Section (#preview) */}
        <section id="preview" className="mb-20 sm:mb-24 lg:mb-32">
          <div className="text-center mb-8 sm:mb-10">
            <p className="text-[10px] sm:text-[11px] font-semibold tracking-[0.2em] sm:tracking-[0.24em] text-atelier-soft-gold uppercase mb-2">
              Evidence-Grounded Intelligence
            </p>
            <h2 className="font-serif text-2xl sm:text-4xl text-white font-medium mb-3">
              Sample output from a live MDO scan
            </h2>
            <p className="text-xs sm:text-sm text-atelier-fog max-w-xl mx-auto px-2 sm:px-0">
              Real telemetry generated from multi-page crawls, hybrid pgvector retrieval, and DeBERTa-v3 natural language inference.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* ScoreGauge Panel */}
            <div className="rounded-2xl bg-atelier-panel border border-atelier-hairline shadow-gold-subtle p-4 sm:p-8">
              <ScoreGauge fScore={SAMPLE_FSCORE} />
            </div>

            {/* Scan Progress & Stats Panel */}
            <div className="space-y-4 sm:space-y-6">
              <div className="rounded-2xl bg-atelier-panel border border-atelier-hairline shadow-gold-subtle p-4 sm:p-8">
                <ScanProgress
                  currentStatus="completed"
                  latestEvent={{
                    scan_id: "scan_preview",
                    status: "completed",
                    progress_percent: 100,
                    current_step: "Audit Complete",
                    message: "Findability report, citation graph, and patches ready.",
                    timestamp: new Date().toISOString(),
                  }}
                  lastGoodStatus="completed"
                />
              </div>

              {/* Three Stat Cards */}
              <div className="grid grid-cols-3 gap-2 sm:gap-4">
                {[
                  { v: "30", l: "Buyer queries simulated" },
                  { v: "4", l: "F-Score core sub-factors" },
                  { v: "1-Click", l: "DOM fix pull request" },
                ].map(({ v, l }) => (
                  <div
                    key={l}
                    className="rounded-xl bg-atelier-coal border border-atelier-hairline p-2.5 sm:p-4 text-center flex flex-col justify-center"
                  >
                    <p className="font-serif text-lg sm:text-2xl font-medium text-white mb-0.5">{v}</p>
                    <p className="text-[10px] sm:text-[11px] text-atelier-fog leading-tight break-words">{l}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Answer Engine Trust Strip */}
        <section className="mb-20 sm:mb-24 lg:mb-32 text-center">
          <p className="text-[10px] sm:text-[11px] font-semibold tracking-[0.2em] sm:tracking-[0.24em] text-atelier-fog uppercase mb-6 sm:mb-8">
            Engineered to maximize citation rates across
          </p>
          <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-14 opacity-75">
            {TRUST_ENGINES.map((engine) => (
              <span
                key={engine}
                className="font-serif italic text-base sm:text-2xl text-atelier-fog/80 hover:text-atelier-champagne transition-colors cursor-default"
              >
                {engine}
              </span>
            ))}
          </div>
        </section>

        {/* Enterprise Commission Bar */}
        <section className="mb-20 sm:mb-24 lg:mb-32">
          <div className="rounded-2xl border border-atelier-hairline bg-gradient-to-r from-atelier-coal via-atelier-panel to-atelier-coal p-5 sm:p-9 flex flex-col md:flex-row items-start md:items-center justify-between gap-5 sm:gap-6 shadow-sm">
            <div className="flex items-start sm:items-center gap-3.5 sm:gap-4">
              <div className="h-10 w-10 sm:h-12 sm:w-12 rounded-xl bg-atelier-ink border border-atelier-gold/30 flex items-center justify-center shrink-0 shadow-inner">
                <Building2 className="h-5 w-5 sm:h-6 sm:w-6 text-atelier-champagne" />
              </div>
              <div>
                <h3 className="font-serif text-lg sm:text-2xl text-white font-medium mb-1">
                  Need a custom enterprise commission?
                </h3>
                <p className="text-xs sm:text-sm text-atelier-fog max-w-2xl leading-relaxed">
                  Dedicated Playwright crawler clusters, custom LLM benchmark suites, private VPC deployment, and white-glove onboarding for high-traffic platforms.
                </p>
              </div>
            </div>

            <a
              href="mailto:enterprise@findable.ai?subject=Enterprise%20Commission%20Inquiry"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-full border border-atelier-gold/40 text-atelier-champagne bg-atelier-gold/5 hover:bg-atelier-gold/15 transition-all text-xs font-semibold tracking-wider uppercase shrink-0 hover:border-atelier-gold active:scale-95 w-full md:w-auto"
            >
              <span>Talk to our team</span>
              <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
          </div>
        </section>

        {/* FAQ Accordion (#faq) */}
        <section id="faq" className="mx-auto max-w-3xl mb-20 sm:mb-24 lg:mb-32">
          <div className="text-center mb-10 sm:mb-12">
            <h2 className="font-serif text-2xl sm:text-4xl text-white font-normal mb-3">
              Questions, answered
            </h2>
            <p className="text-xs sm:text-sm text-atelier-fog px-2 sm:px-0">
              Everything you need to understand about machine discoverability, F-Scores, and automated fixes.
            </p>
          </div>

          <div className="divide-y divide-atelier-hairline border-y border-atelier-hairline">
            {FAQS.map((faq, index) => (
              <details
                key={index}
                className="group py-4 sm:py-5 transition-colors focus-within:bg-atelier-coal/20"
                open={faq.defaultOpen}
              >
                <summary className="flex items-center justify-between cursor-pointer text-left focus:outline-none gap-4">
                  <span className="font-serif text-sm sm:text-lg text-white font-normal group-hover:text-atelier-champagne transition-colors pr-2">
                    {faq.question}
                  </span>
                  <div className="h-6 w-6 sm:h-7 sm:w-7 rounded-full border border-atelier-hairline flex items-center justify-center text-atelier-soft-gold shrink-0 transition-transform duration-200 group-open:rotate-45 group-hover:border-atelier-gold/40">
                    <Plus className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                  </div>
                </summary>
                <div className="pt-3 pb-1 pr-6 sm:pr-12 text-xs sm:text-sm text-atelier-fog leading-relaxed">
                  <p>{faq.answer}</p>
                </div>
              </details>
            ))}
          </div>

          {/* Support Note */}
          <div className="text-center mt-6 sm:mt-8">
            <p className="text-xs text-atelier-fog">
              Have a question not listed here?{" "}
              <a
                href="mailto:support@findable.ai"
                className="text-atelier-champagne hover:underline underline-offset-4"
              >
                Ping our team and we will sort it together.
              </a>
            </p>
          </div>
        </section>
      </main>

      {/* Boutique Footer */}
      <footer className="border-t border-atelier-hairline bg-atelier-coal py-10 sm:py-12 text-xs text-atelier-fog">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-6 pb-6 sm:pb-8 border-b border-atelier-hairline/60">
            {/* Left */}
            <div className="flex items-center gap-3">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={32}
                height={32}
                className="h-8 w-8 rounded-lg object-contain"
              />
              <div>
                <span className="font-serif text-base text-atelier-champagne font-medium">FindableAI</span>
                <span className="text-[11px] text-atelier-fog block">
                  Autonomous Machine Discoverability Platform
                </span>
              </div>
            </div>

            {/* Right Nav */}
            <div className="flex flex-wrap items-center justify-center sm:justify-end gap-x-5 gap-y-2.5">
              <Link href="/audit" className="hover:text-atelier-champagne transition-colors">
                Audit Engine
              </Link>
              <a href="#architecture" className="hover:text-atelier-champagne transition-colors">
                Architecture
              </a>
              <a href="#preview" className="hover:text-atelier-champagne transition-colors">
                F-Score Metric
              </a>
              <a href="#faq" className="hover:text-atelier-champagne transition-colors">
                FAQ
              </a>
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-atelier-champagne transition-colors"
              >
                API Docs
              </a>
              <a
                href="https://github.com"
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-atelier-champagne transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>

          {/* Bottom Copyright */}
          <div className="pt-5 sm:pt-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left text-[11px]">
            <p>© {new Date().getFullYear()} FindableAI Inc. All rights reserved.</p>
            <p className="text-atelier-soft-gold">
              Engineered with precision for autonomous web discoverability.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}