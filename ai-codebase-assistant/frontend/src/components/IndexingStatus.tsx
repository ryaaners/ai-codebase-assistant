import { Loader2 } from "lucide-react";
import type { RepoSummary } from "@/types";

export default function IndexingStatus({ repo }: { repo: RepoSummary }) {
  if (repo.status === "failed") {
    return (
      <div className="border-b border-danger/30 bg-danger-soft px-5 py-2.5 text-sm text-danger">
        Indexing failed: {repo.error_message ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 border-b border-warn/30 bg-warn-soft px-5 py-2.5 text-sm text-warn">
      <Loader2 className="size-3.5 animate-spin" />
      {repo.status === "pending" ? "Queued for indexing…" : "Parsing, building the graph, and embedding symbols…"}
      <span className="text-warn/70">This page updates automatically.</span>
    </div>
  );
}
