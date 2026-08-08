import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { RepoSummary } from "@/types";

export function useRepoPolling(repoId: string) {
  const [repo, setRepo] = useState<RepoSummary | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const data = await api.getRepo(repoId);
        if (cancelled) return;
        setRepo(data);
        if (data.status === "pending" || data.status === "indexing") {
          timer = setTimeout(tick, 1500);
        }
      } catch {
        if (!cancelled) setNotFound(true);
      }
    }
    tick();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [repoId]);

  return { repo, notFound };
}
