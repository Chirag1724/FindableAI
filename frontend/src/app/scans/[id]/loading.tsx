import { GaugeSkeleton, TableSkeleton, StatsSkeleton, CardSkeleton } from "@/components/Skeletons";

export default function ScanDashboardLoading() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header placeholder */}
      <div
        className="sticky top-0 z-30 h-12 w-full"
        style={{
          background: "rgba(10,10,10,0.85)",
          boxShadow: "0 1px 0 rgba(255,255,255,0.06)",
        }}
      />
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        <StatsSkeleton />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          <GaugeSkeleton />
          <TableSkeleton />
        </div>
        <CardSkeleton count={1} />
      </div>
    </div>
  );
}