import { GaugeSkeleton, TableSkeleton, StatsSkeleton, CardSkeleton } from "@/components/Skeletons";

export default function ScanDashboardLoading() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header placeholder matching real header */}
      <div className="sticky top-0 z-30 h-14 w-full glass border-b border-white/[0.08]" />

      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
        <StatsSkeleton />
        <GaugeSkeleton />
        <div>
          <div className="mb-3 h-4 w-36 rounded bg-surface-secondary animate-pulse" />
          <TableSkeleton rows={5} />
        </div>
        <div>
          <div className="mb-3 h-4 w-32 rounded bg-surface-secondary animate-pulse" />
          <CardSkeleton count={1} />
        </div>
      </div>
    </div>
  );
}