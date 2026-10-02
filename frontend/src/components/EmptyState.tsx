import { Inbox } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  positive?: boolean;
}

export function EmptyState({
  title,
  description,
  icon,
  positive = false,
}: EmptyStateProps) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center gap-3 rounded-xl bg-surface shadow-border px-6 py-12 text-center"
    >
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-full ${
          positive ? "bg-emerald-950/70 border border-emerald-800/50" : "bg-surface-secondary shadow-border"
        }`}
      >
        {icon ?? (
          <Inbox
            size={20}
            className={positive ? "text-emerald-400" : "text-text-muted"}
            aria-hidden="true"
          />
        )}
      </div>
      <div>
        <p className="text-sm font-semibold text-text-primary">{title}</p>
        {description && (
          <p className="mt-1 text-xs text-text-muted max-w-sm leading-relaxed">{description}</p>
        )}
      </div>
    </div>
  );
}