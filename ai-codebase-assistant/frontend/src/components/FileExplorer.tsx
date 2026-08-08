import { useState } from "react";
import { ChevronRight, File, FileCode2, Folder, FolderOpen } from "lucide-react";
import type { FileNode } from "@/types";

interface Props {
  nodes: FileNode[];
  activePath: string | null;
  onSelect: (path: string) => void;
  depth?: number;
}

const CODE_EXTENSIONS = [".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"];

function isCodeFile(name: string) {
  return CODE_EXTENSIONS.some((ext) => name.endsWith(ext));
}

export default function FileExplorer({ nodes, activePath, onSelect, depth = 0 }: Props) {
  return (
    <ul className={depth === 0 ? "select-none" : "select-none border-l border-border-soft"}>
      {nodes.map((node) => (
        <TreeNode key={node.path} node={node} activePath={activePath} onSelect={onSelect} depth={depth} />
      ))}
    </ul>
  );
}

function TreeNode({
  node,
  activePath,
  onSelect,
  depth,
}: {
  node: FileNode;
  activePath: string | null;
  onSelect: (path: string) => void;
  depth: number;
}) {
  const [open, setOpen] = useState(depth < 1);
  const isActive = node.path === activePath;

  if (node.is_dir) {
    return (
      <li>
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[13px] text-text-muted hover:bg-surface-hover hover:text-text"
          style={{ paddingLeft: `${depth * 12 + 8}px` }}
        >
          <ChevronRight className={`size-3.5 shrink-0 transition-transform ${open ? "rotate-90" : ""}`} />
          {open ? <FolderOpen className="size-3.5 shrink-0 text-text-faint" /> : <Folder className="size-3.5 shrink-0 text-text-faint" />}
          <span className="truncate">{node.name}</span>
        </button>
        {open && node.children.length > 0 && (
          <FileExplorer nodes={node.children} activePath={activePath} onSelect={onSelect} depth={depth + 1} />
        )}
      </li>
    );
  }

  return (
    <li>
      <button
        onClick={() => onSelect(node.path)}
        className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[13px] transition-colors ${
          isActive ? "bg-accent-soft text-accent-text" : "text-text-muted hover:bg-surface-hover hover:text-text"
        }`}
        style={{ paddingLeft: `${depth * 12 + 26}px` }}
      >
        {isCodeFile(node.name) ? (
          <FileCode2 className="size-3.5 shrink-0 opacity-70" />
        ) : (
          <File className="size-3.5 shrink-0 opacity-50" />
        )}
        <span className="truncate font-mono text-[12.5px]">{node.name}</span>
      </button>
    </li>
  );
}
