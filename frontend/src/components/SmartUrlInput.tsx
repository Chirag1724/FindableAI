"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Clock, Globe2, Link2, X } from "lucide-react";
import {
  type BuilderState,
  type SmartUrlParts,
  type UrlInputMode,
  type UrlProtocol,
  type UrlTldOption,
  URL_PROTOCOLS,
  URL_TLD_OPTIONS,
  composeCanonical,
  composeFromBuilder,
  ingestDomainPaste,
  partsFromCanonical,
  switchMode,
  validateScanUrl,
} from "@/lib/smartUrl";
import {
  clearUrlHistory,
  readUrlHistory,
  removeUrlHistory,
} from "@/lib/urlHistory";

export interface SmartUrlInputProps {
  id?: string;
  value: string;
  onChange: (canonicalUrl: string) => void;
  error?: string | null;
  disabled?: boolean;
  "data-testid"?: string;
}

const modeBtnBase =
  "px-2.5 py-1 rounded-md text-[11px] font-mono transition-colors duration-150 border";

type MenuOption<T extends string> = {
  value: T;
  label: string;
};

type MenuCoords = { top: number; left: number; minWidth: number };

function UrlMenuSelect<T extends string>({
  id,
  label,
  value,
  options,
  disabled,
  testId,
  onChange,
  triggerClassName,
  menuAlign = "left",
}: {
  id: string;
  label: string;
  value: T;
  options: MenuOption<T>[];
  disabled?: boolean;
  testId: string;
  onChange: (value: T) => void;
  triggerClassName?: string;
  menuAlign?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const [mounted, setMounted] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLUListElement | null>(null);
  const listId = `${id}-listbox`;
  const selected = options.find((o) => o.value === value) ?? options[0];

  useEffect(() => {
    setMounted(true);
  }, []);

  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const minWidth = Math.max(rect.width, 152);
    const left =
      menuAlign === "right"
        ? Math.max(8, rect.right - minWidth)
        : Math.min(rect.left, window.innerWidth - minWidth - 8);
    setCoords({
      top: rect.bottom + 6,
      left,
      minWidth,
    });
  }, [menuAlign]);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };

    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    const onReposition = () => updatePosition();

    // Defer so the opening click does not immediately close the menu.
    const timer = window.setTimeout(() => {
      document.addEventListener("pointerdown", onPointerDown, true);
    }, 0);

    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);

    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
    };
  }, [open, updatePosition]);

  const pick = useCallback(
    (next: T) => {
      onChange(next);
      setOpen(false);
      triggerRef.current?.focus();
    },
    [onChange]
  );

  const onTriggerKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    }
  };

  const menu =
    open && mounted && coords
      ? createPortal(
          <ul
            ref={menuRef}
            id={listId}
            role="listbox"
            aria-label={label}
            data-testid={`${testId}-menu`}
            style={{
              position: "fixed",
              top: coords.top,
              left: coords.left,
              minWidth: coords.minWidth,
              zIndex: 9999,
            }}
            className="max-h-64 overflow-auto rounded-xl border border-white/[0.10] bg-[#12141c] py-1.5 shadow-[0_16px_40px_-12px_rgba(0,0,0,0.85),inset_0_1px_0_0_rgba(255,255,255,0.06)]"
          >
            {options.map((opt) => {
              const isActive = opt.value === value;
              return (
                <li key={opt.value} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    data-testid={`${testId}-option-${opt.value.replace(/^\./, "")}`}
                    onClick={() => pick(opt.value)}
                    className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm font-mono transition-colors duration-100 ${
                      isActive
                        ? "bg-white/[0.08] text-white"
                        : "text-text-muted hover:bg-white/[0.05] hover:text-white"
                    }`}
                  >
                    <span>{opt.label}</span>
                    {isActive && (
                      <Check size={14} className="shrink-0 text-emerald-400" aria-hidden="true" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>,
          document.body
        )
      : null;

  return (
    <div className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        id={id}
        data-testid={testId}
        disabled={disabled}
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKey}
        className={
          triggerClassName ??
          "inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm font-mono text-white/90 hover:text-white hover:bg-white/[0.06] border border-transparent hover:border-white/[0.08] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
        }
      >
        <span>{selected?.label}</span>
        <ChevronDown
          size={14}
          className={`text-text-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>
      {menu}
    </div>
  );
}

export default function SmartUrlInput({
  id,
  value,
  onChange,
  error,
  disabled = false,
  "data-testid": testId = "scan-url-input",
}: SmartUrlInputProps) {
  const reactId = useId();
  const protocolId = `${id ?? reactId}-protocol`;
  const domainId = id ?? `${reactId}-domain`;
  const tldId = `${id ?? reactId}-tld`;
  const customId = `${id ?? reactId}-custom`;
  const previewId = `${id ?? reactId}-preview`;

  const [parts, setParts] = useState<SmartUrlParts>(() => partsFromCanonical(value));
  const [history, setHistory] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const lastEmitted = useRef(value);
  const historyPanelRef = useRef<HTMLDivElement | null>(null);
  const fieldWrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (value === lastEmitted.current) return;
    lastEmitted.current = value;
    setParts(partsFromCanonical(value));
  }, [value]);

  useEffect(() => {
    setHistory(readUrlHistory());
  }, []);

  useEffect(() => {
    if (!historyOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (fieldWrapRef.current?.contains(target)) return;
      if (historyPanelRef.current?.contains(target)) return;
      setHistoryOpen(false);
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setHistoryOpen(false);
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("pointerdown", onPointerDown, true);
    }, 0);
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [historyOpen]);

  const openHistory = () => {
    const next = readUrlHistory();
    setHistory(next);
    if (next.length > 0) setHistoryOpen(true);
  };

  const emit = (next: SmartUrlParts) => {
    setParts(next);
    const canonical = composeCanonical(next);
    lastEmitted.current = canonical;
    onChange(canonical);
  };

  const applyHistoryUrl = (url: string) => {
    emit(partsFromCanonical(url));
    setHistoryOpen(false);
  };

  const handleDeleteHistory = (url: string) => {
    const next = removeUrlHistory(url);
    setHistory(next);
    if (next.length === 0) setHistoryOpen(false);
  };

  const handleClearHistory = () => {
    clearUrlHistory();
    setHistory([]);
    setHistoryOpen(false);
  };

  const preview =
    parts.mode === "custom"
      ? parts.customUrl.trim()
      : composeFromBuilder(parts.builder);

  const setBuilder = (patch: Partial<BuilderState>) => {
    emit({
      ...parts,
      mode: "builder",
      builder: { ...parts.builder, ...patch },
    });
  };

  const handleMode = (mode: UrlInputMode) => {
    emit(switchMode(parts, mode));
  };

  const handleDomainChange = (raw: string) => {
    const nextBuilder = ingestDomainPaste(parts.builder, raw);
    emit({ ...parts, mode: "builder", builder: nextBuilder });
  };

  const protocolOptions: MenuOption<UrlProtocol>[] = URL_PROTOCOLS.map((p) => ({
    value: p,
    label: `${p}://`,
  }));

  const tldOptions: MenuOption<UrlTldOption>[] = [
    ...URL_TLD_OPTIONS.map((t) => ({ value: t as UrlTldOption, label: t })),
    { value: "other", label: "Other / Custom" },
  ];

  const showHistory = historyOpen && history.length > 0 && !disabled;

  const historyPanel = showHistory ? (
    <div
      ref={historyPanelRef}
      data-testid="url-history-panel"
      role="listbox"
      aria-label="Recent URLs"
      className="absolute left-0 right-0 top-[calc(100%+6px)] z-40 rounded-xl border border-white/[0.10] bg-[#12141c] py-1.5 shadow-[0_16px_40px_-12px_rgba(0,0,0,0.85),inset_0_1px_0_0_rgba(255,255,255,0.06)]"
    >
      <div className="flex items-center justify-between px-3 pb-1.5 pt-0.5">
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wider text-text-muted/70">
          <Clock size={11} aria-hidden="true" />
          Recent
        </span>
        <button
          type="button"
          data-testid="url-history-clear"
          onClick={handleClearHistory}
          className="text-[10px] font-mono text-text-muted/70 hover:text-rose-300 transition-colors duration-150"
        >
          Clear all
        </button>
      </div>
      <ul>
        {history.map((item) => (
          <li key={item} role="presentation" className="flex items-stretch gap-0.5 px-1">
            <button
              type="button"
              role="option"
              data-testid="url-history-item"
              onClick={() => applyHistoryUrl(item)}
              className="min-w-0 flex-1 truncate rounded-lg px-2.5 py-2 text-left text-sm font-mono text-text-muted hover:bg-white/[0.05] hover:text-white transition-colors duration-100"
            >
              {item}
            </button>
            <button
              type="button"
              data-testid="url-history-delete"
              aria-label={`Remove ${item} from history`}
              onClick={(e) => {
                e.stopPropagation();
                handleDeleteHistory(item);
              }}
              className="shrink-0 rounded-lg px-2 text-text-muted/60 hover:bg-white/[0.05] hover:text-rose-300 transition-colors duration-100"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  ) : null;

  let builderField: ReactNode = null;
  if (parts.mode === "builder") {
    builderField = (
      <div
        className="rounded-xl bg-surface-secondary/80 shadow-border border border-white/[0.06] transition-all duration-150 focus-within:border-white/[0.14] focus-within:ring-2 focus-within:ring-blue-500/40"
        style={{
          boxShadow: error ? "0 0 0 1px #f43f5e" : undefined,
        }}
      >
        <div className="flex flex-col sm:flex-row sm:items-stretch gap-0">
          <div className="flex items-center gap-1.5 px-2.5 sm:px-3 py-2 sm:py-0 sm:border-r border-white/[0.06] shrink-0">
            <Globe2 size={15} className="shrink-0 text-text-muted hidden sm:block" aria-hidden="true" />
            <UrlMenuSelect
              id={protocolId}
              label="URL protocol"
              testId="url-protocol-select"
              disabled={disabled}
              value={parts.builder.protocol}
              options={protocolOptions}
              onChange={(protocol) => setBuilder({ protocol })}
            />
          </div>

          <div className="flex items-center min-w-0 flex-1 px-3 py-2.5 sm:py-3 border-t sm:border-t-0 border-white/[0.06]">
            <label htmlFor={domainId} className="sr-only">
              Domain
            </label>
            <input
              id={domainId}
              data-testid={testId}
              type="text"
              inputMode="url"
              autoComplete="off"
              disabled={disabled}
              value={parts.builder.domain}
              onChange={(e) => handleDomainChange(e.target.value)}
              onFocus={openHistory}
              placeholder="example or www.example"
              required
              aria-label="Domain or host"
              aria-describedby={error ? "url-error" : previewId}
              aria-invalid={!!error}
              aria-autocomplete="list"
              aria-expanded={showHistory}
              className="min-w-0 w-full bg-transparent text-sm text-white placeholder-text-muted/45 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 px-2.5 sm:px-3 py-2 sm:py-0 border-t sm:border-t-0 sm:border-l border-white/[0.06] shrink-0">
            <UrlMenuSelect
              id={tldId}
              label="Top-level domain"
              testId="url-tld-select"
              disabled={disabled}
              value={parts.builder.tld}
              options={tldOptions}
              menuAlign="right"
              onChange={(tld) => setBuilder({ tld })}
              triggerClassName="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-sm font-mono text-emerald-400/90 hover:text-emerald-300 hover:bg-white/[0.06] border border-transparent hover:border-white/[0.08] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
            />
            {parts.builder.tld === "other" && (
              <>
                <label htmlFor={`${tldId}-custom`} className="sr-only">
                  Custom top-level domain
                </label>
                <input
                  id={`${tldId}-custom`}
                  data-testid="url-custom-tld"
                  type="text"
                  disabled={disabled}
                  value={parts.builder.customTld}
                  onChange={(e) => setBuilder({ customTld: e.target.value })}
                  placeholder=".app"
                  aria-label="Custom top-level domain"
                  className="w-[4.5rem] rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-1 text-sm font-mono text-white placeholder-text-muted/45 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                />
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2" role="group" aria-label="URL input mode">
        <button
          type="button"
          data-testid="url-mode-builder"
          disabled={disabled}
          aria-pressed={parts.mode === "builder"}
          onClick={() => handleMode("builder")}
          className={`${modeBtnBase} ${
            parts.mode === "builder"
              ? "bg-surface-secondary text-white border-white/[0.12]"
              : "bg-transparent text-text-muted border-white/[0.06] hover:text-white"
          }`}
        >
          Builder
        </button>
        <button
          type="button"
          data-testid="url-mode-custom"
          disabled={disabled}
          aria-pressed={parts.mode === "custom"}
          onClick={() => handleMode("custom")}
          className={`${modeBtnBase} ${
            parts.mode === "custom"
              ? "bg-surface-secondary text-white border-white/[0.12]"
              : "bg-transparent text-text-muted border-white/[0.06] hover:text-white"
          }`}
        >
          Custom URL
        </button>
      </div>

      <div ref={fieldWrapRef} className="relative">
        {parts.mode === "builder" ? (
          builderField
        ) : (
          <div
            className="flex items-center gap-3 rounded-xl bg-surface-secondary/80 shadow-border border border-white/[0.06] px-3.5 sm:px-4 py-3 sm:py-3.5 transition-all duration-150 focus-within:border-white/[0.14] focus-within:ring-2 focus-within:ring-blue-500/40"
            style={{
              boxShadow: error ? "0 0 0 1px #f43f5e" : undefined,
            }}
          >
            <Link2 size={16} className="shrink-0 text-text-muted" aria-hidden="true" />
            <label htmlFor={customId} className="sr-only">
              Full website URL
            </label>
            <input
              id={customId}
              data-testid={testId}
              type="url"
              autoComplete="off"
              disabled={disabled}
              value={parts.customUrl}
              onChange={(e) =>
                emit({ ...parts, mode: "custom", customUrl: e.target.value })
              }
              onFocus={openHistory}
              placeholder="https://example.com:8443/path?q=1"
              required
              aria-label="Full website URL"
              aria-describedby={error ? "url-error" : previewId}
              aria-invalid={!!error}
              aria-autocomplete="list"
              aria-expanded={showHistory}
              className="w-full bg-transparent text-sm text-white placeholder-text-muted/45 focus:outline-none"
            />
          </div>
        )}
        {historyPanel}
      </div>

      <p
        id={previewId}
        data-testid="url-preview"
        className="text-[11px] font-mono text-text-muted break-all"
      >
        <span className="text-text-muted/60 uppercase tracking-wider mr-1.5">Preview</span>
        {preview ? (
          <span className="text-emerald-400/90">{preview}</span>
        ) : (
          <span className="text-text-muted/40">Enter a domain to preview the normalized URL</span>
        )}
      </p>
    </div>
  );
}

/** Re-export validation for form submit without duplicating rules. */
export { validateScanUrl, composeCanonical };
