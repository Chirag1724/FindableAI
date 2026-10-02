"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";

interface ScanDashboardErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ScanDashboardError({
  error,
  reset,
}: ScanDashboardErrorProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="flex w-full max-w-sm flex-col items-center gap-4 rounded-xl bg-surface shadow-border px-6 py-10 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-950/60 border border-rose-800/50">
          <AlertTriangle size={20} className="text-rose-400" aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-semibold text-text-primary">Dashboard error</p>
          <p className="mt-1 text-xs text-text-muted leading-relaxed">
            {error.message || "An unexpected error occurred while loading this dashboard."}
          </p>
        </div>
        <div className="flex gap-2.5 pt-2">
          <button
            type="button"
            onClick={reset}
            className="rounded-lg bg-white px-4 py-2 text-xs font-semibold text-black tracking-wider uppercase transition-colors duration-150 hover:bg-neutral-200 focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Try again
          </button>
          <Link
            href="/"
            className="rounded-lg bg-surface-secondary shadow-border px-4 py-2 text-xs font-medium text-text-primary transition-colors duration-150 hover:bg-surface-tertiary focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Back home
          </Link>
        </div>
      </div>
    </div>
  );
}