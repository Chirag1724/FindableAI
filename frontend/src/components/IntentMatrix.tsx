"use client";

import { useMemo, useRef, useState, useEffect } from "react";
import { ChevronDown, ChevronUp, ArrowUpDown } from "lucide-react";
import type { IntentEvaluation, EntailmentStatus, EvidenceReference } from "@/types/scan";
import { StatusBadge } from "./StatusBadge";
import { EvidenceViewer } from "./EvidenceViewer";
import { EmptyState } from "./EmptyState";
import { gsap, EASING, prefersReducedMotion } from "@/lib/motion";

type SortKey = "query" | "category" | "status" | "confidence";
type SortDir = "asc" | "desc";

const STATUS_ORDER: Record<EntailmentStatus, number> = {
  SUPPORTED: 0,
  PARTIALLY_SUPPORTED: 1,
  UNKNOWN: 2,
  CONTRADICTED: 3,
};

interface IntentMatrixProps {
  intents: IntentEvaluation[];
}

function StatusChip({ status, count }: { status: EntailmentStatus; count: number }) {
  const colors: Record<EntailmentStatus, string> = {
    SUPPORTED: "bg-emerald-950/60 text-emerald-300 border border-emerald-800/40",
    PARTIALLY_SUPPORTED: "bg-sky-950/60 text-sky-300 border border-sky-800/40",
    CONTRADICTED: "bg-rose-950/60 text-rose-300 border border-rose-800/40",
    UNKNOWN: "bg-amber-950/60 text-amber-300 border border-amber-800/40",
  };
  const labels: Record<EntailmentStatus, string> = {
    SUPPORTED: "Supported",
    PARTIALLY_SUPPORTED: "Partial",
    CONTRADICTED: "Contradicted",
    UNKNOWN: "Unknown",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[status]}`}
    >
      {labels[status]}: {count}
    </span>
  );
}

interface ExpandedRowProps {
  intent: IntentEvaluation;
  onEvidenceOpen: (ev: EvidenceReference, ref: React.RefObject<HTMLElement>) => void;
}

function ExpandedRow({ intent, onEvidenceOpen }: ExpandedRowProps) {
  const btnRef = useRef<HTMLButtonElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!rowRef.current || prefersReducedMotion()) return;

    gsap.fromTo(
      rowRef.current,
      { height: 0, opacity: 0 },
      { height: "auto", opacity: 1, duration: 0.2, ease: EASING.expand }
    );
  }, []);

  return (
    <div ref={rowRef} className="space-y-3 sm:space-y-4 px-4 sm:px-5 pb-4 sm:pb-5 pt-2 sm:pt-3 text-xs overflow-hidden">
      {/* Reasoning */}
      <div>
        <p className="mb-1 font-medium text-text-muted">Reasoning</p>
        <p className="text-text-primary leading-relaxed">{intent.reasoning}</p>
      </div>

      {/* Confidence bar */}
      <div>
        <p className="mb-1 font-medium text-text-muted">
          Confidence: {(intent.confidence * 100).toFixed(0)}%
        </p>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full rounded-full bg-violet-500 transition-all duration-300"
            style={{ width: `${intent.confidence * 100}%` }}
          />
        </div>
      </div>

      {/* Evidence */}
      {intent.evidence.length > 0 && (
        <div>
          <p className="mb-2 font-medium text-text-muted">Evidence ({intent.evidence.length})</p>
          <div className="space-y-1.5">
            {intent.evidence.map((ev, i) => (
              <button
                key={ev.chunk_id}
                ref={i === 0 ? (btnRef as React.RefObject<HTMLButtonElement>) : undefined}
                type="button"
                onClick={() => onEvidenceOpen(ev, btnRef as React.RefObject<HTMLElement>)}
                className="flex w-full items-start gap-2 rounded-lg bg-surface px-3 py-2 text-left shadow-border transition-colors duration-150 hover:bg-surface-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <span className="mt-0.5 shrink-0 font-mono text-[10px] text-text-muted">
                  #{ev.rank ?? i + 1}
                </span>
                <span className="font-mono text-text-primary break-all text-xs">{ev.dom_path}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function IntentMatrix({ intents }: IntentMatrixProps) {
  const [search, setSearch] = useState("");
  const [statusFilters, setStatusFilters] = useState<Set<EntailmentStatus>>(new Set());
  const [categoryFilter, setCategoryFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("status");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState<{
    ev: EvidenceReference;
    ref: React.RefObject<HTMLElement>;
  } | null>(null);

  const allStatuses: EntailmentStatus[] = [
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "CONTRADICTED",
    "UNKNOWN",
  ];

  const statusCounts = useMemo((): Record<EntailmentStatus, number> => {
    const counts = { SUPPORTED: 0, PARTIALLY_SUPPORTED: 0, CONTRADICTED: 0, UNKNOWN: 0 };
    for (const intent of intents) {
      counts[intent.status] = (counts[intent.status] ?? 0) + 1;
    }
    return counts;
  }, [intents]);

  const categories = useMemo(() => {
    const cats = new Set(intents.map((i) => i.category));
    return Array.from(cats).sort();
  }, [intents]);

  const filtered = useMemo(() => {
    let result = intents;
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (i) =>
          i.query.toLowerCase().includes(q) ||
          i.category.toLowerCase().includes(q) ||
          i.reasoning.toLowerCase().includes(q)
      );
    }
    if (statusFilters.size > 0) {
      result = result.filter((i) => statusFilters.has(i.status));
    }
    if (categoryFilter) {
      result = result.filter((i) => i.category === categoryFilter);
    }
    return result;
  }, [intents, search, statusFilters, categoryFilter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "query":
          cmp = a.query.localeCompare(b.query);
          break;
        case "category":
          cmp = a.category.localeCompare(b.category);
          break;
        case "status":
          cmp = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
          break;
        case "confidence":
          cmp = a.confidence - b.confidence;
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [filtered, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const toggleStatus = (s: EntailmentStatus) => {
    setStatusFilters((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  const ariaSortAttr = (key: SortKey): React.AriaAttributes["aria-sort"] => {
    if (sortKey !== key) return "none";
    return sortDir === "asc" ? "ascending" : "descending";
  };

  if (intents.length === 0) {
    return (
      <EmptyState
        title="No intent evaluations"
        description="The backend returned no intent data for this scan."
      />
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary chips */}
      <div className="flex flex-wrap gap-2">
        {allStatuses.map((s) =>
          statusCounts[s] > 0 ? (
            <StatusChip key={s} status={s} count={statusCounts[s]} />
          ) : null
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search intents..."
          aria-label="Search intent queries"
          className="min-w-[180px] flex-1 rounded-lg bg-surface-secondary px-3 py-2 text-sm text-text-primary placeholder-text-muted/60 shadow-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
        />

        <div
          className="flex flex-wrap gap-1"
          data-testid="status-filter"
          role="group"
          aria-label="Filter by status"
        >
          {allStatuses.map((s) => {
            const active = statusFilters.has(s);
            const labels: Record<EntailmentStatus, string> = {
              SUPPORTED: "Supported",
              PARTIALLY_SUPPORTED: "Partial",
              CONTRADICTED: "Contradicted",
              UNKNOWN: "Unknown",
            };
            return (
              <button
                key={s}
                type="button"
                onClick={() => toggleStatus(s)}
                aria-pressed={active}
                className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                  active
                    ? "bg-white text-black font-semibold shadow-sm"
                    : "bg-surface-secondary text-text-muted shadow-border hover:text-text-primary hover:bg-surface-tertiary"
                }`}
              >
                {labels[s]}
              </button>
            );
          })}
        </div>

        {categories.length > 1 && (
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            aria-label="Filter by category"
            className="rounded-lg bg-surface-secondary px-3 py-2 text-sm text-text-primary shadow-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Table */}
      <div className="rounded-xl bg-surface shadow-border overflow-x-auto custom-scrollbar">
        {sorted.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-text-muted">
            No intents match the current filters.
          </div>
        ) : (
          <table className="w-full min-w-[560px] sm:min-w-full table-fixed text-sm">
            <thead>
              <tr className="border-b border-white/[0.06] text-left">
                {(
                  [
                    { key: "category" as SortKey, label: "Category", width: "18%" },
                    { key: "query" as SortKey, label: "Query", width: "50%" },
                    { key: "status" as SortKey, label: "Status", width: "18%" },
                    { key: "confidence" as SortKey, label: "Conf.", width: "14%" },
                  ] as { key: SortKey; label: string; width: string }[]
                ).map(({ key, label, width }) => (
                  <th
                    key={key}
                    scope="col"
                    aria-sort={ariaSortAttr(key)}
                    style={{ width }}
                    className="px-4 py-3 sm:py-3.5"
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(key)}
                      className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-text-muted transition-colors duration-150 hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
                    >
                      {label}
                      <ArrowUpDown size={10} aria-hidden="true" />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((intent) => {
                const isExpanded = expandedId === intent.intent_id;
                return (
                  <tr
                    key={intent.intent_id}
                    data-testid={`intent-row-${intent.intent_id}`}
                    className="border-b border-white/[0.04] last:border-0 cursor-pointer transition-colors duration-150 hover:bg-white/[0.02]"
                    onClick={() =>
                      setExpandedId(isExpanded ? null : intent.intent_id)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpandedId(isExpanded ? null : intent.intent_id);
                      }
                    }}
                    tabIndex={0}
                    role="row"
                    aria-expanded={isExpanded}
                  >
                    <td colSpan={4} className="p-0">
                      <div className="grid grid-cols-12 items-center px-4 py-3 sm:py-3.5">
                        <div className="col-span-2">
                          <span className="rounded-md bg-surface-secondary shadow-border px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
                            {intent.category}
                          </span>
                        </div>
                        <div className="col-span-6 text-text-primary pr-2">
                          <div className="flex items-center gap-2">
                            <span className="line-clamp-2 text-sm leading-normal">
                              {intent.query}
                            </span>
                            {isExpanded ? (
                              <ChevronUp size={12} className="text-text-muted shrink-0" aria-hidden="true" />
                            ) : (
                              <ChevronDown size={12} className="text-text-muted shrink-0" aria-hidden="true" />
                            )}
                          </div>
                        </div>
                        <div
                          className="col-span-2"
                          data-testid={`intent-status-${intent.intent_id}`}
                        >
                          <StatusBadge status={intent.status} />
                        </div>
                        <div className="col-span-2 font-mono text-xs text-text-muted text-right">
                          {(intent.confidence * 100).toFixed(0)}%
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="border-t border-white/[0.04] bg-surface-secondary/40">
                          <ExpandedRow
                            intent={intent}
                            onEvidenceOpen={(ev, ref) =>
                              setEvidenceOpen({ ev, ref })
                            }
                          />
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Evidence viewer slide-over */}
      {evidenceOpen && (
        <EvidenceViewer
          evidence={evidenceOpen.ev}
          onClose={() => setEvidenceOpen(null)}
          triggerRef={evidenceOpen.ref}
        />
      )}
    </div>
  );
}