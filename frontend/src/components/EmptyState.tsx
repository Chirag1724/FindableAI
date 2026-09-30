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
      className="flex flex-col items-center justify-center gap-3 rounded-2xl bg-[#141414] px-6 py-12 text-center"
      style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
    >
      <div
        className={`flex h-12 w-12 items-center justify-center rounded-full ${positive ? "bg-emerald-950" : "bg-[#191919]"
          }`}
      >
        {icon ?? (
          <Inbox
            size={22}
            className={positive ? "text-emerald-400" : "text-[#A1A1A1]"}
            aria-hidden="true"
          />
        )}
      </div>
      <div>
        <p className="text-sm font-semibold text-[#EDEDED]">{title}</p>
        {description && (
          <p className="mt-1 text-xs text-[#A1A1A1]">{description}</p>
        )}
      </div>
    </div>
  );
}