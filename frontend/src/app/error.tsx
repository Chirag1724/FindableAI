"use client";

import { useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, RotateCcw } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Client runtime error:", error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 text-center">
      {/* Monospace Code Pill */}
      <div className="inline-flex items-center rounded-md border border-white/10 bg-surface px-2.5 py-1 text-xs font-mono text-text-muted mb-6">
        <span>500 &middot; APPLICATION ERROR</span>
      </div>

      <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-text-primary mb-3">
        Something went wrong
      </h1>

      <p className="max-w-md text-sm text-text-muted mb-6 leading-relaxed">
        An unexpected error occurred. You can retry the operation or navigate back to the dashboard.
      </p>

      {error.digest && (
        <div className="mb-8 rounded-md border border-white/10 bg-surface px-3 py-1.5 font-mono text-xs text-text-muted">
          Digest: {error.digest}
        </div>
      )}

      {/* Clean Linear/Vercel-style Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => reset()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black transition-colors hover:bg-neutral-200 focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <RotateCcw size={13} aria-hidden="true" />
          <span>Try again</span>
        </button>

        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-surface px-4 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-surface-secondary hover:text-white focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <ArrowLeft size={13} aria-hidden="true" />
          <span>Home</span>
        </Link>
      </div>
    </div>
  );
}
