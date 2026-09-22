"use client";

import React, { useState } from "react";
import {
  Search,
  Sparkles,
  Cpu,
  GitPullRequest,
  ArrowUpRight,
  Zap,
} from "lucide-react";
import type { ScanResponse, ScanStatusEvent } from "@/types/scan";

export default function Home() {
  const [url, setUrl] = useState("https://findable.ai");
  const [isScanning, setIsScanning] = useState(false);
  const [currentEvent, setCurrentEvent] = useState<ScanStatusEvent | null>(null);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);

  const startScan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) return;

    setIsScanning(true);
    setScanResult(null);
    setCurrentEvent({
      scan_id: "scan_init",
      status: "pending",
      progress_percent: 5,
      current_step: "Initializing Scan",
      message: "Connecting to FindableAI crawl dispatcher...",
      timestamp: new Date().toISOString(),
    });

    try {
      // 1. Trigger scan creation
      const res = await fetch("/api/v1/scans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, max_pages: 5, personas: ["cto", "developer", "procurement"] }),
      });
      const data = await res.json();
      const scanId = data.scan_id || "scan_demo";

      // 2. Open SSE stream
      const eventSource = new EventSource(`/api/v1/scans/${scanId}/stream`);

      eventSource.onmessage = (event) => {
        try {
          const payload: ScanStatusEvent = JSON.parse(event.data);
          setCurrentEvent(payload);

          if (payload.status === "completed") {
            eventSource.close();
            setIsScanning(false);
            // Fetch final completed scan record
            fetch(`/api/v1/scans/${scanId}`)
              .then((r) => r.json())
              .then((finalData) => setScanResult(finalData))
              .catch(console.error);
          }
        } catch (err) {
          console.error("SSE parse error:", err);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        setIsScanning(false);
      };
    } catch (err) {
      console.error("Failed to start scan:", err);
      setIsScanning(false);
    }
  };

  return (
    <main className="relative min-h-screen px-4 py-8 md:px-12 lg:px-24">
      {/* Background glow accents */}
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[500px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-tr from-brandIndigo/20 via-brandCyan/10 to-transparent blur-3xl" />

      {/* Top Navbar */}
      <header className="relative z-10 mb-12 flex items-center justify-between border-b border-gray-800/80 pb-6">
        <div className="flex items-center space-x-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-brandCyan via-brandIndigo to-brandPurple p-[1px]">
            <div className="flex h-full w-full items-center justify-center rounded-xl bg-surface">
              <Sparkles className="h-5 w-5 text-brandCyan" />
            </div>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">FindableAI</h1>
            <p className="text-xs text-gray-400">Machine-Discoverability Optimization</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400 border border-emerald-500/20">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            API Core v0.1.0 Ready
          </span>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="text-xs text-gray-400 hover:text-brandCyan transition"
          >
            FastAPI Docs &rarr;
          </a>
        </div>
      </header>

      {/* Hero / Input Section */}
      <section className="relative z-10 mx-auto max-w-3xl text-center mb-12">
        <div className="inline-flex items-center gap-2 rounded-full border border-brandIndigo/30 bg-brandIndigo/10 px-4 py-1.5 text-xs text-indigo-300 mb-6">
          <Zap className="h-3.5 w-3.5 text-brandCyan" />
          GEO / MDO Diagnostics for Perplexity, SearchGPT & Gemini
        </div>

        <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-4">
          How Visible Is Your Product to{" "}
          <span className="bg-gradient-to-r from-brandCyan via-indigo-400 to-brandPurple bg-clip-text text-transparent">
            AI Search Engines?
          </span>
        </h2>
        <p className="text-sm md:text-base text-gray-400 mb-8 max-w-xl mx-auto">
          Audit semantic clarity, compute your factual F-Score, and generate zero-hallucination code remediations autonomously.
        </p>

        {/* Scan Input Form */}
        <form onSubmit={startScan} className="mx-auto flex max-w-2xl items-center gap-2 rounded-2xl glass-panel-glow p-2">
          <div className="flex flex-1 items-center gap-3 px-3">
            <Search className="h-5 w-5 text-gray-400" />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://yourcompany.com"
              required
              className="w-full bg-transparent text-sm text-white placeholder-gray-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={isScanning}
            className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-brandCyan via-brandIndigo to-brandPurple px-6 py-3 text-sm font-semibold text-white shadow-lg transition hover:opacity-90 disabled:opacity-50"
          >
            {isScanning ? (
              <>
                <Cpu className="h-4 w-4 animate-spin" />
                Auditing...
              </>
            ) : (
              <>
                <span>Run Audit</span>
                <ArrowUpRight className="h-4 w-4" />
              </>
            )}
          </button>
        </form>
      </section>

      {/* Live SSE Progress Indicator */}
      {currentEvent && (
        <section className="relative z-10 mx-auto max-w-2xl mb-12 glass-panel rounded-2xl p-6 border border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-brandCyan animate-ping" />
              <span className="text-xs font-semibold uppercase tracking-wider text-brandCyan">
                {currentEvent.current_step}
              </span>
            </div>
            <span className="text-xs font-mono text-gray-400">{currentEvent.progress_percent}%</span>
          </div>

          {/* Progress bar */}
          <div className="h-2 w-full overflow-hidden rounded-full bg-surfaceLight mb-3">
            <div
              className="h-full bg-gradient-to-r from-brandCyan to-brandPurple transition-all duration-500 ease-out"
              style={{ width: `${currentEvent.progress_percent}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 font-mono">{currentEvent.message}</p>
        </section>
      )}

      {/* Results Dashboard (F-Score & Patches) */}
      {scanResult?.f_score && (
        <section className="relative z-10 mx-auto max-w-5xl space-y-8">
          {/* Top Score Banner */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="glass-panel-glow rounded-2xl p-6 text-center">
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Findability F-Score</p>
              <div className="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-brandCyan to-brandPurple">
                {scanResult.f_score.overall_score.toFixed(1)}
              </div>
              <span className="mt-2 inline-block rounded-md bg-brandIndigo/20 px-2.5 py-0.5 text-xs font-semibold text-brandCyan">
                Grade: {scanResult.f_score.grade}
              </span>
            </div>

            <div className="glass-panel rounded-2xl p-6">
              <p className="text-xs text-gray-400 mb-1">Query Coverage (40%)</p>
              <div className="text-2xl font-bold text-white">{scanResult.f_score.coverage.score.toFixed(1)}%</div>
              <p className="text-xs text-gray-400 mt-2">{scanResult.f_score.coverage.details}</p>
            </div>

            <div className="glass-panel rounded-2xl p-6">
              <p className="text-xs text-gray-400 mb-1">Entailment Grounding (35%)</p>
              <div className="text-2xl font-bold text-emerald-400">{scanResult.f_score.entailment.score.toFixed(1)}%</div>
              <p className="text-xs text-gray-400 mt-2">{scanResult.f_score.entailment.details}</p>
            </div>

            <div className="glass-panel rounded-2xl p-6">
              <p className="text-xs text-gray-400 mb-1">Contradiction Penalty (15%)</p>
              <div className="text-2xl font-bold text-rose-400">-{scanResult.f_score.contradiction_penalty.score.toFixed(1)}%</div>
              <p className="text-xs text-gray-400 mt-2">{scanResult.f_score.contradiction_penalty.details}</p>
            </div>
          </div>

          {/* Autonomous Remediation Patches */}
          <div className="glass-panel rounded-2xl p-6 border border-gray-800">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-bold text-white flex items-center gap-2">
                  <GitPullRequest className="h-5 w-5 text-brandCyan" />
                  Proposed Zero-Hallucination Code Patches
                </h3>
                <p className="text-xs text-gray-400">
                  DOM-anchored diffs synthesized to resolve discoverability bottlenecks.
                </p>
              </div>
              <span className="rounded-full bg-brandCyan/10 px-3 py-1 text-xs font-semibold text-brandCyan">
                {scanResult.patches.length} Patches Ready
              </span>
            </div>

            <div className="space-y-4">
              {scanResult.patches.map((patch) => (
                <div key={patch.patch_id} className="rounded-xl border border-gray-800 bg-surface/80 p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <span className="inline-block rounded bg-indigo-900/40 px-2 py-0.5 text-[10px] font-mono font-semibold text-indigo-300 uppercase tracking-wider mb-1">
                        {patch.patch_type}
                      </span>
                      <h4 className="text-sm font-semibold text-white">{patch.title}</h4>
                      <p className="text-xs text-gray-400 mt-1">{patch.rationale}</p>
                    </div>
                    <span className="text-xs font-mono text-emerald-400">+{patch.impact_score_delta} F-Score</span>
                  </div>

                  {/* Code Diff Display */}
                  <div className="rounded-lg bg-black/70 p-3 font-mono text-xs overflow-x-auto text-gray-300 border border-gray-800/80">
                    <pre>{patch.unified_diff}</pre>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </main>
  );
}
