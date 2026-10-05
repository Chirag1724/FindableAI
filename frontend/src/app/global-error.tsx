"use client";

import { useEffect } from "react";
import { RotateCcw } from "lucide-react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Root layout error:", error);
  }, [error]);

  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#0A0A0A] text-[#EDEDED] antialiased flex flex-col items-center justify-center p-4 text-center font-sans">
        <div className="inline-flex items-center rounded-md border border-white/10 bg-[#141414] px-2.5 py-1 text-xs font-mono text-[#A1A1A1] mb-6">
          <span>CRITICAL &middot; SYSTEM ERROR</span>
        </div>

        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white mb-3">
          Application error
        </h1>

        <p className="max-w-md text-sm text-[#A1A1A1] mb-6 leading-relaxed">
          A critical error occurred in the root layout. Please reload or reset the application.
        </p>

        {error.digest && (
          <div className="mb-8 rounded-md border border-white/10 bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#A1A1A1]">
            Digest: {error.digest}
          </div>
        )}

        <button
          onClick={() => reset()}
          className="inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-xs font-medium text-black transition-colors hover:bg-neutral-200"
        >
          <RotateCcw size={13} aria-hidden="true" />
          <span>Reload application</span>
        </button>
      </body>
    </html>
  );
}
