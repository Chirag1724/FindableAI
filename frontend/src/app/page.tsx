"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { Search, ChevronDown, ChevronUp, Activity } from "lucide-react";
import { createScan, getHealth } from "@/lib/api";
import type { ApiError } from "@/types/scan";
import dynamic from "next/dynamic";
import { ScanProgress } from "@/components/ScanProgress";
import { GaugeSkeleton } from "@/components/Skeletons";
import type { FScoreBreakdown } from "@/types/scan";

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
    weight: 0.40,
    score: 79.0,
    details: "Answers 11 of 14 simulated high-intent queries.",
    strengths: ["Clear pricing page", "Detailed feature list"],
    gaps: ["Missing security compliance info"],
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
    gaps: ["Opening hours differ across pages"],
  },
  structural_clarity: {
    name: "DOM Structure",
    weight: 0.10,
    score: 82.0,
    details: "Good heading hierarchy, missing JSON-LD.",
    strengths: ["Semantic HTML5 elements"],
    gaps: ["No Schema.org microdata"],
  },
};

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
    <div className="flex items-center gap-1.5">
      <span
        className={`h-1.5 w-1.5 rounded-full ${online ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
          }`}
        aria-hidden="true"
      />
      <span className="text-xs text-[#A1A1A1]">
        API {online ? "online" : "offline"}
      </span>
    </div>
  );
}

function StatCard({
  value,
  label,
}: {
  value: string;
  label: string;
}) {
  return (
    <div
      className="rounded-xl bg-[#141414] px-4 py-4 sm:px-6 sm:py-5 animate-fade-up"
      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
    >
      <p className="text-2xl font-bold text-[#EDEDED]">{value}</p>
      <p className="mt-0.5 text-xs text-[#A1A1A1]">{label}</p>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [maxPages, setMaxPages] = useState(5);
  const [repoUrl, setRepoUrl] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [headerScrolled, setHeaderScrolled] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Sticky header glass effect on scroll
  useEffect(() => {
    const onScroll = () => setHeaderScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const validateUrl = (value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) return "Please enter a URL.";
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
          personas: ["cto", "developer", "procurement"],
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
        setSubmitError(apiErr.message || "Failed to start scan. Please try again.");
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
    <div className="min-h-screen bg-background">
      {/* Fixed header */}
      <header
        className={`fixed inset-x-0 top-0 z-40 flex h-14 sm:h-16 items-center justify-between border-b border-white/[0.06] px-5 sm:px-8 lg:px-12 transition-all duration-300 ${headerScrolled
            ? "glass"
            : "bg-transparent"
          }`}
      >
        <div className="flex items-center gap-2.5">
          <Image
            src="/logo.png"
            alt="FindableAI"
            width={36}
            height={36}
            className="h-7 w-7 sm:h-9 sm:w-9 rounded-md"
            priority
          />
          <span className="text-sm sm:text-base font-bold text-[#EDEDED]">FindableAI</span>
        </div>
        <div className="flex items-center gap-4">
          <HealthIndicator />
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#A1A1A1] transition-colors hover:text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
          >
            API Docs
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-24 pt-24 sm:px-6 sm:pt-28 lg:px-8">
        {/* Hero */}
        <section className="mx-auto max-w-2xl text-center mb-12 sm:mb-20">
          <p
            className="mb-5 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium text-[#A1A1A1] animate-fade-up delay-0"
            style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
          >
            <Activity size={12} className="text-violet-400" aria-hidden="true" />
            GEO / MDO Diagnostics
          </p>

          <h1
            className="text-4xl font-extrabold leading-tight tracking-tight text-[#EDEDED] sm:text-5xl animate-fade-up delay-1"
          >
            Can AI search engines actually find your site?
          </h1>

          <p className="mt-4 sm:mt-6 text-base text-[#A1A1A1] animate-fade-up delay-2">
            Run a full discoverability audit. Get an F-Score, detect factual contradictions, and generate code fixes automatically.
          </p>

          {/* URL input form */}
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className="mt-8 sm:mt-10 animate-fade-up delay-3"
            noValidate
          >
            <div
              className="flex items-stretch overflow-hidden rounded-2xl"
              style={{
                boxShadow: urlError
                  ? "0 0 0 1px rgba(244,63,94,0.5)"
                  : "0 0 0 1px rgba(255,255,255,0.1), 0 4px 20px rgba(0,0,0,0.4)",
              }}
            >
              <div className="flex flex-1 items-center gap-3 bg-[#141414] pl-4">
                <Search
                  size={16}
                  className="shrink-0 text-[#A1A1A1]"
                  aria-hidden="true"
                />
                <input
                  id="scan-url-input"
                  data-testid="scan-url-input"
                  type="url"
                  value={url}
                  onChange={(e) => handleUrlChange(e.target.value)}
                  placeholder="https://acme.com"
                  required
                  aria-label="Website URL to audit"
                  aria-describedby={urlError ? "url-error" : undefined}
                  aria-invalid={!!urlError}
                  className="w-full bg-transparent py-4 text-sm text-[#EDEDED] placeholder-[#A1A1A1]/50 focus-visible:outline-none"
                />
              </div>
              <button
                type="submit"
                id="scan-submit"
                data-testid="scan-submit"
                disabled={submitting}
                className="shrink-0 rounded-r-2xl bg-violet-600 px-6 py-4 text-sm font-semibold text-white transition-colors hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-inset"
              >
                {submitting ? "Starting..." : "Run Audit"}
              </button>
            </div>

            {urlError && (
              <p id="url-error" role="alert" className="mt-2 text-xs text-rose-400 text-left">
                {urlError}
              </p>
            )}

            {submitError && (
              <p role="alert" className="mt-2 text-xs text-rose-400 text-left">
                {submitError}
              </p>
            )}

            {/* Advanced options */}
            <div className="mt-3 text-left">
              <button
                type="button"
                onClick={() => setAdvancedOpen((o) => !o)}
                aria-expanded={advancedOpen}
                className="flex items-center gap-1 text-xs text-[#A1A1A1] transition-colors hover:text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
              >
                {advancedOpen ? (
                  <ChevronUp size={12} aria-hidden="true" />
                ) : (
                  <ChevronDown size={12} aria-hidden="true" />
                )}
                Advanced options
              </button>

              {advancedOpen && (
                <div
                  className="mt-3 space-y-3 rounded-xl bg-[#141414] p-4"
                  style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                >
                  <div>
                    <label
                      htmlFor="max-pages"
                      className="mb-1 block text-xs font-medium text-[#A1A1A1]"
                    >
                      Max pages to crawl (1-25)
                    </label>
                    <input
                      id="max-pages"
                      type="number"
                      min={1}
                      max={25}
                      value={maxPages}
                      onChange={(e) =>
                        setMaxPages(
                          Math.min(25, Math.max(1, parseInt(e.target.value, 10) || 5))
                        )
                      }
                      className="w-24 rounded-lg bg-[#191919] px-3 py-2 text-sm text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="repo-url"
                      className="mb-1 block text-xs font-medium text-[#A1A1A1]"
                    >
                      GitHub repo URL (optional, for PR creation)
                    </label>
                    <input
                      id="repo-url"
                      type="url"
                      value={repoUrl}
                      onChange={(e) => setRepoUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="w-full rounded-lg bg-[#191919] px-3 py-2 text-sm text-[#EDEDED] placeholder-[#A1A1A1]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                    />
                  </div>
                </div>
              )}
            </div>
          </form>
        </section>

        {/* Live preview section - uses real components with sample data */}
        <section
          className="w-full mb-12 animate-fade-up delay-4"
          aria-label="Sample audit preview"
        >
          <p className="mb-4 sm:mb-6 text-center text-xs text-[#A1A1A1]">
            Sample output - what your audit looks like when complete
          </p>
          <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
            {/* Real ScoreGauge component with sample data */}
            <ScoreGauge fScore={SAMPLE_FSCORE} />

            {/* Real ScanProgress component showing a completed state */}
            <div className="space-y-4">
              <ScanProgress
                currentStatus="completed"
                latestEvent={{
                  scan_id: "scan_preview",
                  status: "completed",
                  progress_percent: 100,
                  current_step: "Audit Complete",
                  message: "Findability report and patches ready.",
                  timestamp: new Date().toISOString(),
                }}
                lastGoodStatus="completed"
              />
              {/* Stat mini-cards */}
              <div className="grid grid-cols-3 gap-3">
                {[
                  { v: "30", l: "buyer queries tested" },
                  { v: "4", l: "F-Score sub-factors" },
                  { v: "Auto", l: "opens a pull request" },
                ].map(({ v, l }) => (
                  <div
                    key={l}
                    className="rounded-xl bg-[#141414] px-3 py-3 sm:px-4 sm:py-4 text-center"
                    style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                  >
                    <p className="text-xl font-bold text-[#EDEDED]">{v}</p>
                    <p className="mt-0.5 text-[10px] text-[#A1A1A1]">{l}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Stat cards */}
        <section className="mx-auto max-w-4xl">
          <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
            <StatCard value="30" label="Synthetic buyer queries per scan" />
            <StatCard value="4" label="F-Score sub-factors analyzed" />
            <StatCard value="1-click" label="Automatic GitHub pull request" />
          </div>
        </section>
      </main>
    </div>
  );
}