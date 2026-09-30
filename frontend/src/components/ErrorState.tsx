import { AlertTriangle } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  action?: React.ReactNode;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retryLabel = "Try again",
  action,
}: ErrorStateProps) {
  return (
    <div
      data-testid="error-state"
      className="flex flex-col items-center justify-center gap-4 rounded-2xl bg-[#141414] px-6 py-12 text-center"
      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-950">
        <AlertTriangle size={22} className="text-rose-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-[#EDEDED]">{title}</p>
        <p className="mt-1 text-xs text-[#A1A1A1]">{message}</p>
      </div>
      <div className="flex gap-2">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg bg-[#191919] px-4 py-2 text-sm text-[#EDEDED] transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {retryLabel}
          </button>
        )}
        {action}
      </div>
    </div>
  );
}