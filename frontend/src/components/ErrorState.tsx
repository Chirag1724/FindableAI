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
      className="flex flex-col items-center justify-center gap-4 rounded-xl bg-surface shadow-border px-6 py-12 text-center"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-rose-950/70 border border-rose-800/50">
        <AlertTriangle size={20} className="text-rose-400" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        <p className="mt-1 text-xs text-text-muted max-w-sm leading-relaxed">{message}</p>
      </div>
      <div className="flex gap-2.5 pt-1">
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-lg bg-white px-4 py-2 text-xs font-semibold text-black tracking-wider uppercase transition-colors duration-150 hover:bg-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            {retryLabel}
          </button>
        )}
        {action}
      </div>
    </div>
  );
}