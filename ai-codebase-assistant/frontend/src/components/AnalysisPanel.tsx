import { useEffect, useState } from "react";
import { AlertTriangle, Ghost, Loader2, ShieldAlert } from "lucide-react";
import { api } from "@/api/client";
import type { AnalysisOut } from "@/types";

interface Props {
  repoId: string;
  onOpenSymbol: (filePath: string, line: number) => void;
}

type Tab = "dead_code" | "complexity" | "security";

const SEVERITY_STYLE: Record<string, string> = {
  HIGH: "text-danger bg-danger-soft border-danger/30",
  MEDIUM: "text-warn bg-warn-soft border-warn/30",
  LOW: "text-text-muted bg-surface-raised border-border",
};

export default function AnalysisPanel({ repoId, onOpenSymbol }: Props) {
  const [tab, setTab] = useState<Tab>("dead_code");
  const [data, setData] = useState<AnalysisOut | null>(null);

  useEffect(() => {
    api.getAnalysis(repoId).then(setData);
  }, [repoId]);

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-5 animate-spin text-text-faint" />
      </div>
    );
  }

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: "dead_code", label: "Dead code", count: data.dead_code.length },
    { id: "complexity", label: "Complexity", count: data.complexity_hotspots.length },
    { id: "security", label: "Security", count: data.security_findings.length },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-border-soft bg-surface px-4 py-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.id ? "bg-surface-raised text-text" : "text-text-faint hover:text-text-muted"
            }`}
          >
            {t.label}
            {t.count > 0 && (
              <span className="rounded-full bg-bg px-1.5 py-0.5 text-[10px] text-text-faint">{t.count}</span>
            )}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === "dead_code" && (
          <List
            empty="No unreferenced functions or methods found — nice."
            items={data.dead_code}
            renderItem={(f) => (
              <Row
                key={f.symbol.id}
                icon={<Ghost className="size-3.5 text-text-faint" />}
                title={f.symbol.qualified_name}
                subtitle={`${f.symbol.file_path}:${f.symbol.start_line} — ${f.reason}`}
                onClick={() => onOpenSymbol(f.symbol.file_path, f.symbol.start_line)}
              />
            )}
          />
        )}

        {tab === "complexity" && (
          <List
            empty="Nothing stands out — no unusually complex functions found."
            items={data.complexity_hotspots}
            renderItem={(h) => (
              <Row
                key={h.symbol.id}
                icon={
                  <span
                    className={`flex size-5 items-center justify-center rounded text-[10px] font-semibold ${
                      h.complexity >= 10 ? "bg-danger-soft text-danger" : h.complexity >= 6 ? "bg-warn-soft text-warn" : "bg-surface-raised text-text-muted"
                    }`}
                  >
                    {h.complexity}
                  </span>
                }
                title={h.symbol.qualified_name}
                subtitle={`${h.symbol.file_path}:${h.symbol.start_line} — ${h.line_count} lines`}
                onClick={() => onOpenSymbol(h.symbol.file_path, h.symbol.start_line)}
              />
            )}
          />
        )}

        {tab === "security" && (
          <List
            empty="No findings — either it's clean, or nothing matched the scan's rule set."
            items={data.security_findings}
            renderItem={(s, i) => (
              <Row
                key={i}
                icon={<ShieldAlert className="size-3.5 text-text-faint" />}
                title={s.rule}
                subtitle={`${s.file_path}:${s.line} — ${s.message}`}
                badge={
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${SEVERITY_STYLE[s.severity]}`}>
                    {s.severity}
                  </span>
                }
                onClick={() => onOpenSymbol(s.file_path, s.line)}
              />
            )}
          />
        )}
      </div>
    </div>
  );
}

function List<T>({
  items,
  empty,
  renderItem,
}: {
  items: T[];
  empty: string;
  renderItem: (item: T, i: number) => React.ReactNode;
}) {
  if (items.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-text-faint">
        <AlertTriangle className="size-4" />
        <p className="max-w-xs text-xs">{empty}</p>
      </div>
    );
  }
  return <div className="space-y-1">{items.map(renderItem)}</div>;
}

function Row({
  icon,
  title,
  subtitle,
  badge,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  badge?: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-surface-hover"
    >
      <div className="mt-0.5">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-mono text-[12.5px] text-text">{title}</p>
          {badge}
        </div>
        <p className="mt-0.5 truncate text-[11.5px] text-text-faint">{subtitle}</p>
      </div>
    </button>
  );
}
