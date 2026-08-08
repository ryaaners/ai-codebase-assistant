export type RepoStatus = "pending" | "indexing" | "ready" | "failed";

export interface RepoSummary {
  id: string;
  name: string;
  source_type: "github" | "zip";
  source: string;
  status: RepoStatus;
  error_message: string | null;
  primary_language: string | null;
  languages: Record<string, number>;
  file_count: number;
  symbol_count: number;
  created_at: string;
  indexed_at: string | null;
}

export interface FileNode {
  path: string;
  name: string;
  is_dir: boolean;
  language: string | null;
  children: FileNode[];
}

export type SymbolKind = "function" | "method" | "class" | "interface" | "file";

export interface SymbolOut {
  id: string;
  kind: SymbolKind;
  name: string;
  qualified_name: string;
  file_path: string;
  start_line: number;
  end_line: number;
  signature: string;
  docstring: string | null;
  summary: string | null;
  complexity: number | null;
}

export interface FileContent {
  path: string;
  language: string | null;
  content: string;
  symbols: SymbolOut[];
}

export interface CitationOut {
  file_path: string;
  symbol_name: string;
  kind: string;
  start_line: number;
  end_line: number;
}

export interface ChatResponse {
  answer: string;
  mode: "generated" | "extractive";
  citations: CitationOut[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: CitationOut[];
  mode?: "generated" | "extractive";
}

export interface GraphNodeOut {
  id: string;
  kind: string;
  name: string;
  qualified_name: string;
  file_path: string;
  start_line: number;
  end_line: number;
}

export interface GraphEdgeOut {
  source: string;
  target: string;
  kind: "CALLS" | "IMPORTS" | "INHERITS" | "CONTAINS";
  confidence: "exact" | "same_file" | "heuristic";
}

export interface GraphOut {
  nodes: GraphNodeOut[];
  edges: GraphEdgeOut[];
}

export interface SymbolNeighborsOut {
  symbol: SymbolOut;
  callers: SymbolOut[];
  callees: SymbolOut[];
}

export interface DeadCodeFindingOut {
  symbol: SymbolOut;
  reason: string;
}

export interface ComplexityHotspotOut {
  symbol: SymbolOut;
  complexity: number;
  line_count: number;
}

export interface SecurityFindingOut {
  file_path: string;
  line: number;
  severity: "LOW" | "MEDIUM" | "HIGH";
  confidence: string;
  rule: string;
  message: string;
}

export interface AnalysisOut {
  dead_code: DeadCodeFindingOut[];
  complexity_hotspots: ComplexityHotspotOut[];
  security_findings: SecurityFindingOut[];
}

export interface CodeReviewResponse {
  review: string;
  mode: string;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}
