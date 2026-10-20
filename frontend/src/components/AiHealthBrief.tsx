"use client";

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Sparkles,
  FileSearch,
  AlertCircle,
  Clock3,
  ChevronDown,
  Search,
  Lightbulb,
  HelpCircle,
  ListChecks,
  Info,
  ArrowRight,
  type LucideIcon,
} from "lucide-react";
import { generateScanSummary, getScanSummary } from "@/lib/api";
import type {
  ApiError,
  FactStatement,
  NextStepStatement,
  ScanSummaryResponse,
  SummaryPriority,
  SummaryVerdict,
} from "@/types/scan";
import { formatRelativeTime } from "@/lib/format";
import { ErrorState } from "./ErrorState";

type AccordionSectionId =
  | "found"
  | "matters"
  | "gaps"
  | "actions"
  | "notes";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 60_000;

export interface AiHealthBriefProps {
  scanId: string;
  scanStatus: string;
  outcome?: string | null;
  jobStatus?: string | null;
  /** When true, only render the panel (control lives in the tab row). */
  panelOnly?: boolean;
  /** Controlled open state from the tab-row toggle. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Fire generate once after mount/open (from tab control). */
  autoGenerate?: boolean;
  onAutoGenerateConsumed?: () => void;
  onBusyChange?: (busy: boolean) => void;
  /** Called when GET restores a ready summary so the parent can open the panel. */
  onRestoredReady?: () => void;
}

type ViewState =
  | "loading"
  | "idle"
  | "generating"
  | "ready"
  | "ineligible"
  | "rate_limited"
  | "error";

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort);
  });
}

function localIneligibleMessage(
  scanStatus: string,
  outcome?: string | null,
  jobStatus?: string | null
): string | null {
  const status = (scanStatus || "").trim().toLowerCase();
  const out = (outcome || "").trim().toLowerCase();
  const job = (jobStatus || "").trim().toLowerCase();

  if (status === "cancelled" || status === "cancelling") {
    return "Scan was cancelled; summary is unavailable.";
  }
  if (status === "failed" || out === "failed") {
    return "Scan failed; summary is unavailable.";
  }
  if (
    job === "queued" ||
    job === "claimed" ||
    job === "running" ||
    job === "retry_scheduled" ||
    status === "pending"
  ) {
    return "Scan is still queued or running; summary is available after completion.";
  }
  const running = new Set([
    "crawling",
    "extracting_dom",
    "audited",
    "synthesizing_intents",
    "hybrid_retrieval",
    "nli_evaluation",
    "computing_fscore",
    "generating_patches",
  ]);
  if (running.has(status) || out === "inconclusive") {
    return "Scan is incomplete; summary is unavailable until a conclusive audit finishes.";
  }
  return null;
}

function verdictLabel(v: SummaryVerdict): string {
  switch (v) {
    case "scan_incomplete":
      return "Scan incomplete";
    case "insufficient_evidence":
      return "Needs more evidence";
    case "issues_found":
      return "Issues found";
    case "no_confirmed_issues":
      return "No confirmed issues";
    default:
      return v;
  }
}

function verdictHint(v: SummaryVerdict): string {
  switch (v) {
    case "scan_incomplete":
      return "This audit did not finish cleanly — treat results as partial.";
    case "insufficient_evidence":
      return "Checks ran, but the site did not provide enough verified content to confirm claims.";
    case "issues_found":
      return "At least one check found conflicting or incomplete information.";
    case "no_confirmed_issues":
      return "Verified checks did not surface confirmed problems. Unverified checks are not a pass.";
    default:
      return "";
  }
}

/** Verdict accents use the same semantic status palette as the rest of the app. */
function verdictTone(v?: SummaryVerdict | null): {
  rail: string;
  text: string;
  glow: string;
  hairline: string;
} {
  switch (v) {
    case "issues_found":
      return {
        rail: "bg-rose-400",
        text: "text-rose-300",
        glow: "bg-gradient-to-br from-rose-500/10 via-transparent to-transparent",
        hairline: "bg-gradient-to-r from-rose-400/60 via-rose-400/15 to-transparent",
      };
    case "insufficient_evidence":
    case "scan_incomplete":
      return {
        rail: "bg-amber-400",
        text: "text-amber-200",
        glow: "bg-gradient-to-br from-amber-500/10 via-transparent to-transparent",
        hairline: "bg-gradient-to-r from-amber-400/60 via-amber-400/15 to-transparent",
      };
    case "no_confirmed_issues":
      return {
        rail: "bg-emerald-400",
        text: "text-emerald-300",
        glow: "bg-gradient-to-br from-emerald-500/10 via-transparent to-transparent",
        hairline: "bg-gradient-to-r from-emerald-400/60 via-emerald-400/15 to-transparent",
      };
    default:
      return {
        rail: "bg-white/30",
        text: "text-text-muted",
        glow: "bg-gradient-to-br from-white/[0.06] via-transparent to-transparent",
        hairline: "bg-gradient-to-r from-white/40 via-white/10 to-transparent",
      };
  }
}

function priorityTone(p: SummaryPriority): { dot: string; text: string; chip: string } {
  if (p === "high")
    return {
      dot: "bg-rose-400",
      text: "text-rose-300",
      chip: "border border-rose-500/30 bg-rose-500/10",
    };
  if (p === "medium")
    return {
      dot: "bg-amber-400",
      text: "text-amber-200",
      chip: "border border-amber-500/30 bg-amber-500/10",
    };
  return {
    dot: "bg-sky-400",
    text: "text-sky-300",
    chip: "border border-sky-500/30 bg-sky-500/10",
  };
}

function priorityLabel(p: SummaryPriority): string {
  if (p === "high") return "Do first";
  if (p === "medium") return "Soon";
  return "Later";
}

function factAnchor(factId: string): string | null {
  if (factId.startsWith("I_")) return `#intent-${factId.slice(2)}`;
  if (factId.startsWith("C_")) return `#contradiction-${factId.slice(2)}`;
  if (factId.startsWith("S_")) return "#panel-overview";
  if (factId.startsWith("L_")) return "#panel-lighthouse";
  return null;
}

function factLabel(fid: string): string {
  if (fid.startsWith("I_")) return `Check ${fid.slice(2)}`;
  if (fid.startsWith("E_")) return "Evidence";
  if (fid.startsWith("F_")) return "Crawl";
  if (fid.startsWith("S_")) return "Score";
  if (fid.startsWith("L_")) return "Lighthouse";
  if (fid.startsWith("R_")) return "Remediation";
  return fid;
}

/** Presentation-only wording — does not invent findings. */
function humanizeCopy(text: string): string {
  return text
    .replace(/\bUNKNOWN\b/g, "could not be verified")
    .replace(/\bUnknown\b/g, "could not be verified")
    .replace(/\bDOM chunks?\b/gi, "readable page content")
    .replace(/\bintents?\b/gi, "site checks")
    .replace(/\bNLI\b/g, "claim checks")
    .trim();
}

function previewText(text: string, max = 96): string {
  const clean = humanizeCopy(text).replace(/\s+/g, " ");
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max - 1).trimEnd()}…`;
}

/** Small uppercase label used for eyebrows and meta rows. */
const EYEBROW =
  "text-[10px] font-semibold uppercase tracking-wider text-text-muted";

/** Footnote-style source references: quiet text links, not chips. */
function FactLinks({ factIds }: { factIds?: string[] }) {
  if (!factIds?.length) return null;
  return (
    <p className="mt-2.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-xs text-text-muted">
      <span>Based on</span>
      {factIds.map((fid, i) => {
        const href = factAnchor(fid);
        const sep = i < factIds.length - 1 ? "," : "";
        return (
          <span key={fid} className="inline-flex items-baseline">
            {href ? (
              <a
                href={href}
                title={fid}
                className="rounded text-violet-400 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                {factLabel(fid)}
              </a>
            ) : (
              <span title={fid}>{factLabel(fid)}</span>
            )}
            {sep}
          </span>
        );
      })}
    </p>
  );
}

function StatementBullets({
  items,
  testId,
}: {
  items: FactStatement[];
  testId: string;
}) {
  if (!items.length) return null;
  return (
    <ul data-testid={testId} className="space-y-5">
      {items.map((item, idx) => (
        <li
          key={`${testId}-${idx}`}
          className="relative pl-5 text-sm text-text-primary leading-relaxed"
        >
          <span
            aria-hidden="true"
            className="absolute left-0 top-[0.85em] h-px w-2.5 bg-white/25"
          />
          <p className="break-words whitespace-pre-wrap">{humanizeCopy(item.text)}</p>
          <FactLinks factIds={item.fact_ids} />
        </li>
      ))}
    </ul>
  );
}

/** Next steps are a real sequence, so they get a timeline. */
function NextStepBullets({ items }: { items: NextStepStatement[] }) {
  if (!items.length) return null;
  return (
    <ol
      data-testid="ai-health-brief-next-steps"
      className="relative ml-[5px] space-y-6 border-l border-white/[0.08]"
    >
      {items.map((item, idx) => {
        const tone = priorityTone(item.priority);
        return (
          <li key={`next-${idx}`} className="relative pl-6">
            <span
              aria-hidden="true"
              className={`absolute -left-[4.5px] top-[7px] h-2 w-2 rounded-full ring-[5px] ring-surface ${tone.dot}`}
            />
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tone.chip} ${tone.text}`}
            >
              {priorityLabel(item.priority)}
            </span>
            <p className="mt-2 text-sm text-text-primary leading-relaxed break-words whitespace-pre-wrap">
              {humanizeCopy(item.text)}
            </p>
            <FactLinks factIds={item.fact_ids} />
          </li>
        );
      })}
    </ol>
  );
}

function AccordionRow({
  id,
  title,
  preview,
  count,
  icon: Icon,
  open,
  onToggle,
  children,
  testId,
}: {
  id: AccordionSectionId;
  title: string;
  preview: string;
  count?: number;
  icon: LucideIcon;
  open: boolean;
  onToggle: (id: AccordionSectionId) => void;
  children: ReactNode;
  testId: string;
}) {
  const panelId = useId();
  const buttonId = useId();

  return (
    <div
      data-testid={testId}
      data-accordion-section={id}
      data-open={open ? "true" : "false"}
      className={`relative border-b border-white/[0.06] last:border-b-0 transition-colors duration-150 motion-reduce:transition-none ${
        open ? "bg-white/[0.018]" : ""
      }`}
    >
      {/* Active-row marker */}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute left-0 top-0 h-full w-px bg-gradient-to-b from-white/50 via-white/20 to-transparent transition-opacity duration-150 motion-reduce:transition-none ${
          open ? "opacity-100" : "opacity-0"
        }`}
      />
      <button
        type="button"
        id={buttonId}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onToggle(id)}
        className="group w-full flex items-center gap-3.5 px-5 sm:px-7 py-4 text-left transition-colors duration-150 hover:bg-white/[0.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500 motion-reduce:transition-none"
      >
        <span
          aria-hidden="true"
          className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ring-1 ring-inset transition-colors duration-150 motion-reduce:transition-none ${
            open
              ? "bg-white/[0.08] ring-white/20 text-text-primary"
              : "bg-white/[0.03] ring-white/[0.07] text-text-muted group-hover:text-text-primary group-hover:ring-white/15"
          }`}
        >
          <Icon size={14} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium tracking-tight text-text-primary">
            {title}
          </span>
          {!open && preview && (
            <span className="mt-0.5 block text-xs text-text-muted leading-snug line-clamp-1">
              {preview}
            </span>
          )}
        </span>
        {typeof count === "number" && count > 0 && (
          <span className="shrink-0 rounded-full bg-white/[0.05] px-2 py-0.5 text-xs font-medium tabular-nums text-text-muted">
            {count}
          </span>
        )}
        <ChevronDown
          size={15}
          aria-hidden="true"
          className={`shrink-0 text-text-muted transition-transform duration-150 ease-out motion-reduce:transition-none ${
            open ? "rotate-180 text-text-primary" : "group-hover:text-text-primary"
          }`}
        />
      </button>
      <div
        id={panelId}
        role="region"
        aria-labelledby={buttonId}
        hidden={!open}
        className={open ? "px-5 sm:px-7 pb-6" : undefined}
      >
        {open && (
          <div className="ml-[42px] pt-1.5 motion-safe:animate-fade-in motion-reduce:animate-none">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

function defaultOpenSection(summary: ScanSummaryResponse): AccordionSectionId | null {
  const steps = summary.next_steps ?? [];
  if (steps.some((s) => s.priority === "high") || steps.length > 0) return "actions";
  if ((summary.what_the_scan_found ?? []).length > 0) return "found";
  if ((summary.evidence_gaps ?? []).length > 0) return "gaps";
  if ((summary.why_it_matters ?? []).length > 0) return "matters";
  return "notes";
}

function remediationCopy(
  status: ScanSummaryResponse["remediation_status"],
  reason: string | null | undefined
): string {
  if (status === "unavailable") {
    const why = reason?.trim()
      ? humanizeCopy(reason)
      : "no evidence-backed findings to fix automatically";
    return `Automatic fixes unavailable — ${why}.`;
  }
  if (status === "in_progress") return "A fix workflow is in progress.";
  if (status === "done") return "A fix workflow completed.";
  if (status === "not_started") return "No automatic fix has been started yet.";
  return reason ? humanizeCopy(reason) : "Remediation status unavailable.";
}

function Notice({
  tone,
  icon: Icon,
  children,
}: {
  tone: "warn" | "danger";
  icon: LucideIcon;
  children: ReactNode;
}) {
  const classes =
    tone === "warn"
      ? "border-amber-500/20 bg-amber-500/5 text-amber-200/90"
      : "border-rose-500/20 bg-rose-500/5 text-rose-200/90";
  const iconClasses = tone === "warn" ? "text-amber-400" : "text-rose-400";
  return (
    <div
      role="status"
      className={`flex items-start gap-3 rounded-xl border px-4 py-3.5 text-sm leading-relaxed ${classes}`}
    >
      <Icon size={16} className={`shrink-0 mt-[1px] ${iconClasses}`} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

function ReadyBriefPanel({ summary }: { summary: ScanSummaryResponse }) {
  const verdict = summary.verdict;
  const found = summary.what_the_scan_found ?? [];
  const matters = summary.why_it_matters ?? [];
  const gaps = summary.evidence_gaps ?? [];
  const steps = summary.next_steps ?? [];
  const hasNotes = Boolean(
    summary.remediation_status ||
      summary.remediation_reason ||
      summary.limitations?.trim() ||
      (summary.omitted?.length ?? 0) > 0
  );

  const [openId, setOpenId] = useState<AccordionSectionId | null>(() =>
    defaultOpenSection(summary)
  );

  const onToggle = useCallback((id: AccordionSectionId) => {
    setOpenId((prev) => (prev === id ? null : id));
  }, []);

  const assessment = summary.overall_assessment?.text
    ? humanizeCopy(summary.overall_assessment.text)
    : "";
  const tone = verdictTone(verdict);

  return (
    <div
      data-testid="ai-health-brief-ready"
      className="relative rounded-xl bg-surface shadow-border overflow-hidden"
    >
      {/* Ambient verdict wash + top hairline — the single colored moment in the panel */}
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-x-0 top-0 h-56 ${tone.glow}`}
      />
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute inset-x-0 top-0 h-px ${tone.hairline}`}
      />

      <div className="relative px-5 sm:px-7 pt-6 pb-8">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <span
              aria-hidden="true"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/[0.05] ring-1 ring-inset ring-white/10"
            >
              <FileSearch size={12} strokeWidth={2} className="text-text-primary" />
            </span>
            <h2 className={`${EYEBROW} !text-text-primary`}>AI Summary</h2>
            <span aria-hidden="true" className="hidden sm:inline h-3 w-px bg-white/10" />
            <span className="hidden sm:inline text-xs text-text-muted truncate">
              Written by AI from your saved scan
            </span>
          </div>
          {summary.generated_at && (
            <span className="shrink-0 text-xs tabular-nums text-text-muted">
              {formatRelativeTime(summary.generated_at)}
            </span>
          )}
        </div>

        {(assessment || verdict) && (
          <section data-testid="ai-health-brief-overall" className="mt-8">
            {verdict && (
              <p
                data-testid="ai-health-brief-verdict"
                className={`inline-flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider ${tone.text}`}
              >
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 rounded-full ${tone.rail}`}
                />
                {verdictLabel(verdict)}
              </p>
            )}
            {assessment && (
              <p className="mt-3 text-lg sm:text-xl font-semibold tracking-tight text-text-primary leading-snug break-words max-w-[46ch] text-balance">
                {assessment}
              </p>
            )}
            {verdict && (
              <p className="mt-4 text-sm text-text-muted leading-relaxed max-w-[62ch]">
                {verdictHint(verdict)}
              </p>
            )}
            <FactLinks factIds={summary.overall_assessment?.fact_ids} />
          </section>
        )}
      </div>

      <div className="relative border-t border-white/[0.06]">
        {found.length > 0 && (
          <AccordionRow
            id="found"
            testId="ai-health-brief-found"
            title="What we found"
            preview={previewText(found[0]?.text ?? "")}
            count={found.length}
            icon={Search}
            open={openId === "found"}
            onToggle={onToggle}
          >
            <StatementBullets items={found} testId="ai-health-brief-found-items" />
          </AccordionRow>
        )}

        {matters.length > 0 && (
          <AccordionRow
            id="matters"
            testId="ai-health-brief-matters"
            title="Why it matters"
            preview={previewText(matters[0]?.text ?? "")}
            count={matters.length}
            icon={Lightbulb}
            open={openId === "matters"}
            onToggle={onToggle}
          >
            <StatementBullets items={matters} testId="ai-health-brief-matters-items" />
          </AccordionRow>
        )}

        {gaps.length > 0 && (
          <AccordionRow
            id="gaps"
            testId="ai-health-brief-gaps"
            title="What we couldn’t verify"
            preview={previewText(gaps[0]?.text ?? "")}
            count={gaps.length}
            icon={HelpCircle}
            open={openId === "gaps"}
            onToggle={onToggle}
          >
            <div className="mb-5 flex gap-2.5 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3.5 py-3 text-xs text-text-muted leading-relaxed">
              <Info size={14} className="mt-px shrink-0" aria-hidden="true" />
              <p>
                Unverified checks are gaps — not a pass. They mean the scan lacked solid
                evidence for those questions.
              </p>
            </div>
            <StatementBullets items={gaps} testId="ai-health-brief-gaps-items" />
          </AccordionRow>
        )}

        {steps.length > 0 && (
          <AccordionRow
            id="actions"
            testId="ai-health-brief-actions"
            title="What to do next"
            preview={previewText(steps[0]?.text ?? "")}
            count={steps.length}
            icon={ListChecks}
            open={openId === "actions"}
            onToggle={onToggle}
          >
            <NextStepBullets items={steps} />
          </AccordionRow>
        )}

        {hasNotes && (
          <AccordionRow
            id="notes"
            testId="ai-health-brief-notes"
            title="Notes & limits"
            preview={
              summary.remediation_status
                ? remediationCopy(summary.remediation_status, summary.remediation_reason)
                : previewText(summary.limitations || "Scan coverage notes")
            }
            icon={Info}
            open={openId === "notes"}
            onToggle={onToggle}
          >
            <div className="space-y-3.5 text-sm text-text-muted leading-relaxed">
              {(summary.remediation_status || summary.remediation_reason) && (
                <p data-testid="ai-health-brief-remediation" className="break-words">
                  <span className="font-semibold text-text-primary">Fixes: </span>
                  {remediationCopy(summary.remediation_status, summary.remediation_reason)}
                </p>
              )}
              {summary.limitations?.trim() && (
                <p className="break-words">{humanizeCopy(summary.limitations)}</p>
              )}
              {(summary.omitted?.length ?? 0) > 0 && (
                <p className="break-words">
                  <span className="font-semibold text-text-primary">
                    Not included in this brief:{" "}
                  </span>
                  {summary.omitted!.join("; ")}
                </p>
              )}
            </div>
          </AccordionRow>
        )}
      </div>

      <footer className="relative px-5 sm:px-7 py-3.5 border-t border-white/[0.06] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1.5 bg-surface-secondary/40">
        <p className="text-xs text-text-muted leading-relaxed">
          Generated from your saved scan.
        </p>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tabular-nums text-text-muted">
          {summary.model && <span className="font-mono text-[10px]">{summary.model}</span>}
        </div>
      </footer>
    </div>
  );
}

/** Compact tab-row control — place beside Intelligence Overview / AI Lighthouse. */
export function AiSummaryTabControl({
  active,
  disabled,
  loading,
  onClick,
  id = "tab-summary",
  "aria-controls": ariaControls = "panel-summary",
}: {
  active: boolean;
  disabled?: boolean;
  loading?: boolean;
  onClick: () => void;
  id?: string;
  "aria-controls"?: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      id={id}
      aria-controls={ariaControls}
      data-testid="ai-summary-tab-control"
      aria-selected={active}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      onClick={onClick}
      className={`group inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold tracking-wide transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 shrink-0 motion-reduce:transition-none ${
        active
          ? "bg-white text-black shadow-md font-bold"
          : "bg-surface-secondary text-text-muted hover:text-white hover:bg-surface-tertiary shadow-border"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin"
        />
      ) : (
        <FileSearch
          size={14}
          strokeWidth={2}
          aria-hidden="true"
          className={active ? undefined : "text-text-primary"}
        />
      )}
      <span>AI Summary</span>
    </button>
  );
}

/** Skeleton shaped like the finished brief, so the layout does not jump on arrival. */
function GeneratingState() {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const statusText =
    secs < 4
      ? "Preparing your scan findings…"
      : secs < 12
        ? "Writing your AI Website Health Brief…"
        : secs < 25
          ? "Validating evidence citations…"
          : "Still finishing — large scans can take a bit longer…";

  return (
    <div
      data-testid="ai-health-brief"
      className="relative rounded-xl bg-surface shadow-border overflow-hidden"
      aria-live="polite"
      aria-busy="true"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-violet-400/55 via-violet-400/10 to-transparent"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-br from-violet-500/10 via-transparent to-transparent"
      />
      <div className="relative px-5 sm:px-7 pt-6 pb-8">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-2.5 text-xs text-text-muted min-w-0">
            <span
              aria-hidden="true"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/[0.05] ring-1 ring-inset ring-white/10"
            >
              <Sparkles size={12} className="text-violet-400 motion-safe:animate-pulse" />
            </span>
            <span className="truncate">{statusText}</span>
          </p>
          <span className="shrink-0 text-xs tabular-nums text-text-muted">{secs}s</span>
        </div>
        <div className="mt-8 space-y-3 motion-safe:animate-pulse">
          <div className="h-2.5 w-24 rounded-full bg-white/[0.08]" />
          <div className="h-5 w-full max-w-[32rem] rounded-md bg-white/[0.07]" />
          <div className="h-5 w-4/5 max-w-[24rem] rounded-md bg-white/[0.07]" />
          <div className="pt-1">
            <div className="h-3 w-3/5 max-w-[20rem] rounded bg-white/[0.05]" />
          </div>
        </div>
      </div>
      <div className="relative border-t border-white/[0.06] motion-safe:animate-pulse">
        {["What we found", "Why it matters", "What to do next"].map((label) => (
          <div
            key={label}
            className="flex items-center gap-3.5 px-5 sm:px-7 py-4 border-b border-white/[0.06] last:border-b-0"
          >
            <div className="h-7 w-7 rounded-lg bg-white/[0.06]" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="h-3 w-28 sm:w-32 rounded bg-white/[0.07]" />
              <div className="h-2.5 w-40 sm:w-52 max-w-[70%] rounded bg-white/[0.04]" />
            </div>
            <div className="h-4 w-6 rounded-full bg-white/[0.06]" />
          </div>
        ))}
      </div>
      <div className="relative px-5 sm:px-7 py-3.5 border-t border-white/[0.06] bg-surface-secondary/40">
        <p className="text-xs text-text-muted leading-relaxed">
          Generating from your saved scan — this usually takes a few seconds.
        </p>
      </div>
    </div>
  );
}

function readySummary(data: ScanSummaryResponse | null): data is ScanSummaryResponse {
  return Boolean(data && data.status === "ready");
}

export function AiHealthBrief({
  scanId,
  scanStatus,
  outcome,
  jobStatus,
  panelOnly = false,
  open = true,
  onOpenChange,
  autoGenerate = false,
  onAutoGenerateConsumed,
  onBusyChange,
  onRestoredReady,
}: AiHealthBriefProps) {
  const [summary, setSummary] = useState<ScanSummaryResponse | null>(null);
  const [view, setView] = useState<ViewState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [retryAfter, setRetryAfter] = useState<number | null>(null);
  const [ineligibleMessage, setIneligibleMessage] = useState<string | null>(null);

  const pollAbortRef = useRef<AbortController | null>(null);
  const generateInFlightRef = useRef(false);
  const autoGenerateHandledRef = useRef(false);
  const restoredNotifiedRef = useRef(false);
  const viewRef = useRef<ViewState>("loading");
  const summaryRef = useRef<ScanSummaryResponse | null>(null);

  // Keep latest callbacks in refs so parent re-renders (SSE/poll) never
  // recreate fetch effects or flash loading over a ready brief.
  const onOpenChangeRef = useRef(onOpenChange);
  const onAutoGenerateConsumedRef = useRef(onAutoGenerateConsumed);
  const onBusyChangeRef = useRef(onBusyChange);
  const onRestoredReadyRef = useRef(onRestoredReady);
  onOpenChangeRef.current = onOpenChange;
  onAutoGenerateConsumedRef.current = onAutoGenerateConsumed;
  onBusyChangeRef.current = onBusyChange;
  onRestoredReadyRef.current = onRestoredReady;

  const propIneligible = useMemo(
    () => localIneligibleMessage(scanStatus, outcome, jobStatus),
    [scanStatus, outcome, jobStatus]
  );
  const propIneligibleRef = useRef(propIneligible);
  propIneligibleRef.current = propIneligible;

  useEffect(() => {
    viewRef.current = view;
  }, [view]);

  useEffect(() => {
    summaryRef.current = summary;
  }, [summary]);

  useEffect(() => {
    const busy = view === "generating" || view === "loading";
    onBusyChangeRef.current?.(busy);
  }, [view]);

  const applySummary = useCallback((data: ScanSummaryResponse) => {
    setSummary(data);
    summaryRef.current = data;
    if (data.status === "ready") {
      setView("ready");
      viewRef.current = "ready";
      if (!restoredNotifiedRef.current) {
        restoredNotifiedRef.current = true;
        onRestoredReadyRef.current?.();
      }
      return;
    }
    if (data.status === "generating") {
      // Never demote an already-ready brief back to skeleton.
      if (readySummary(summaryRef.current) && viewRef.current === "ready") {
        return;
      }
      setView("generating");
      viewRef.current = "generating";
      return;
    }
    if (data.status === "failed") {
      if (data.reason === "summary_rate_limited") {
        setRetryAfter(data.retry_after ?? null);
        setView("rate_limited");
        viewRef.current = "rate_limited";
      } else {
        setErrorMessage(data.message ?? "Summary generation failed.");
        setView("error");
        viewRef.current = "error";
      }
      return;
    }
    // status === "none" (or unknown): only idle if we do not already have ready content
    if (readySummary(summaryRef.current) && viewRef.current === "ready") {
      return;
    }
    const ineligible = propIneligibleRef.current;
    if (ineligible) {
      setIneligibleMessage(ineligible);
      setView("ineligible");
      viewRef.current = "ineligible";
    } else {
      setView("idle");
      viewRef.current = "idle";
    }
  }, []);

  const pollForReady = useCallback(async (signal: AbortSignal) => {
    const started = Date.now();
    while (Date.now() - started < POLL_TIMEOUT_MS) {
      await sleep(POLL_INTERVAL_MS, signal);
      const data = await getScanSummary(scanId, signal);
      if (data.status === "ready" || data.status === "failed") {
        applySummary(data);
        return;
      }
    }
    setErrorMessage(
      "Summary is taking longer than expected. Please try again in a moment."
    );
    setView("error");
    viewRef.current = "error";
  }, [applySummary, scanId]);

  // Initial GET once per scanId — independent of parent callback identity / status churn.
  useEffect(() => {
    restoredNotifiedRef.current = false;
    autoGenerateHandledRef.current = false;
    generateInFlightRef.current = false;
    setSummary(null);
    summaryRef.current = null;
    setView("loading");
    viewRef.current = "loading";
    setErrorMessage(null);
    setRetryAfter(null);
    setIneligibleMessage(propIneligibleRef.current);

    const controller = new AbortController();
    void (async () => {
      try {
        const data = await getScanSummary(scanId, controller.signal);
        if (controller.signal.aborted) return;
        applySummary(data);
      } catch (err) {
        if (controller.signal.aborted) return;
        const apiErr = err as ApiError;
        setErrorMessage(apiErr.message ?? "Failed to load AI summary.");
        setView("error");
        viewRef.current = "error";
      }
    })();

    return () => {
      controller.abort();
      pollAbortRef.current?.abort();
      pollAbortRef.current = null;
    };
  }, [scanId, applySummary]);

  // Reflect eligibility changes without refetching or clearing a ready brief.
  useEffect(() => {
    if (viewRef.current === "ready" || viewRef.current === "generating" || viewRef.current === "loading") {
      return;
    }
    if (propIneligible) {
      setIneligibleMessage(propIneligible);
      if (viewRef.current === "idle") {
        setView("ineligible");
        viewRef.current = "ineligible";
      }
    } else if (viewRef.current === "ineligible") {
      setIneligibleMessage(null);
      setView("idle");
      viewRef.current = "idle";
    }
  }, [propIneligible]);

  const handleGenerate = useCallback(async () => {
    if (generateInFlightRef.current) return;
    if (propIneligibleRef.current) {
      setIneligibleMessage(propIneligibleRef.current);
      setView("ineligible");
      viewRef.current = "ineligible";
      return;
    }
    // Already have a ready brief — keep it; do not regenerate unless forced by a new click
    // after explicit user intent. Tab control sets autoGenerate only when opening to generate.
    onOpenChangeRef.current?.(true);
    generateInFlightRef.current = true;
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;
    setView("generating");
    viewRef.current = "generating";
    setErrorMessage(null);
    setRetryAfter(null);

    try {
      const data = await generateScanSummary(scanId, controller.signal);
      if (controller.signal.aborted) return;
      if (data.status === "generating") {
        await pollForReady(controller.signal);
        return;
      }
      applySummary(data);
    } catch (err) {
      if (controller.signal.aborted) return;
      const apiErr = err as ApiError;
      const body = apiErr.body;
      if (body?.reason === "summary_rate_limited" || apiErr.status === 429) {
        setRetryAfter(body?.retry_after ?? apiErr.retry_after ?? null);
        setView("rate_limited");
        viewRef.current = "rate_limited";
        return;
      }
      if (apiErr.status === 409 && body?.message) {
        setIneligibleMessage(body.message);
        setView("ineligible");
        viewRef.current = "ineligible";
        return;
      }
      if (body?.status === "generating") {
        try {
          await pollForReady(controller.signal);
        } catch (pollErr) {
          if (controller.signal.aborted) return;
          setErrorMessage(
            (pollErr as ApiError).message ?? "Failed while waiting for summary."
          );
          setView("error");
          viewRef.current = "error";
        }
        return;
      }
      setErrorMessage(apiErr.message ?? "Failed to generate AI summary.");
      setView("error");
      viewRef.current = "error";
    } finally {
      generateInFlightRef.current = false;
    }
  }, [applySummary, pollForReady, scanId]);

  // One-shot auto-generate from tab control. Never re-fires on parent re-renders.
  useEffect(() => {
    if (!autoGenerate) {
      autoGenerateHandledRef.current = false;
      return;
    }
    if (autoGenerateHandledRef.current) return;

    if (view === "loading") return;

    autoGenerateHandledRef.current = true;
    onAutoGenerateConsumedRef.current?.();

    if (view === "ready" || view === "generating") return;
    if (view === "ineligible" || propIneligibleRef.current) return;

    void handleGenerate();
  }, [autoGenerate, view, handleGenerate]);

  const handleRetry = useCallback(() => {
    if (generateInFlightRef.current) return;
    void handleGenerate();
  }, [handleGenerate]);

  // Keep mounted when collapsed so state survives; only hide markup.
  if (!open && panelOnly) {
    return <div className="hidden" aria-hidden="true" data-testid="ai-health-brief-hidden" />;
  }

  const generateDisabled =
    view === "generating" ||
    view === "loading" ||
    view === "ineligible" ||
    Boolean(propIneligible) ||
    generateInFlightRef.current;

  if (view === "ready" && summary) {
    return <ReadyBriefPanel summary={summary} />;
  }

  if (view === "error") {
    return (
      <div data-testid="ai-health-brief" className="space-y-3">
        <ErrorState
          title="AI summary unavailable"
          message={errorMessage ?? "Something went wrong."}
          onRetry={handleRetry}
          retryLabel="Retry"
        />
      </div>
    );
  }

  if (view === "loading" || view === "generating") {
    return <GeneratingState />;
  }

  const rateLimitedNotice = (
    <Notice tone="danger" icon={Clock3}>
      Rate limit reached
      {retryAfter != null ? ` — try again in about ${retryAfter}s` : ". Try again later."}
    </Notice>
  );

  // idle / ineligible / rate_limited
  if (panelOnly) {
    return (
      <div
        data-testid="ai-health-brief"
        className="relative rounded-xl bg-surface shadow-border px-5 sm:px-7 py-6 space-y-4 overflow-hidden"
        aria-live="polite"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-white/30 via-white/5 to-transparent"
        />
        {view === "ineligible" && (
          <Notice tone="warn" icon={AlertCircle}>
            {ineligibleMessage ?? propIneligible}
          </Notice>
        )}
        {view === "rate_limited" && rateLimitedNotice}
        {view === "idle" && (
          <div className="flex items-start gap-3.5">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/[0.04] ring-1 ring-inset ring-white/10"
            >
              <Sparkles size={16} className="text-violet-400" />
            </span>
            <p className="text-sm text-text-muted leading-relaxed pt-0.5">
              Select <span className="font-semibold text-text-primary">AI Summary</span> above
              to generate a plain-English brief from this scan.
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      data-testid="ai-health-brief"
      className="relative rounded-xl bg-surface shadow-border px-5 sm:px-7 py-6 sm:py-7 space-y-6 overflow-hidden"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-violet-400/55 via-violet-400/10 to-transparent"
      />
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0 max-w-xl">
          <div className="flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-white/[0.05] ring-1 ring-inset ring-white/10"
            >
              <Sparkles size={12} className="text-violet-400" />
            </span>
            <span className={EYEBROW}>On demand</span>
          </div>
          <h2 className="mt-4 text-lg sm:text-xl font-semibold tracking-tight text-text-primary leading-snug">
            AI Website Health Brief
          </h2>
          <p className="mt-3 text-sm text-text-muted leading-relaxed">
            Plain-English explanation of your scan, what matters and what to do first
          </p>
          <p className="mt-2 text-xs text-text-muted/80 leading-relaxed">
            You’ll get what we found, why it matters, what we couldn’t verify and the next
            steps. It runs only when you ask, using this scan’s saved data.
          </p>
        </div>

        <button
          type="button"
          data-testid="ai-health-brief-generate"
          disabled={generateDisabled}
          onClick={() => void handleGenerate()}
          className="group inline-flex shrink-0 items-center justify-center gap-2.5 rounded-lg bg-white px-5 py-3 text-xs font-semibold text-black tracking-wider uppercase transition-colors duration-150 hover:bg-neutral-200 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 motion-reduce:transition-none"
        >
          <Sparkles size={14} aria-hidden="true" />
          Generate AI Summary
          <ArrowRight
            size={14}
            aria-hidden="true"
            className="-ml-0.5 transition-transform duration-150 group-hover:translate-x-0.5 group-disabled:translate-x-0 motion-reduce:transition-none"
          />
        </button>
      </div>

      {view === "ineligible" && (
        <Notice tone="warn" icon={AlertCircle}>
          {ineligibleMessage ?? propIneligible}
        </Notice>
      )}
      {view === "rate_limited" && rateLimitedNotice}
    </div>
  );
}