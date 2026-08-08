import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Code2, MessageSquare, Network, ShieldCheck } from "lucide-react";
import { api } from "@/api/client";
import { useRepoPolling } from "@/hooks/useRepoPolling";
import type { ChatMessage, CitationOut, FileNode } from "@/types";
import StatusBadge from "@/components/StatusBadge";
import IndexingStatus from "@/components/IndexingStatus";
import FileExplorer from "@/components/FileExplorer";
import CodeViewer from "@/components/CodeViewer";
import ChatPanel from "@/components/ChatPanel";
import GraphView from "@/components/GraphView";
import AnalysisPanel from "@/components/AnalysisPanel";

type Tab = "chat" | "code" | "graph" | "analysis";

export default function Workspace() {
  const { repoId } = useParams<{ repoId: string }>();
  const navigate = useNavigate();
  const { repo, notFound } = useRepoPolling(repoId!);

  const [tree, setTree] = useState<FileNode[]>([]);
  const [tab, setTab] = useState<Tab>("chat");
  const [openFile, setOpenFile] = useState<{ path: string; line: number | null } | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  useEffect(() => {
    if (!repoId) return;
    api.getFileTree(repoId).then(setTree).catch(() => {});
  }, [repoId, repo?.status]);

  function openSymbol(path: string, line: number) {
    setOpenFile({ path, line });
    setTab("code");
  }

  async function handleSend(question: string) {
    if (!repoId) return;
    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", text: question };
    setMessages((prev) => [...prev, userMsg]);
    setChatLoading(true);
    try {
      const res = await api.chat(repoId, question);
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", text: res.answer, citations: res.citations, mode: res.mode },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: err instanceof Error ? err.message : "Something went wrong answering that.",
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  function handleCitationClick(citation: CitationOut) {
    openSymbol(citation.file_path, citation.start_line);
  }

  if (notFound) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 bg-bg text-text-muted">
        <p>This repo doesn't exist (or was deleted).</p>
        <button onClick={() => navigate("/")} className="text-sm text-accent-text hover:underline">
          Back to home
        </button>
      </div>
    );
  }

  if (!repo) {
    return <div className="h-screen bg-bg" />;
  }

  const ready = repo.status === "ready";

  const tabs: { id: Tab; label: string; icon: React.ReactNode; disabled?: boolean }[] = [
    { id: "chat", label: "Chat", icon: <MessageSquare className="size-3.5" /> },
    { id: "code", label: "Code", icon: <Code2 className="size-3.5" /> },
    { id: "graph", label: "Graph", icon: <Network className="size-3.5" />, disabled: !ready },
    { id: "analysis", label: "Analysis", icon: <ShieldCheck className="size-3.5" />, disabled: !ready },
  ];

  return (
    <div className="flex h-screen flex-col bg-bg">
      <header className="flex items-center justify-between border-b border-border-soft px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <button onClick={() => navigate("/")} className="text-text-faint hover:text-text">
            <ArrowLeft className="size-4" />
          </button>
          <span className="truncate font-display text-sm font-semibold text-text">{repo.name}</span>
          <StatusBadge status={repo.status} />
        </div>
        {ready && (
          <div className="hidden shrink-0 items-center gap-3 text-xs text-text-faint sm:flex">
            <span>{repo.file_count} files</span>
            <span>·</span>
            <span>{repo.symbol_count} symbols</span>
            {repo.primary_language && (
              <>
                <span>·</span>
                <span className="font-mono">{repo.primary_language}</span>
              </>
            )}
          </div>
        )}
      </header>

      {!ready && <IndexingStatus repo={repo} />}

      <div className="flex min-h-0 flex-1">
        <aside className="w-60 shrink-0 overflow-y-auto border-r border-border-soft py-3">
          {tree.length === 0 ? (
            <p className="px-3 text-xs text-text-faint">
              {repo.status === "failed" ? "Indexing failed." : "Loading files…"}
            </p>
          ) : (
            <FileExplorer
              nodes={tree}
              activePath={openFile?.path ?? null}
              onSelect={(path) => {
                setOpenFile({ path, line: null });
                setTab("code");
              }}
            />
          )}
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="flex gap-1 border-b border-border-soft bg-surface px-3 py-1.5">
            {tabs.map((t) => (
              <button
                key={t.id}
                disabled={t.disabled}
                onClick={() => setTab(t.id)}
                title={t.disabled ? "Available once indexing finishes" : undefined}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  tab === t.id ? "bg-surface-raised text-text" : "text-text-faint hover:text-text-muted"
                } ${t.disabled ? "cursor-not-allowed opacity-40" : ""}`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>

          <div className="min-h-0 flex-1">
            {tab === "chat" &&
              (ready ? (
                <ChatPanel
                  messages={messages}
                  loading={chatLoading}
                  onSend={handleSend}
                  onCitationClick={handleCitationClick}
                />
              ) : (
                <CenteredNote text="Chat will be available once indexing finishes." />
              ))}

            {tab === "code" &&
              (openFile ? (
                <CodeViewer repoId={repoId!} path={openFile.path} focusLine={openFile.line} />
              ) : (
                <CenteredNote text="Select a file from the sidebar to view it." />
              ))}

            {tab === "graph" && ready && <GraphView repoId={repoId!} onOpenSymbol={openSymbol} />}
            {tab === "analysis" && ready && <AnalysisPanel repoId={repoId!} onOpenSymbol={openSymbol} />}
          </div>
        </main>
      </div>
    </div>
  );
}

function CenteredNote({ text }: { text: string }) {
  return (
    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-text-faint">{text}</div>
  );
}
