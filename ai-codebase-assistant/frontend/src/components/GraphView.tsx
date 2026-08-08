import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  type Node,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Loader2 } from "lucide-react";
import { api } from "@/api/client";
import type { GraphOut, SymbolNeighborsOut } from "@/types";
import { layoutGraph } from "./graphLayout";

interface Props {
  repoId: string;
  onOpenSymbol: (filePath: string, line: number) => void;
}

const KIND_COLOR: Record<string, string> = {
  class: "#f5a623",
  interface: "#f5a623",
  method: "#2dd4bf",
  function: "#2dd4bf",
  file: "#8b93a1",
};

const EDGE_COLOR: Record<string, string> = {
  CALLS: "#2dd4bf",
  IMPORTS: "#565e6b",
  INHERITS: "#f5a623",
  CONTAINS: "#242a33",
};

export default function GraphView({ repoId, onOpenSymbol }: Props) {
  const [view, setView] = useState<"symbols" | "files">("symbols");
  const [graph, setGraph] = useState<GraphOut | null>(null);
  const [selected, setSelected] = useState<SymbolNeighborsOut | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    api
      .getGraph(repoId, view === "files" ? "file" : undefined)
      .then((g) => setGraph(view === "files" ? g : { ...g, nodes: g.nodes.filter((n) => n.kind !== "file") }))
      .finally(() => setLoading(false));
  }, [repoId, view]);

  const { nodes, edges } = useMemo<{ nodes: Node[]; edges: Edge[] }>(() => {
    if (!graph) return { nodes: [], edges: [] };
    const visibleIds = new Set(graph.nodes.map((n) => n.id));
    const visibleEdges = graph.edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));
    const positioned = layoutGraph(graph.nodes, visibleEdges);

    const flowNodes: Node[] = positioned.map((n) => ({
      id: n.id,
      position: { x: n.x, y: n.y },
      data: { label: n.name, kind: n.kind },
      style: {
        background: "#12151a",
        border: `1.5px solid ${KIND_COLOR[n.kind] ?? "#242a33"}`,
        borderRadius: 8,
        color: "#e8eaed",
        fontSize: 12,
        fontFamily: "'JetBrains Mono', monospace",
        padding: "6px 10px",
        width: 190,
      },
    }));

    const flowEdges: Edge[] = visibleEdges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      animated: e.kind === "CALLS",
      style: {
        stroke: EDGE_COLOR[e.kind] ?? "#242a33",
        strokeWidth: e.confidence === "heuristic" ? 1 : 1.5,
        strokeDasharray: e.confidence === "heuristic" ? "3 3" : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: EDGE_COLOR[e.kind] ?? "#242a33", width: 14, height: 14 },
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [graph]);

  async function handleNodeClick(_: unknown, node: Node) {
    if (view === "files") return;
    const neighbors = await api.getSymbolNeighbors(repoId, node.id);
    setSelected(neighbors);
  }

  return (
    <div className="relative flex h-full">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 border-b border-border-soft bg-surface px-4 py-2">
          <div className="flex gap-1 rounded-md border border-border bg-bg p-0.5">
            {(["symbols", "files"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                  view === v ? "bg-surface-raised text-text" : "text-text-faint hover:text-text-muted"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
          <span className="text-xs text-text-faint">
            {graph ? `${graph.nodes.length} nodes · ${graph.edges.length} edges` : ""}
          </span>
        </div>

        {loading ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="size-5 animate-spin text-text-faint" />
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-text-faint">
            No {view} found for this repo.
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            fitView
            colorMode="dark"
            proOptions={{ hideAttribution: true }}
          >
            <Background color="#1a1f26" gap={20} />
            <Controls showInteractive={false} />
          </ReactFlow>
        )}
      </div>

      {selected && (
        <div className="w-72 shrink-0 overflow-y-auto border-l border-border-soft bg-surface p-4">
          <button onClick={() => setSelected(null)} className="mb-3 text-xs text-text-faint hover:text-text">
            Close
          </button>
          <p className="font-mono text-[13px] font-medium text-text">{selected.symbol.qualified_name}</p>
          <p className="mt-0.5 font-mono text-[11px] text-text-faint">
            {selected.symbol.file_path}:{selected.symbol.start_line}
          </p>
          <button
            onClick={() => onOpenSymbol(selected.symbol.file_path, selected.symbol.start_line)}
            className="mt-2 rounded-md border border-border px-2.5 py-1 text-xs text-text-muted hover:border-accent/40 hover:text-accent-text"
          >
            View code
          </button>

          <div className="mt-5">
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-text-faint">
              Called by ({selected.callers.length})
            </p>
            {selected.callers.length === 0 && <p className="text-xs text-text-faint">Nothing found in this repo.</p>}
            {selected.callers.map((c) => (
              <button
                key={c.id}
                onClick={() => onOpenSymbol(c.file_path, c.start_line)}
                className="block w-full truncate rounded px-1.5 py-1 text-left font-mono text-[12px] text-text-muted hover:bg-surface-hover hover:text-text"
              >
                {c.qualified_name}
              </button>
            ))}
          </div>

          <div className="mt-4">
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-text-faint">
              Calls ({selected.callees.length})
            </p>
            {selected.callees.length === 0 && <p className="text-xs text-text-faint">Nothing found in this repo.</p>}
            {selected.callees.map((c) => (
              <button
                key={c.id}
                onClick={() => onOpenSymbol(c.file_path, c.start_line)}
                className="block w-full truncate rounded px-1.5 py-1 text-left font-mono text-[12px] text-text-muted hover:bg-surface-hover hover:text-text"
              >
                {c.qualified_name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
