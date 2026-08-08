interface Node {
  x: number;
  y: number;
  r: number;
  color: "accent" | "warn" | "danger";
  delay: number;
}

const NODES: Node[] = [
  { x: 60, y: 90, r: 5, color: "accent", delay: 0 },
  { x: 160, y: 40, r: 7, color: "accent", delay: 0.3 },
  { x: 260, y: 100, r: 4, color: "accent", delay: 0.6 },
  { x: 150, y: 150, r: 6, color: "warn", delay: 0.9 },
  { x: 320, y: 60, r: 5, color: "accent", delay: 1.2 },
  { x: 340, y: 160, r: 4, color: "danger", delay: 1.5 },
  { x: 40, y: 180, r: 4, color: "accent", delay: 1.8 },
  { x: 230, y: 190, r: 5, color: "accent", delay: 2.1 },
];

const EDGES: [number, number][] = [
  [0, 1],
  [1, 2],
  [1, 3],
  [2, 4],
  [2, 5],
  [3, 6],
  [3, 7],
  [4, 5],
];

const COLOR_VAR: Record<Node["color"], string> = {
  accent: "var(--color-accent)",
  warn: "var(--color-warn)",
  danger: "var(--color-danger)",
};

export default function ConstellationArt() {
  return (
    <svg viewBox="0 0 380 230" className="h-full w-full" aria-hidden="true">
      {EDGES.map(([a, b], i) => {
        const na = NODES[a];
        const nb = NODES[b];
        return (
          <line
            key={i}
            x1={na.x}
            y1={na.y}
            x2={nb.x}
            y2={nb.y}
            stroke="var(--color-border)"
            strokeWidth={1}
            className="animate-draw-edge"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        );
      })}
      {NODES.map((n, i) => (
        <circle
          key={i}
          cx={n.x}
          cy={n.y}
          r={n.r}
          fill={COLOR_VAR[n.color]}
          className="animate-pulse-node"
          style={{ animationDelay: `${n.delay}s` }}
        />
      ))}
    </svg>
  );
}
