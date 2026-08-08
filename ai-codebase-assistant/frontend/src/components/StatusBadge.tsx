import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import type { RepoStatus } from "@/types";

const CONFIG: Record<RepoStatus, { label: string; className: string; icon: React.ReactNode }> = {
  pending: {
    label: "Queued",
    className: "text-text-muted bg-surface-raised border-border",
    icon: <CircleDashed className="size-3.5" />,
  },
  indexing: {
    label: "Indexing",
    className: "text-warn bg-warn-soft border-warn/30",
    icon: <Loader2 className="size-3.5 animate-spin" />,
  },
  ready: {
    label: "Ready",
    className: "text-accent-text bg-accent-soft border-accent/30",
    icon: <CheckCircle2 className="size-3.5" />,
  },
  failed: {
    label: "Failed",
    className: "text-danger bg-danger-soft border-danger/30",
    icon: <XCircle className="size-3.5" />,
  },
};

export default function StatusBadge({ status }: { status: RepoStatus }) {
  const c = CONFIG[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${c.className}`}
    >
      {c.icon}
      {c.label}
    </span>
  );
}
