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
      <div
        className="flex w-full max-w-sm flex-col items-center gap-4 rounded-2xl bg-[#141414] px-6 py-12 text-center"
        style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-950">
          <AlertTriangle size={22} className="text-rose-400" aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-semibold text-[#EDEDED]">Page error</p>
          <p className="mt-1 text-xs text-[#A1A1A1]">
            {error.message || "An unexpected error occurred."}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={reset}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-violet-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Try again
          </button>
          <Link
            href="/"
            className="rounded-lg bg-[#191919] px-4 py-2 text-sm text-[#EDEDED] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Back home
          </Link>
        </div>
      </div>
    </div>
  );
}