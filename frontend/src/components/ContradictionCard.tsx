"use client";

import { ExternalLink, CheckCircle } from "lucide-react";
import type { Contradiction } from "@/types/scan";
import { StatusBadge } from "./StatusBadge";
import { CopyButton } from "./CopyButton";
import { EmptyState } from "./EmptyState";

interface ContradictionCardProps {
  contradictions: Contradiction[];
}

function SingleCard({ contradiction }: { contradiction: Contradiction }) {
  return (
    <div
      id={
        contradiction.contradiction_id
          ? `contradiction-${contradiction.contradiction_id}`
          : undefined
      }
      data-testid={`contradiction-card-${contradiction.contradiction_id}`}
      className="rounded-xl bg-surface shadow-border p-4 sm:p-6 space-y-4"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-xs text-text-muted mb-1">{contradiction.entity}</p>
          <p className="text-sm font-medium text-text-primary">{contradiction.conflict}</p>
        </div>
        <StatusBadge status={contradiction.severity} />
      </div>

      {/* Conflicting values */}
      {contradiction.values.length >= 2 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {contradiction.values.slice(0, 2).map((val, i) => (
            <div
              key={i}
              className="rounded-lg bg-surface-secondary shadow-border px-3.5 py-2.5 sm:px-4 sm:py-3"
            >
              <p className="mb-1 text-[10px] font-medium text-text-muted uppercase tracking-wider">
                {i === 0 ? "Claim A" : "Claim B"}
              </p>
              <p className="text-xs text-text-primary">{String(val)}</p>
            </div>
          ))}
        </div>
      )}

      {/* Source URLs */}
      {contradiction.source_urls.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            Sources
          </p>
          <div className="space-y-1.5">
            {contradiction.source_urls.map((url) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-violet-400 font-mono underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
              >
                <ExternalLink size={11} aria-hidden="true" />
                <span className="truncate">{url}</span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* DOM paths */}
      {contradiction.dom_paths.length > 0 && (
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            DOM Paths
          </p>
          <div className="space-y-2">
            {contradiction.dom_paths.map((path) => (
              <div
                key={path}
                className="flex items-center justify-between gap-2 rounded-lg bg-surface-secondary shadow-border px-3.5 py-2"
              >
                <span className="font-mono text-xs text-text-primary break-all min-w-0">
                  {path}
                </span>
                <CopyButton text={path} label="Copy" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ContradictionCard({ contradictions }: ContradictionCardProps) {
  if (contradictions.length === 0) {
    return (
      <EmptyState
        title="No contradictions found"
        description="The scan detected no conflicting claims across the crawled pages."
        positive
        icon={<CheckCircle size={22} className="text-emerald-400" aria-hidden="true" />}
      />
    );
  }

  return (
    <div className="space-y-4 sm:space-y-5">
      {contradictions.map((c) => (
        <SingleCard key={c.contradiction_id} contradiction={c} />
      ))}
    </div>
  );
}