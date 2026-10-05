"use client";

import { useEffect, useRef } from "react";
import { X, Globe, ExternalLink, CheckCircle2, Layers, AlertCircle } from "lucide-react";
import type { CrawledPageDetail } from "@/types/scan";

interface CrawledPagesModalProps {
  isOpen: boolean;
  onClose: () => void;
  crawledPages?: CrawledPageDetail[];
  pagesCrawled: number;
  maxPagesRequested?: number;
}

export function CrawledPagesModal({
  isOpen,
  onClose,
  crawledPages = [],
  pagesCrawled,
  maxPagesRequested,
}: CrawledPagesModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    closeButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const hasFewerPagesThanRequested =
    maxPagesRequested !== undefined &&
    maxPagesRequested > 1 &&
    pagesCrawled < maxPagesRequested;

  const reachedMaxPages =
    maxPagesRequested !== undefined &&
    pagesCrawled >= maxPagesRequested;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fade-in"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="crawled-manifest-title"
    >
      <div
        ref={modalRef}
        className="relative flex flex-col w-full max-w-2xl max-h-[85vh] bg-[#0c0d12] border border-white/[0.08] rounded-xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-surface/50">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04] border border-white/[0.08] text-sky-400">
              <Globe size={16} aria-hidden="true" />
            </div>
            <div>
              <h2
                id="crawled-manifest-title"
                className="text-sm font-semibold tracking-wide text-white"
              >
                Crawl Scope Manifest
              </h2>
              <p className="text-xs text-text-muted">
                {pagesCrawled} {pagesCrawled === 1 ? "page" : "pages"} crawled
                {maxPagesRequested ? ` (Configured Scope: ${maxPagesRequested})` : ""}
              </p>
            </div>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            aria-label="Close crawl manifest"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors hover:bg-white/[0.08] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>

        {/* Scope Context Banner */}
        <div className="px-6 py-3 border-b border-white/[0.06] bg-white/[0.02]">
          {hasFewerPagesThanRequested ? (
            <div className="flex items-start gap-2.5 text-xs text-text-secondary">
              <CheckCircle2 size={15} className="text-white/60 shrink-0 mt-0.5" />
              <span>
                <strong className="text-white font-medium">Reachable domain boundary:</strong>{" "}
                FindableAI discovered and crawled all {pagesCrawled} reachable same-origin internal links on this domain. Single-page applications or focused sites naturally complete when the crawl queue is exhausted.
              </span>
            </div>
          ) : reachedMaxPages ? (
            <div className="flex items-start gap-2.5 text-xs text-text-secondary">
              <AlertCircle size={15} className="text-white/60 shrink-0 mt-0.5" />
              <span>
                <strong className="text-white font-medium">Configured scope limit:</strong>{" "}
                Crawl completed at the {maxPagesRequested}-page ceiling set in the audit configuration.
              </span>
            </div>
          ) : (
            <div className="flex items-start gap-2.5 text-xs text-text-secondary">
              <CheckCircle2 size={15} className="text-white/60 shrink-0 mt-0.5" />
              <span>
                Verified crawl manifest showing all visited routes and DOM chunks extracted.
              </span>
            </div>
          )}
        </div>

        {/* Body / Table */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3 custom-scrollbar">
          {crawledPages.length === 0 ? (
            <div className="py-8 text-center text-xs text-text-muted">
              No individual route breakdown recorded. The target root page was crawled and analyzed.
            </div>
          ) : (
            <div className="divide-y divide-white/[0.04] rounded-lg border border-white/[0.06] bg-white/[0.01] overflow-hidden">
              <div className="grid grid-cols-12 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted bg-white/[0.02]">
                <span className="col-span-8">Route & URL</span>
                <span className="col-span-2 text-center">Status</span>
                <span className="col-span-2 text-right">Chunks</span>
              </div>
              {crawledPages.map((page, idx) => {
                let pathname = "/";
                try {
                  const parsed = new URL(page.url);
                  pathname = parsed.pathname || "/";
                } catch {
                  pathname = page.url;
                }

                return (
                  <div
                    key={`${page.url}-${idx}`}
                    className="grid grid-cols-12 items-center px-4 py-3 text-xs transition-colors hover:bg-white/[0.02] gap-2"
                  >
                    <div className="col-span-8 min-w-0 pr-2">
                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[11px] text-white border border-white/[0.08] truncate max-w-[200px]">
                          {pathname === "/" ? "Home (/)" : pathname}
                        </span>
                        {page.title && (
                          <span className="text-[11px] text-text-muted truncate hidden sm:inline">
                            {page.title}
                          </span>
                        )}
                      </div>
                      <a
                        href={page.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-1 text-[11px] font-mono text-text-muted hover:text-white transition-colors truncate max-w-full"
                      >
                        <span className="truncate">{page.url}</span>
                        <ExternalLink size={10} className="shrink-0 opacity-60" />
                      </a>
                    </div>

                    <div className="col-span-2 flex justify-center">
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-medium border ${
                          page.status_code >= 200 && page.status_code < 300
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                            : page.status_code >= 300 && page.status_code < 400
                            ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                            : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                        }`}
                      >
                        {page.status_code} {page.status_code === 200 ? "OK" : ""}
                      </span>
                    </div>

                    <div className="col-span-2 text-right">
                      <div className="inline-flex items-center gap-1 text-[11px] font-mono text-text-secondary">
                        <Layers size={11} className="opacity-50" />
                        <span>{page.chunks_count}</span>
                      </div>
                      {page.load_time_ms !== undefined && page.load_time_ms > 0 && (
                        <p className="text-[10px] font-mono text-text-muted">
                          {page.load_time_ms}ms
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-6 py-3 border-t border-white/[0.08] bg-surface/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg text-xs font-medium text-white/80 bg-white/[0.05] border border-white/[0.08] hover:bg-white/[0.1] hover:text-white transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
