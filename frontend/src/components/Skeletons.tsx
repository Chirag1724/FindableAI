// Skeleton loader components for the dashboard loading states

export function GaugeSkeleton() {
  return (
    <div className="rounded-xl bg-surface shadow-border p-6 animate-pulse">
      <div className="flex flex-col items-center gap-4">
        <div className="h-4 w-32 rounded bg-surface-secondary" />
        <div className="h-44 w-44 rounded-full bg-surface-secondary" />
        <div className="h-6 w-24 rounded bg-surface-secondary" />
        <div className="w-full space-y-2.5 pt-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full bg-surface-secondary" />
              <div className="h-3 flex-1 rounded bg-surface-secondary" />
              <div className="h-3 w-10 rounded bg-surface-secondary" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="rounded-xl bg-surface shadow-border overflow-hidden animate-pulse">
      {/* Header */}
      <div className="flex gap-4 px-4 py-3 border-b border-white/[0.06]">
        {[40, 20, 15, 15].map((w, i) => (
          <div key={i} className="h-3.5 rounded bg-surface-secondary" style={{ width: `${w}%` }} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 px-4 py-3.5 border-b border-white/[0.04] last:border-0">
          {[30, 40, 15, 12].map((w, j) => (
            <div key={j} className="h-3 rounded bg-surface-secondary" style={{ width: `${w}%` }} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ count = 2 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl bg-surface shadow-border p-5 animate-pulse"
        >
          <div className="mb-3 h-4 w-1/3 rounded bg-surface-secondary" />
          <div className="mb-2 h-3 w-full rounded bg-surface-secondary" />
          <div className="h-3 w-4/5 rounded bg-surface-secondary" />
        </div>
      ))}
    </div>
  );
}

export function StatsSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl bg-surface shadow-border p-4 animate-pulse"
        >
          <div className="mb-2.5 h-3 w-3/4 rounded bg-surface-secondary" />
          <div className="h-7 w-1/2 rounded bg-surface-secondary" />
        </div>
      ))}
    </div>
  );
}