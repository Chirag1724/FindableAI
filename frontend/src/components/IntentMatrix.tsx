"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, ArrowUpDown } from "lucide-react";
import type { IntentEvaluation, EntailmentStatus, EvidenceReference } from "@/types/scan";
import { StatusBadge } from "./StatusBadge";
import { EvidenceViewer } from "./EvidenceViewer";
import { EmptyState } from "./EmptyState";

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
    SUPPORTED: "bg-emerald-950 text-emerald-300 ring-emerald-800",
    PARTIALLY_SUPPORTED: "bg-sky-950 text-sky-300 ring-sky-800",
    CONTRADICTED: "bg-rose-950 text-rose-300 ring-rose-800",
    UNKNOWN: "bg-amber-950 text-amber-300 ring-amber-800",
  };
  const labels: Record<EntailmentStatus, string> = {
    SUPPORTED: "Supported",
    PARTIALLY_SUPPORTED: "Partial",
    CONTRADICTED: "Contradicted",
    UNKNOWN: "Unknown",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${colors[status]}`}
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

  return (
    <div className="space-y-3 sm:space-y-4 px-4 sm:px-5 pb-4 sm:pb-5 pt-2 sm:pt-3 text-xs">
      {/* Reasoning */}
      <div>
        <p className="mb-1 font-medium text-[#A1A1A1]">Reasoning</p>
        <p className="text-[#EDEDED]">{intent.reasoning}</p>
      </div>

      {/* Confidence bar */}
      <div>
        <p className="mb-1 font-medium text-[#A1A1A1]">
          Confidence: {(intent.confidence * 100).toFixed(0)}%
        </p>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
          <div
            className="h-full rounded-full bg-violet-500"
            style={{ width: `${intent.confidence * 100}%` }}
          />
        </div>
      </div>

      {/* Evidence */}
      {intent.evidence.length > 0 && (
        <div>
          <p className="mb-2 font-medium text-[#A1A1A1]">Evidence ({intent.evidence.length})</p>
          <div className="space-y-1">
            {intent.evidence.map((ev, i) => (
              <button
                key={ev.chunk_id}
                ref={i === 0 ? (btnRef as React.RefObject<HTMLButtonElement>) : undefined}
                type="button"
                onClick={() => onEvidenceOpen(ev, btnRef as React.RefObject<HTMLElement>)}
                className="flex w-full items-start gap-2 rounded-lg bg-[#191919] px-3 py-2 text-left transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                <span className="mt-0.5 shrink-0 font-mono text-[10px] text-[#A1A1A1]">
                  #{ev.rank ?? i + 1}
                </span>
                <span className="font-mono text-[#EDEDED] break-all">{ev.dom_path}</span>
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
          className="min-w-[180px] flex-1 rounded-lg bg-[#191919] px-3 py-2 text-sm text-[#EDEDED] placeholder-[#A1A1A1] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
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
                className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${active
                    ? "bg-violet-600 text-white"
                    : "bg-[#191919] text-[#A1A1A1] hover:text-[#EDEDED]"
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
            className="rounded-lg bg-[#191919] px-3 py-2 text-sm text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
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
      <div
        className="rounded-2xl overflow-x-auto"
        style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
      >
        {sorted.length === 0 ? (
          <div className="bg-[#141414] px-4 py-10 text-center text-sm text-[#A1A1A1]">
            No intents match the current filters.
          </div>
        ) : (
          <table className="w-full min-w-[560px] sm:min-w-full table-fixed bg-[#141414] text-sm">
            <thead>
              <tr className="border-b border-white/5 text-left">
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
                    className="px-4 py-3 sm:py-4"
                  >
                    <button
                      type="button"
                      onClick={() => toggleSort(key)}
                      className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-[#A1A1A1] transition-colors hover:text-[#EDEDED] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded"
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
                  <>
                    <tr
                      key={intent.intent_id}
                      data-testid={`intent-row-${intent.intent_id}`}
                      className="border-b border-white/5 last:border-0 cursor-pointer transition-colors hover:bg-white/[0.03]"
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
                      <td className="px-4 py-3 sm:py-4">
                        <span className="rounded-md bg-[#191919] px-1.5 py-0.5 font-mono text-[10px] text-[#A1A1A1]">
                          {intent.category}
                        </span>
                      </td>
                      <td className="px-4 py-3 sm:py-4 text-[#EDEDED]">
                        <div className="flex items-center gap-2">
                          <span className="line-clamp-2 text-sm leading-normal">
                            {intent.query}
                          </span>
                          {isExpanded ? (
                            <ChevronUp size={12} className="text-[#A1A1A1] shrink-0" aria-hidden="true" />
                          ) : (
                            <ChevronDown size={12} className="text-[#A1A1A1] shrink-0" aria-hidden="true" />
                          )}
                        </div>
                      </td>
                      <td
                        className="px-4 py-3 sm:py-4"
                        data-testid={`intent-status-${intent.intent_id}`}
                      >
                        <StatusBadge status={intent.status} />
                      </td>
                      <td className="px-4 py-3 sm:py-4 font-mono text-xs text-[#A1A1A1]">
                        {(intent.confidence * 100).toFixed(0)}%
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr
                        key={`${intent.intent_id}-expanded`}
                        className="border-b border-white/5 bg-[#191919]/50"
                      >
                        <td colSpan={4} className="p-0">
                          <ExpandedRow
                            intent={intent}
                            onEvidenceOpen={(ev, ref) =>
                              setEvidenceOpen({ ev, ref })
                            }
                          />
                        </td>
                      </tr>
                    )}
                  </>
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