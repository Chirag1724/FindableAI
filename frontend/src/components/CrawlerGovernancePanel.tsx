"use client";

import { useState, useEffect, useRef } from "react";
import {
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileCode,
  FileText,
  X,
  Bot,
  Compass,
} from "lucide-react";
import type { CrawlerGovernance, BotStatus } from "@/types/lighthouse";
import { StatusBadge } from "./StatusBadge";
import { CopyButton } from "./CopyButton";
import { useCountUp } from "@/hooks/useCountUp";
import { lighthouseTierColor, lighthouseTierStroke } from "@/lib/format";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

interface CrawlerGovernancePanelProps {
  governance: CrawlerGovernance;
}

// Recommended robots.txt configuration template
const OPTIMIZED_ROBOTS_TXT_PLACEHOLDER = `# FindableAI Recommended robots.txt
# Generated to maximize AI discovery while protecting proprietary data

# 1. Search & Citation Bots (Allowed for direct RAG citations)
User-agent: OAI-SearchBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

# 2. General Web Crawlers
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

# 3. Model Training Bots (Optional: Block if protecting training IP)
User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: Google-Extended
Disallow: /

# 4. Aggressive Scrapers & Data Harvesters (Strictly Blocked)
User-agent: CCBot
Disallow: /

User-agent: Bytespider
Disallow: /

User-agent: Diffbot
Disallow: /

# Sitemap & LLMs Manifest
Sitemap: https://yourdomain.com/sitemap.xml
# llms.txt: https://yourdomain.com/llms.txt
`;

function getBotStatusMeta(item: BotStatus) {
  const { category, status } = item;

  if (category === "search") {
    if (status === "allowed") {
      return {
        label: "Allowed",
        sublabel: "Citation Active",
        icon: <CheckCircle2 size={13} className="text-emerald-400 shrink-0" aria-hidden="true" />,
        badgeClass: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-800",
      };
    }
    return {
      label: "Blocked",
      sublabel: "Critical Risk",
      icon: <XCircle size={13} className="text-rose-400 shrink-0" aria-hidden="true" />,
      badgeClass: "bg-rose-950/60 text-rose-300 ring-1 ring-inset ring-rose-800",
    };
  }

  if (category === "scraper") {
    if (status === "blocked") {
      return {
        label: "Protected",
        sublabel: "Scraper Blocked",
        icon: <ShieldCheck size={13} className="text-emerald-400 shrink-0" aria-hidden="true" />,
        badgeClass: "bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-800",
      };
    }
    return {
      label: "Exposed",
      sublabel: "Scraping Risk",
      icon: <AlertTriangle size={13} className="text-rose-400 shrink-0" aria-hidden="true" />,
      badgeClass: "bg-rose-950/60 text-rose-300 ring-1 ring-inset ring-rose-800",
    };
  }

  // Training bot
  if (status === "allowed") {
    return {
      label: "Allowed",
      sublabel: "Model Training",
      icon: <CheckCircle2 size={13} className="text-sky-400 shrink-0" aria-hidden="true" />,
      badgeClass: "bg-sky-950/60 text-sky-300 ring-1 ring-inset ring-sky-800",
    };
  }

  return {
    label: "Blocked",
    sublabel: "Data Protected",
    icon: <ShieldCheck size={13} className="text-amber-400 shrink-0" aria-hidden="true" />,
    badgeClass: "bg-amber-950/60 text-amber-300 ring-1 ring-inset ring-amber-800",
  };
}

function getCategoryLabel(category: BotStatus["category"]) {
  switch (category) {
    case "search":
      return "Search / Citation";
    case "training":
      return "Model Training";
    case "scraper":
      return "Commercial Scraper";
  }
}

export function CrawlerGovernancePanel({ governance }: CrawlerGovernancePanelProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  const { value: animatedVisibility, ref: visibilityRef } = useCountUp(
    governance.ai_visibility_index,
    0
  );
  const visibilityColor = lighthouseTierColor(governance.ai_visibility_index);
  const visibilityStroke = lighthouseTierStroke(governance.ai_visibility_index);

  // Close modal on Escape key
  useEffect(() => {
    if (!modalOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setModalOpen(false);
    };

    window.addEventListener("keydown", handleKeyDown);
    closeBtnRef.current?.focus();

    if (modalRef.current && !prefersReducedMotion()) {
      gsap.fromTo(
        modalRef.current,
        { scale: 0.96, opacity: 0 },
        { scale: 1, opacity: 1, duration: 0.2, ease: EASING.modal }
      );
    }

    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [modalOpen]);

  return (
    <div
      data-testid="crawler-governance-panel"
      className="rounded-xl bg-surface-secondary/70 p-5 sm:p-6 shadow-border space-y-6"
    >
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/[0.08] pb-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400 ring-1 ring-sky-500/20">
            <Compass size={20} aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white tracking-tight">
              AI Crawler Governance & Access Policy
            </h2>
            <p className="text-xs text-text-muted mt-0.5">
              ML analysis of robots.txt rules, search citation access, and scraping exposure.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] border border-white/[0.08] px-3.5 py-2 text-xs font-semibold text-white transition-colors duration-150 active:scale-[0.98] self-start sm:self-auto"
        >
          <FileCode size={14} className="text-sky-400" aria-hidden="true" />
          <span>Generate Optimized robots.txt</span>
        </button>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        {/* AI Visibility Index */}
        <div className="flex items-center justify-between rounded-lg bg-black/40 border border-white/[0.06] p-4">
          <div className="space-y-1">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              AI Visibility Index
            </span>
            <div className="flex items-baseline gap-2">
              <span ref={visibilityRef} className={`font-mono text-2xl sm:text-3xl font-bold ${visibilityColor}`}>
                {animatedVisibility}
              </span>
              <span className="text-xs font-mono text-text-muted">/ 100</span>
            </div>
          </div>
          <div className="h-10 w-10 flex items-center justify-center rounded-full bg-white/[0.03] ring-1 ring-white/10">
            <Bot size={18} style={{ color: visibilityStroke }} aria-hidden="true" />
          </div>
        </div>

        {/* Scraping Risk Status */}
        <div className="flex items-center justify-between rounded-lg bg-black/40 border border-white/[0.06] p-4">
          <div className="space-y-1.5">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              Data Scraping Risk
            </span>
            <div>
              <StatusBadge status={governance.scraping_risk} />
            </div>
          </div>
          <div className="h-10 w-10 flex items-center justify-center rounded-full bg-white/[0.03] ring-1 ring-white/10">
            <ShieldCheck size={18} className="text-emerald-400" aria-hidden="true" />
          </div>
        </div>

        {/* llms.txt Status */}
        <div className="flex items-center justify-between rounded-lg bg-black/40 border border-white/[0.06] p-4">
          <div className="space-y-1.5">
            <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
              /llms.txt Standard
            </span>
            <div>
              {governance.llms_txt_present ? (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-emerald-950/60 text-emerald-300 ring-1 ring-inset ring-emerald-800">
                  <CheckCircle2 size={11} aria-hidden="true" />
                  Active Manifest
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium bg-amber-950/60 text-amber-300 ring-1 ring-inset ring-amber-800">
                  <AlertTriangle size={11} aria-hidden="true" />
                  Missing Manifest
                </span>
              )}
            </div>
          </div>
          <div className="h-10 w-10 flex items-center justify-center rounded-full bg-white/[0.03] ring-1 ring-white/10">
            <FileText size={18} className="text-text-muted" aria-hidden="true" />
          </div>
        </div>
      </div>

      {/* Bot Matrix Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
            Crawler Access Matrix ({governance.bot_matrix.length} User Agents)
          </h3>
          <span className="text-[11px] text-text-muted hidden sm:inline">
            Evaluated against root robots.txt
          </span>
        </div>

        <div className="overflow-x-auto rounded-lg border border-white/[0.08] bg-black/30">
          <table className="w-full text-left text-xs text-text-primary" role="table">
            <thead>
              <tr className="border-b border-white/[0.08] bg-white/[0.02] text-text-muted">
                <th scope="col" className="py-2.5 px-4 font-medium">User Agent (Bot)</th>
                <th scope="col" className="py-2.5 px-4 font-medium">Category</th>
                <th scope="col" className="py-2.5 px-4 font-medium">Policy Status</th>
                <th scope="col" className="py-2.5 px-4 font-medium">Impact Assessment</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {governance.bot_matrix.map((item, idx) => {
                const meta = getBotStatusMeta(item);
                return (
                  <tr
                    key={`${item.bot}-${idx}`}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="py-3 px-4 font-mono font-medium text-white">
                      {item.bot}
                    </td>
                    <td className="py-3 px-4 text-text-muted">
                      {getCategoryLabel(item.category)}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.badgeClass}`}
                      >
                        {meta.icon}
                        <span>{meta.label}</span>
                      </span>
                    </td>
                    <td className="py-3 px-4 text-text-muted font-mono text-[11px]">
                      {item.impact ? (
                        item.impact === "critical" ? (
                          <span className="text-rose-400 font-semibold">Critical Citation Drop</span>
                        ) : item.impact === "positive" ? (
                          <span className="text-emerald-400">Scraping Protected</span>
                        ) : (
                          <span>{item.impact}</span>
                        )
                      ) : (
                        <span className="text-text-muted/60">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Optimized robots.txt Modal */}
      {modalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="robots-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
          onClick={() => setModalOpen(false)}
        >
          <div
            ref={modalRef}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-2xl rounded-2xl bg-[#141414] border border-white/[0.12] p-6 shadow-2xl space-y-4 text-text-primary"
          >
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
              <div className="flex items-center gap-2.5">
                <FileCode size={18} className="text-sky-400" aria-hidden="true" />
                <h3 id="robots-modal-title" className="text-base font-semibold text-white">
                  Optimized robots.txt Configuration
                </h3>
              </div>
              <button
                ref={closeBtnRef}
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg p-1 text-text-muted hover:text-white hover:bg-white/[0.08] transition-colors"
                aria-label="Close dialog"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>

            <p className="text-xs text-text-muted leading-relaxed">
              This Pareto-optimal configuration allows search & citation crawlers (Perplexity, ChatGPT Search, Gemini, Claude Search) while restricting aggressive scrapers and preserving training IP control.
            </p>

            <div className="relative rounded-lg bg-black/60 border border-white/[0.08] p-4">
              <div className="absolute top-3 right-3">
                <CopyButton text={OPTIMIZED_ROBOTS_TXT_PLACEHOLDER} label="Copy robots.txt" />
              </div>
              <pre className="font-mono text-xs text-sky-200/90 overflow-x-auto max-h-72 whitespace-pre pr-12">
                <code>{OPTIMIZED_ROBOTS_TXT_PLACEHOLDER}</code>
              </pre>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-xs font-semibold text-white transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
