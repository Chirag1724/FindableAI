import { ScanProgress } from "@/components/ScanProgress";
import { LiveScanConsole } from "@/components/LiveScanConsole";

export default function ScanDashboardLoading() {
  return (
    <div className="min-h-screen bg-background pb-24 relative overflow-x-hidden">
      {/* Ambient Grid & Glow Background */}
      <div className="pointer-events-none absolute inset-0 -top-20 flex items-center justify-center overflow-hidden">
        <div className="hero-grid-bg absolute inset-0 opacity-40" />
        <div className="hero-glow absolute inset-0 opacity-40" />
      </div>

      {/* Header placeholder matching real header */}
      <div className="sticky top-0 z-30 h-14 w-full glass border-b border-white/[0.08]" />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
        <ScanProgress
          currentStatus="pending"
          latestEvent={{
            scan_id: "",
            status: "pending",
            progress_percent: 12,
            current_step: "Initializing",
            message: "Connecting to telemetry stream and loading scan status...",
            timestamp: new Date().toISOString(),
          }}
          lastGoodStatus="pending"
        />
        <LiveScanConsole
          currentStatus="pending"
          latestEvent={null}
          events={[]}
          targetUrl="Initializing audit session..."
        />
      </main>
    </div>
  );
}