"use client";

import { useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

interface CopyButtonProps {
  text: string;
  label?: string;
  className?: string;
}

export function CopyButton({ text, label, className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveRef = useRef<HTMLSpanElement>(null);

  const handleCopy = async () => {
    if (copied) return;
    let success = false;

    try {
      await navigator.clipboard.writeText(text);
      success = true;
    } catch {
      // Fallback for browsers without clipboard API
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        success = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        // Copy not available
      }
    }

    if (success) {
      setCopied(true);
      if (liveRef.current) liveRef.current.textContent = "Copied to clipboard";
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setCopied(false);
        if (liveRef.current) liveRef.current.textContent = "";
      }, 1500);
    }
  };

  return (
    <>
      <span
        ref={liveRef}
        aria-live="polite"
        className="sr-only"
      />
      <button
        type="button"
        onClick={() => void handleCopy()}
        title={label ?? "Copy to clipboard"}
        aria-label={label ?? "Copy to clipboard"}
        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${copied
            ? "text-emerald-400"
            : "text-[#A1A1A1] hover:text-[#EDEDED]"
          } ${className}`}
      >
        {copied ? (
          <Check size={12} aria-hidden="true" />
        ) : (
          <Copy size={12} aria-hidden="true" />
        )}
        <span>{copied ? "Copied" : (label ?? "Copy")}</span>
      </button>
    </>
  );
}