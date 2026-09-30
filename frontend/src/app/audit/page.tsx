"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import {
  ArrowLeft,
  ArrowRight,
  Search,
  Sparkles,
  Bot,
  Layers,
  Github,
  AlertCircle,
  Check,
} from "lucide-react";
import { createScan, getHealth } from "@/lib/api";
import type { ApiError } from "@/types/scan";

const PERSONAS = [
  {
    id: "cto",
    name: "Skeptical CTO",
    description: "Evaluates security standards, architecture claims, and SLA grounding.",
  },
  {
    id: "developer",
    name: "Developer Evaluator",
    description: "Checks code snippets, API contracts, schema models, and technical specs.",
  },
  {
    id: "procurement",
    name: "Procurement Officer",
    description: "Audits pricing tables, terms of service, compliance, and enterprise viability.",
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
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-atelier-coal border border-atelier-hairline text-xs">
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
    <div className="min-h-screen bg-atelier-ink text-white font-sans selection:bg-atelier-gold selection:text-atelier-ink relative overflow-hidden">
      {/* Soft Gold Radial Ambient Glow at Top */}
      <div
        className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[900px] rounded-full opacity-20 blur-[130px]"
        style={{
          background:
            "radial-gradient(ellipse at center, #d4af72 0%, rgba(212, 175, 114, 0.05) 60%, transparent 100%)",
        }}
        aria-hidden="true"
      />

      {/* Top Header */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-atelier-ink/85 border-b border-atelier-hairline py-4">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-medium text-atelier-fog hover:text-atelier-champagne transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Overview</span>
          </Link>

          <Link href="/" className="flex items-center gap-2.5 group">
            <Image
              src="/logo.png"
              alt="FindableAI Logo"
              width={28}
              height={28}
              className="h-7 w-7 rounded-md object-contain"
            />
            <span className="font-serif text-base tracking-tight text-atelier-champagne font-medium">
              FindableAI
            </span>
          </Link>

          <HealthIndicator />
        </div>
      </header>

      {/* Main Workspace */}
      <main className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8 pt-12 pb-24 lg:pt-16">
        {/* Title */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-atelier-coal border border-atelier-hairline text-[11px] font-semibold tracking-[0.22em] text-atelier-soft-gold uppercase mb-4 shadow-sm">
            <Sparkles className="h-3 w-3 text-atelier-gold" />
            <span>MDO Diagnostic Console</span>
          </div>

          <h1 className="font-serif text-3xl sm:text-4xl lg:text-5xl text-white font-normal mb-3">
            Initialize your machine audit
          </h1>
          <p className="text-xs sm:text-sm text-atelier-fog max-w-lg mx-auto leading-relaxed">
            Configure crawl scope, synthetic buyer personas, and optional GitHub repository integration for automated zero-hallucination PRs.
          </p>
        </div>

        {/* Audit Form Card */}
        <div className="rounded-2xl bg-atelier-panel border border-atelier-hairline shadow-gold-panel p-6 sm:p-9 relative">
          <form onSubmit={(e) => void handleSubmit(e)} noValidate className="space-y-7">
            {/* Field 1: Target URL */}
            <div>
              <label
                htmlFor="scan-url-input"
                className="block text-xs font-mono tracking-wider uppercase text-atelier-soft-gold mb-2 font-medium"
              >
                Target Website URL <span className="text-atelier-gold">*</span>
              </label>

              <div
                className="flex items-center gap-3 rounded-xl bg-atelier-coal border px-4 py-3.5 transition-colors"
                style={{
                  borderColor: urlError ? "#f43f5e" : "#26262c",
                }}
              >
                <Search size={16} className="shrink-0 text-atelier-soft-gold" aria-hidden="true" />
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
                  className="w-full bg-transparent text-sm text-white placeholder-atelier-fog/50 focus:outline-none"
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
                <label className="block text-xs font-mono tracking-wider uppercase text-atelier-soft-gold font-medium">
                  Synthetic Intent Personas
                </label>
                <span className="text-[11px] text-atelier-fog">
                  {selectedPersonas.length} of {PERSONAS.length} active
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {PERSONAS.map((p) => {
                  const isActive = selectedPersonas.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => togglePersona(p.id)}
                      className={`p-3.5 rounded-xl border text-left transition-all duration-200 flex flex-col justify-between ${
                        isActive
                          ? "bg-atelier-coal border-atelier-gold/40 shadow-sm"
                          : "bg-atelier-coal/40 border-atelier-hairline opacity-60 hover:opacity-100"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium text-white">{p.name}</span>
                        <div
                          className={`h-4 w-4 rounded-full flex items-center justify-center border text-[9px] ${
                            isActive
                              ? "bg-gold-gradient text-atelier-ink border-transparent font-bold"
                              : "border-atelier-hairline text-transparent"
                          }`}
                        >
                          <Check className="h-2.5 w-2.5 stroke-[3]" />
                        </div>
                      </div>
                      <p className="text-[10px] text-atelier-fog leading-relaxed">
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
                  className="block text-xs font-mono tracking-wider uppercase text-atelier-soft-gold font-medium"
                >
                  Crawl Scope (Pages)
                </label>
                <span className="font-mono text-xs text-atelier-champagne bg-atelier-coal px-2.5 py-1 rounded-md border border-atelier-hairline">
                  {maxPages} {maxPages === 1 ? "page" : "pages"}
                </span>
              </div>

              <input
                id="max-pages-slider"
                type="range"
                min={1}
                max={25}
                value={maxPages}
                onChange={(e) => setMaxPages(parseInt(e.target.value, 10))}
                className="w-full accent-[#d4af72] cursor-pointer bg-atelier-coal"
              />
              <div className="flex justify-between text-[10px] font-mono text-atelier-fog mt-1">
                <span>1 page (Homepage only)</span>
                <span>10 pages</span>
                <span>25 pages (Deep crawl)</span>
              </div>
            </div>

            {/* Field 4: Optional GitHub Repo for Automated PRs */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="repo-url-input"
                  className="block text-xs font-mono tracking-wider uppercase text-atelier-soft-gold font-medium flex items-center gap-1.5"
                >
                  <Github className="h-3.5 w-3.5 text-atelier-champagne" />
                  <span>GitHub Repository (Optional)</span>
                </label>
                <span className="text-[10px] text-atelier-fog uppercase tracking-wider">
                  For automated PRs
                </span>
              </div>

              <div className="flex items-center gap-3 rounded-xl bg-atelier-coal border border-atelier-hairline px-4 py-3 transition-colors focus-within:border-atelier-gold/40">
                <input
                  id="repo-url-input"
                  type="url"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/organization/repository"
                  className="w-full bg-transparent text-xs text-white placeholder-atelier-fog/50 focus:outline-none"
                />
              </div>
              <p className="mt-1.5 text-[11px] text-atelier-fog">
                When provided, FindableAI generates unified DOM diffs and Schema.org JSON-LD microdata, opening a ready-to-merge pull request.
              </p>
            </div>

            {/* Global Error Banner */}
            {submitError && (
              <div
                role="alert"
                className="flex items-start gap-2.5 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/50 text-xs text-rose-300"
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
                className="group w-full py-4 px-6 rounded-full bg-gold-gradient text-atelier-ink font-semibold text-xs tracking-wider uppercase transition-all duration-200 hover:brightness-105 active:scale-95 shadow-lg flex items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span>{submitting ? "Initializing Crawl..." : "Initialize Machine Audit"}</span>
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
              </button>
            </div>
          </form>
        </div>

        {/* Console Safeguard Note */}
        <p className="text-center text-[11px] text-atelier-fog mt-6">
          Audits run non-invasively via headless Playwright browsers. No code changes are pushed without your explicit pull request review.
        </p>
      </main>
    </div>
  );
}
