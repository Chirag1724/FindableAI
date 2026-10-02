"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowLeft,
  ArrowRight,
  Search,
  Sliders,
  Github,
  AlertCircle,
  Check,
  Shield,
  Code2,
  Scale,
  Sparkles,
  Zap,
  Globe,
  Lock,
} from "lucide-react";
import { createScan, getHealth } from "@/lib/api";
import type { ApiError } from "@/types/scan";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

const PERSONAS = [
  {
    id: "cto",
    name: "Skeptical CTO",
    role: "Architecture & Security",
    icon: Shield,
    description: "Evaluates security standards, architecture claims, and SLA grounding.",
  },
  {
    id: "developer",
    name: "Developer Evaluator",
    role: "Technical Integration",
    icon: Code2,
    description: "Checks code snippets, API contracts, schema models, and technical specs.",
  },
  {
    id: "procurement",
    name: "Procurement Officer",
    role: "Pricing & Legal Terms",
    icon: Scale,
    description: "Audits pricing tables, terms of service, compliance, and enterprise viability.",
  },
];

const SAMPLE_URLS = [
  { label: "Stripe", url: "https://stripe.com" },
  { label: "Linear", url: "https://linear.app" },
  { label: "Resend", url: "https://resend.com" },
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
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-secondary shadow-border text-xs">
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

export default function AuditPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [maxPages, setMaxPages] = useState(5);
  const [selectedPersonas, setSelectedPersonas] = useState<string[]>([
    "cto",
    "developer",
    "procurement",
  ]);
  const [repoUrl, setRepoUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const urlParam = params.get("url");
      if (urlParam) {
        setUrl(urlParam);
      }
    }
  }, []);

  useEffect(() => {
    if (!containerRef.current || prefersReducedMotion()) return;

    const ctx = gsap.context(() => {
      gsap.from("[data-animate-item]", {
        y: 16,
        opacity: 0,
        duration: 0.45,
        stagger: 0.07,
        ease: EASING.entrance,
      });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  const togglePersona = (id: string) => {
    setSelectedPersonas((prev) => {
      if (prev.includes(id)) {
        if (prev.length === 1) return prev; // Keep at least one
        return prev.filter((p) => p !== id);
      }
      return [...prev, id];
    });
  };

  const validateUrl = (value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) return "Please enter a website URL.";
    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return "URL must start with http:// or https://";
      }
    } catch {
      return "Please enter a valid URL (e.g. https://example.com)";
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedUrl = url.trim();
    const err = validateUrl(trimmedUrl);
    if (err) {
      setUrlError(err);
      return;
    }
    setUrlError(null);
    setSubmitError(null);
    setSubmitting(true);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      const scan = await createScan(
        {
          url: trimmedUrl,
          max_pages: maxPages,
          personas: selectedPersonas,
          repo_url: repoUrl.trim() || null,
        },
        ac.signal
      );
      router.push(`/scans/${scan.scan_id}`);
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") return;
      const apiErr = err as ApiError;
      if (apiErr.status === 400 && apiErr.detail?.startsWith("Security rejection")) {
        setSubmitError(
          `Security check blocked this URL: ${apiErr.detail}. Please use a publicly accessible URL.`
        );
      } else if (apiErr.status === 0) {
        setSubmitError(
          "Cannot reach the FindableAI API. Make sure the backend server is running on port 8000."
        );
      } else {
        setSubmitError(apiErr.message || "Failed to start audit scan. Please try again.");
      }
      setSubmitting(false);
    }
  };

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const handleUrlChange = (val: string) => {
    setUrl(val);
    if (urlError) setUrlError(validateUrl(val));
  };

  return (
    <div
      ref={containerRef}
      className="min-h-screen bg-background text-text-primary font-sans relative overflow-x-hidden flex flex-col justify-between"
    >
      {/* Ambient Grid & Atmospheric Glow Background */}
      <div className="pointer-events-none absolute inset-0 -top-20 flex items-center justify-center overflow-hidden">
        <div className="hero-grid-bg absolute inset-0 opacity-40" />
        <div className="hero-glow absolute inset-0 opacity-40" />
      </div>

      {/* Top Navigation Bar */}
      <header className="sticky top-0 z-50 glass border-b border-white/[0.08] py-3 sm:py-3.5 w-full">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            {/* Logo */}
            <Link href="/" className="flex items-center gap-2 sm:gap-3 group">
              <Image
                src="/logo.png"
                alt="FindableAI Logo"
                width={32}
                height={32}
                className="h-7 w-7 rounded-lg object-contain transition-transform duration-150 group-hover:scale-105"
                priority
              />
              <div className="flex items-baseline gap-1.5">
                <span className="text-base tracking-tight text-text-primary font-semibold">
                  FindableAI
                </span>
                <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase hidden sm:inline">
                  MDO
                </span>
              </div>
            </Link>

            {/* Navigation links & Breadcrumbs */}
            <nav className="hidden md:flex items-center gap-6 text-xs font-medium tracking-wide">
              <Link
                href="/"
                className="inline-flex items-center gap-1.5 text-text-muted hover:text-white transition-colors duration-150"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                <span>Overview</span>
              </Link>
              <Link
                href="/#crawl"
                className="text-text-muted hover:text-white transition-colors duration-150"
              >
                Extraction
              </Link>
              <Link
                href="/#intent"
                className="text-text-muted hover:text-white transition-colors duration-150"
              >
                Intent
              </Link>
              <Link
                href="/#fscore"
                className="text-text-muted hover:text-white transition-colors duration-150"
              >
                F-Score
              </Link>
            </nav>

            {/* Right Status */}
            <div className="flex items-center gap-3">
              <HealthIndicator />
              <a
                href="https://github.com/Chirag1724/FindableAI"
                target="_blank"
                rel="noopener noreferrer"
                className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-secondary shadow-border text-xs text-text-muted hover:text-white transition-colors duration-150"
              >
                <Github className="h-3 w-3 text-white" />
                <span>GitHub</span>
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="relative z-10 mx-auto max-w-3xl px-4 sm:px-6 lg:px-8 pt-8 sm:pt-12 pb-16 sm:pb-20 w-full">
        {/* Title Header */}
        <div className="text-center mb-8 sm:mb-10" data-animate-item>
          <div className="inline-flex items-center gap-2 px-3 sm:px-3.5 py-1 rounded-full bg-surface-secondary shadow-border text-[10px] sm:text-[11px] font-medium tracking-wider text-text-muted uppercase mb-3 sm:mb-4">
            <Sliders className="h-3 w-3 text-emerald-400" />
            <span>Diagnostic Console</span>
          </div>

          <h1 className="text-2xl sm:text-4xl lg:text-5xl text-white font-semibold tracking-tight mb-2.5 sm:mb-3">
            Initialize your machine audit
          </h1>
          <p className="text-xs sm:text-sm text-text-muted max-w-lg mx-auto leading-relaxed px-2 sm:px-0">
            Configure crawl scope, synthetic buyer personas, and optional GitHub repository integration for automated fixes.
          </p>
        </div>

        {/* Audit Form Card */}
        <div
          className="rounded-xl bg-surface shadow-border p-5 sm:p-8 relative overflow-hidden"
          data-animate-item
        >
          <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-6 sm:space-y-7">
            {/* Field 1: Target URL */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="scan-url-input"
                  className="block text-xs font-mono tracking-wider uppercase text-text-muted font-medium"
                >
                  Target Website URL <span className="text-rose-400">*</span>
                </label>

                {/* Quick Fill Sample Links */}
                <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono text-text-muted">
                  <span>Quick test:</span>
                  {SAMPLE_URLS.map((s) => (
                    <button
                      key={s.label}
                      type="button"
                      onClick={() => handleUrlChange(s.url)}
                      className="px-2 py-0.5 rounded bg-surface-secondary text-text-muted hover:text-white hover:bg-white/[0.08] transition-colors duration-150 border border-white/[0.06]"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              <div
                className="flex items-center gap-3 rounded-lg bg-surface-secondary shadow-border px-3.5 sm:px-4 py-3 sm:py-3.5 transition-all duration-150 focus-within:ring-2 focus-within:ring-white/30"
                style={{
                  boxShadow: urlError
                    ? "0 0 0 1px #f43f5e"
                    : undefined,
                }}
              >
                <Search size={16} className="shrink-0 text-text-muted" aria-hidden="true" />
                <input
                  id="scan-url-input"
                  data-testid="scan-url-input"
                  type="url"
                  value={url}
                  onChange={(e) => handleUrlChange(e.target.value)}
                  placeholder="https://acme.com"
                  required
                  aria-label="Target website URL to audit"
                  aria-describedby={urlError ? "url-error" : undefined}
                  aria-invalid={!!urlError}
                  className="w-full bg-transparent text-sm text-white placeholder-text-muted/50 focus:outline-none"
                />
              </div>

              {urlError && (
                <p id="url-error" role="alert" className="mt-2 text-xs text-rose-400">
                  {urlError}
                </p>
              )}
            </div>

            {/* Field 2: Synthetic Intent Personas */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-mono tracking-wider uppercase text-text-muted font-medium">
                  Synthetic Intent Personas
                </label>
                <span className="text-[11px] text-text-muted font-mono">
                  {selectedPersonas.length} of {PERSONAS.length} active
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 sm:gap-3">
                {PERSONAS.map((p) => {
                  const isActive = selectedPersonas.includes(p.id);
                  const Icon = p.icon;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => togglePersona(p.id)}
                      className={`p-3.5 rounded-lg text-left transition-all duration-150 flex flex-col justify-between shadow-border ${
                        isActive
                          ? "bg-surface-secondary ring-1 ring-emerald-500/40 shadow-sm"
                          : "bg-surface opacity-60 hover:opacity-100 hover:bg-surface-secondary"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <Icon className="h-3.5 w-3.5 text-text-muted" />
                          <span className="text-xs font-medium text-white">{p.name}</span>
                        </div>
                        <div
                          className={`h-4 w-4 rounded-full flex items-center justify-center text-[9px] shrink-0 transition-colors duration-150 ${
                            isActive
                              ? "bg-white text-black font-bold"
                              : "border border-white/20 text-transparent"
                          }`}
                        >
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </div>
                      </div>
                      <p className="text-[10px] text-text-muted leading-relaxed">
                        {p.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Field 3: Crawl Scope Slider */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="max-pages-slider"
                  className="block text-xs font-mono tracking-wider uppercase text-text-muted font-medium"
                >
                  Crawl Scope (Pages)
                </label>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-text-muted">
                    Est. {maxPages * 350}ms
                  </span>
                  <span className="font-mono text-xs text-text-primary bg-surface-secondary px-2.5 py-0.5 rounded-md shadow-border">
                    {maxPages} {maxPages === 1 ? "page" : "pages"}
                  </span>
                </div>
              </div>

              <input
                id="max-pages-slider"
                type="range"
                min={1}
                max={25}
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value, 10))}
                className="w-full accent-white cursor-pointer bg-surface-secondary h-1.5 rounded-lg appearance-none"
              />
              <div className="flex justify-between text-[10px] font-mono text-text-muted mt-1.5">
                <span>1 page (Homepage)</span>
                <span>5 pages (Recommended)</span>
                <span>25 pages (Deep)</span>
              </div>
            </div>

            {/* Field 4: Optional GitHub Repo for Automated PRs */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="repo-url-input"
                  className="text-xs font-mono tracking-wider uppercase text-text-muted font-medium flex items-center gap-1.5"
                >
                  <Github className="h-3.5 w-3.5 text-text-primary" />
                  <span>GitHub Repository (Optional)</span>
                </label>
                <span className="text-[10px] text-text-muted uppercase tracking-wider font-mono">
                  For automated PRs
                </span>
              </div>

              <div className="flex items-center gap-3 rounded-lg bg-surface-secondary shadow-border px-4 py-3 transition-colors duration-150 focus-within:ring-2 focus-within:ring-white/30">
                <input
                  id="repo-url-input"
                  type="url"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/organization/repository"
                  className="w-full bg-transparent text-xs text-white placeholder-text-muted/50 focus:outline-none"
                />
              </div>
              <p className="mt-1.5 text-[11px] text-text-muted">
                When provided, FindableAI generates unified DOM diffs and Schema.org JSON-LD microdata, opening a ready-to-merge pull request.
              </p>
            </div>

            {/* Global Error Banner */}
            {submitError && (
              <div
                role="alert"
                className="flex items-start gap-2.5 p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/50 text-xs text-rose-300"
              >
                <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                <p>{submitError}</p>
              </div>
            )}

            {/* Submit Action */}
            <div className="pt-2">
              <button
                type="submit"
                id="scan-submit"
                data-testid="scan-submit"
                disabled={submitting}
                className="group w-full py-3.5 px-6 rounded-lg bg-white text-black font-semibold text-xs tracking-wider uppercase transition-all duration-150 hover:bg-neutral-200 active:scale-[0.99] flex items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span>{submitting ? "Initializing Crawl..." : "Initialize Machine Audit"}</span>
                <ArrowRight className="h-4 w-4 transition-transform duration-150 group-hover:translate-x-1" />
              </button>
            </div>
          </form>
        </div>

        {/* 3 Telemetry Safeguard Badges */}
        <div
          className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center mt-6"
          data-animate-item
        >
          <div className="p-3 rounded-lg bg-surface/50 border border-white/[0.06] text-[11px] font-mono text-text-muted flex items-center justify-center gap-1.5">
            <Globe className="h-3 w-3 text-emerald-400" />
            <span>100% Non-Invasive Crawl</span>
          </div>
          <div className="p-3 rounded-lg bg-surface/50 border border-white/[0.06] text-[11px] font-mono text-text-muted flex items-center justify-center gap-1.5">
            <Lock className="h-3 w-3 text-sky-400" />
            <span>Zero Write-Access Required</span>
          </div>
          <div className="p-3 rounded-lg bg-surface/50 border border-white/[0.06] text-[11px] font-mono text-text-muted flex items-center justify-center gap-1.5">
            <Zap className="h-3 w-3 text-amber-400" />
            <span>Deterministic Scoring</span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/[0.08] bg-surface py-6 text-xs text-text-muted w-full">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px]">
          <p>© {new Date().getFullYear()} FindableAI Inc. All rights reserved.</p>
          <div className="flex items-center gap-4">
            <Link href="/" className="hover:text-white transition-colors duration-150">
              Overview
            </Link>
            <a
              href="https://github.com/Chirag1724/FindableAI"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-white transition-colors duration-150"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
