import type { GraphEdgeOut, GraphNodeOut } from "@/types";

export interface PositionedNode extends GraphNodeOut {
  x: number;
  y: number;
}

const LAYER_WIDTH = 260;
const ROW_HEIGHT = 84;

/**
 * Assigns each node a layer via Kahn's algorithm (longest-path-from-a-root
 * layering), then stacks nodes within a layer vertically. Not force-
 * directed and won't untangle a dense graph, but for a call graph -- which
 * is mostly a DAG with a handful of back-edges from recursion -- a left-
 * to-right "who calls what" layering is more readable than a generic
 * physics layout would be, and needs no extra dependency.
 */
export function layoutGraph(nodes: GraphNodeOut[], edges: GraphEdgeOut[]): PositionedNode[] {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const outgoing = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  nodes.forEach((n) => {
    outgoing.set(n.id, []);
    inDegree.set(n.id, 0);
  });
  edges.forEach((e) => {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target) || e.source === e.target) return;
    outgoing.get(e.source)!.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  });

  const layer = new Map<string, number>();
  const queue: string[] = [];
  nodes.forEach((n) => {
    if ((inDegree.get(n.id) ?? 0) === 0) {
      layer.set(n.id, 0);
      queue.push(n.id);
    }
  });

  // Any node not reachable from a zero-in-degree root (i.e. purely cyclic
  // components) still needs a layer -- seed those separately so they don't
  // get silently dropped.
  const visited = new Set(queue);
  let head = 0;
  while (head < queue.length) {
    const current = queue[head++];
    const currentLayer = layer.get(current) ?? 0;
    for (const next of outgoing.get(current) ?? []) {
      const candidate = currentLayer + 1;
      if ((layer.get(next) ?? -1) < candidate) layer.set(next, candidate);
      if (!visited.has(next)) {
        visited.add(next);
        queue.push(next);
      }
    }
  }
  nodes.forEach((n) => {
    if (!layer.has(n.id)) layer.set(n.id, 0);
  });

  const byLayer = new Map<number, string[]>();
  nodes.forEach((n) => {
    const l = layer.get(n.id) ?? 0;
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l)!.push(n.id);
  });

  const positions = new Map<string, { x: number; y: number }>();
  [...byLayer.entries()]
    .sort(([a], [b]) => a - b)
    .forEach(([l, ids]) => {
      ids.forEach((id, i) => {
        positions.set(id, { x: l * LAYER_WIDTH, y: i * ROW_HEIGHT - ((ids.length - 1) * ROW_HEIGHT) / 2 });
      });
    });

  return nodes.map((n) => ({ ...n, ...(positions.get(n.id) ?? { x: 0, y: 0 }) }));
}
