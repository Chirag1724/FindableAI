import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 text-center">
      {/* Monospace Code Pill */}
      <div className="inline-flex items-center rounded-md border border-white/10 bg-surface px-2.5 py-1 text-xs font-mono text-text-muted mb-6">
        <span>404 &middot; NOT FOUND</span>
      </div>

      <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-text-primary mb-3">
        Page not found
      </h1>

      <p className="max-w-md text-sm text-text-muted mb-8 leading-relaxed">
        The requested URL does not exist or may have been moved.
      </p>

      {/* Clean Linear/Vercel-style Actions */}
      <div className="flex items-center gap-3">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-surface px-4 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-surface-secondary hover:text-white focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <ArrowLeft size={13} aria-hidden="true" />
          <span>Home</span>
        </Link>
        <Link
          href="/audit"
          className="inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black transition-colors hover:bg-neutral-200 focus-visible:ring-2 focus-visible:ring-blue-500"
        >
          <span>Run Audit</span>
          <ArrowRight size={13} aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}