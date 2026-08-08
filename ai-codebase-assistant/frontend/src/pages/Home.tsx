import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitBranch, Loader2, Trash2, Upload } from "lucide-react";
import { api } from "@/api/client";
import type { RepoSummary } from "@/types";
import { ApiError } from "@/types";
import ConstellationArt from "@/components/ConstellationArt";
import StatusBadge from "@/components/StatusBadge";

type Mode = "upload" | "github";

export default function Home() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("github");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listRepos().then(setRepos).catch(() => {});
  }, []);

  async function handleClone(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const repo = await api.cloneRepo(url.trim());
      navigate(`/repos/${repo.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpload(file: File) {
    setSubmitting(true);
    setError(null);
    try {
      const repo = await api.uploadRepo(file);
      navigate(`/repos/${repo.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    await api.deleteRepo(id);
    setRepos((prev) => prev.filter((r) => r.id !== id));
  }

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border-soft px-8 py-5">
        <div className="mx-auto flex max-w-5xl items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-md bg-accent-soft text-accent-text">
            <svg viewBox="0 0 24 24" className="size-4" fill="none">
              <path
                d="M4 6h16M4 12h10M4 18h16"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <span className="font-display text-[15px] font-semibold tracking-tight">
            AI Codebase Assistant
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-8 py-16">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_360px]">
          <div>
            <h1 className="font-display text-4xl font-semibold leading-tight tracking-tight text-text sm:text-5xl">
              Understand any codebase
              <br />
              <span className="text-text-muted">before you read a line.</span>
            </h1>
            <p className="mt-4 max-w-md text-[15px] leading-relaxed text-text-muted">
              Connect a repo. It's parsed, graphed, and embedded in the background —
              then you can ask it questions in plain language, with answers grounded
              in the actual call graph.
            </p>

            <div className="mt-8 max-w-md">
              <div className="flex gap-1 rounded-lg border border-border bg-surface p-1">
                <button
                  onClick={() => setMode("github")}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    mode === "github" ? "bg-surface-raised text-text" : "text-text-muted hover:text-text"
                  }`}
                >
                  <GitBranch className="size-4" /> GitHub URL
                </button>
                <button
                  onClick={() => setMode("upload")}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    mode === "upload" ? "bg-surface-raised text-text" : "text-text-muted hover:text-text"
                  }`}
                >
                  <Upload className="size-4" /> Upload ZIP
                </button>
              </div>

              <div className="mt-4">
                {mode === "github" ? (
                  <form onSubmit={handleClone} className="flex gap-2">
                    <input
                      value={url}
                      onChange={(e) => setUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="flex-1 rounded-lg border border-border bg-surface px-3.5 py-2.5 font-mono text-sm text-text placeholder:text-text-faint focus:border-accent focus:outline-none"
                    />
                    <button
                      type="submit"
                      disabled={submitting || !url.trim()}
                      className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-bg transition-opacity hover:opacity-90 disabled:opacity-40"
                    >
                      {submitting && <Loader2 className="size-4 animate-spin" />}
                      Index
                    </button>
                  </form>
                ) : (
                  <div
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDragOver(false);
                      const file = e.dataTransfer.files[0];
                      if (file) void handleUpload(file);
                    }}
                    onClick={() => fileInputRef.current?.click()}
                    className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-8 text-center transition-colors ${
                      dragOver ? "border-accent bg-accent-soft/40" : "border-border bg-surface hover:border-text-faint"
                    }`}
                  >
                    {submitting ? (
                      <Loader2 className="size-5 animate-spin text-accent" />
                    ) : (
                      <Upload className="size-5 text-text-muted" />
                    )}
                    <p className="text-sm text-text-muted">
                      Drop a <span className="font-mono text-text">.zip</span> of your repo, or click to browse
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".zip"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) void handleUpload(file);
                      }}
                    />
                  </div>
                )}
                {error && <p className="mt-2.5 text-sm text-danger">{error}</p>}
              </div>
            </div>
          </div>

          <div className="hidden aspect-square items-center justify-center rounded-2xl border border-border-soft bg-surface/50 lg:flex">
            <div className="h-56 w-full p-6">
              <ConstellationArt />
            </div>
          </div>
        </div>

        {repos.length > 0 && (
          <div className="mt-20">
            <h2 className="mb-4 font-display text-sm font-semibold uppercase tracking-wide text-text-faint">
              Previously indexed
            </h2>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {repos.map((repo) => (
                <a
                  key={repo.id}
                  href={`/repos/${repo.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`/repos/${repo.id}`);
                  }}
                  className="group flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3.5 transition-colors hover:border-text-faint"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-text">{repo.name}</p>
                    <p className="mt-0.5 truncate font-mono text-xs text-text-faint">
                      {repo.file_count} files · {repo.symbol_count} symbols
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <StatusBadge status={repo.status} />
                    <button
                      onClick={(e) => handleDelete(repo.id, e)}
                      className="text-text-faint opacity-0 transition-opacity hover:text-danger group-hover:opacity-100"
                      aria-label="Delete repo"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                </a>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
