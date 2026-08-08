import type {
  AnalysisOut,
  ChatResponse,
  CodeReviewResponse,
  FileContent,
  FileNode,
  GraphOut,
  RepoSummary,
  SymbolNeighborsOut,
} from "@/types";
import { ApiError } from "@/types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers:
      init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json", ...init.headers }
        : init?.headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* response wasn't JSON -- fall back to statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listRepos: () => request<RepoSummary[]>("/api/repos"),

  getRepo: (repoId: string) => request<RepoSummary>(`/api/repos/${repoId}`),

  cloneRepo: (url: string) =>
    request<RepoSummary>("/api/repos/clone", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  uploadRepo: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<RepoSummary>("/api/repos/upload", { method: "POST", body: form });
  },

  deleteRepo: (repoId: string) => request<void>(`/api/repos/${repoId}`, { method: "DELETE" }),

  getFileTree: (repoId: string) => request<FileNode[]>(`/api/repos/${repoId}/files`),

  getFileContent: (repoId: string, path: string) =>
    request<FileContent>(`/api/repos/${repoId}/files/content?path=${encodeURIComponent(path)}`),

  chat: (repoId: string, question: string) =>
    request<ChatResponse>(`/api/repos/${repoId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    }),

  getGraph: (repoId: string, kind?: string) =>
    request<GraphOut>(`/api/repos/${repoId}/graph${kind ? `?kind=${kind}` : ""}`),

  getSymbolNeighbors: (repoId: string, symbolId: string) =>
    request<SymbolNeighborsOut>(`/api/repos/${repoId}/graph/symbols/${symbolId}/neighbors`),

  getAnalysis: (repoId: string) => request<AnalysisOut>(`/api/repos/${repoId}/analysis`),

  reviewCode: (repoId: string, code: string, language?: string) =>
    request<CodeReviewResponse>(`/api/repos/${repoId}/review`, {
      method: "POST",
      body: JSON.stringify({ code, language }),
    }),
};
