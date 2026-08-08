"""
Turns the per-file output of extractor.py into a whole-repo graph: CONTAINS
(class -> method), INHERITS (class -> base class), CALLS (caller -> callee),
and IMPORTS (file -> file).

Call and import resolution are both name/path matching, not semantic
analysis -- see extractor.py's module docstring for why that tradeoff is
fine for this product. Every CALLS edge gets a `confidence`:
  - "exact": callee name matches exactly one symbol in the repo
  - "same_file": multiple symbols share that name repo-wide, but exactly
    one lives in the caller's file, so we prefer it
  - "heuristic": still ambiguous after that -- we pick the first candidate
    (stable order) so results are reproducible, but the UI should show
    this edge as lower-confidence
Calls to names that aren't defined anywhere in the repo (stdlib, third-party
packages) simply produce no edge -- there's no candidate to point at, which
is exactly the graph we want ("who calls what in *this* codebase").
"""
from __future__ import annotations

import hashlib
import os
import posixpath

from app.core.extractor import FileExtraction, Symbol
from app.core.storage.graph_store import GraphEdge, GraphNode

JS_RESOLVE_EXTENSIONS = ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")
PY_ROOTS_TO_TRY = ("", "src/", "app/")


def _file_node_id(repo_id: str, file_path: str) -> str:
    return "file:" + hashlib.sha1(f"{repo_id}:{file_path}".encode()).hexdigest()[:16]


def _pick_target(candidates: list[Symbol], caller_file: str) -> tuple[Symbol | None, str]:
    if not candidates:
        return None, "heuristic"
    if len(candidates) == 1:
        return candidates[0], "exact"
    same_file = [c for c in candidates if c.file_path == caller_file]
    if len(same_file) == 1:
        return same_file[0], "same_file"
    return sorted(candidates, key=lambda c: (c.file_path, c.start_line))[0], "heuristic"


def _resolve_python_import(source: str, all_files: set[str]) -> str | None:
    as_path = source.replace(".", "/")
    for root in PY_ROOTS_TO_TRY:
        for suffix in (".py", "/__init__.py"):
            candidate = f"{root}{as_path}{suffix}"
            if candidate in all_files:
                return candidate
    return None


def _resolve_js_import(source: str, importer_file: str, all_files: set[str]) -> str | None:
    if not source.startswith("."):
        return None  # bare specifier ("react", "lodash") -> external package, not in-repo
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer_file), source))
    for suffix in JS_RESOLVE_EXTENSIONS:
        candidate = base + suffix if suffix and not suffix.startswith("/") else base + suffix
        if candidate in all_files:
            return candidate
    return None


def build_graph(
    repo_id: str, extractions: list[FileExtraction], all_file_paths: list[str]
) -> tuple[list[GraphNode], list[GraphEdge]]:
    all_files = set(all_file_paths)
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    qualified_to_symbol: dict[str, Symbol] = {}
    by_name: dict[str, list[Symbol]] = {}
    for ext in extractions:
        for sym in ext.symbols:
            qualified_to_symbol[sym.qualified_name] = sym
            by_name.setdefault(sym.name, []).append(sym)
            nodes.append(
                GraphNode(
                    id=sym.id, repo_id=repo_id, kind=sym.kind, name=sym.name,
                    qualified_name=sym.qualified_name, file_path=sym.file_path,
                    start_line=sym.start_line, end_line=sym.end_line,
                )
            )

    # File nodes, one per parsed file, so IMPORTS has something to point between.
    file_node_id: dict[str, str] = {}
    for ext in extractions:
        fid = _file_node_id(repo_id, ext.file_path)
        file_node_id[ext.file_path] = fid
        nodes.append(
            GraphNode(
                id=fid, repo_id=repo_id, kind="file", name=posixpath.basename(ext.file_path),
                qualified_name=ext.file_path, file_path=ext.file_path, start_line=1, end_line=ext.loc,
            )
        )

    # CONTAINS: class -> method/nested symbol
    for ext in extractions:
        for sym in ext.symbols:
            if sym.parent_qualified_name and sym.parent_qualified_name in qualified_to_symbol:
                parent = qualified_to_symbol[sym.parent_qualified_name]
                edges.append(GraphEdge(parent.id, sym.id, "CONTAINS"))

    # INHERITS: class -> base class (by unqualified name; same ambiguity
    # tradeoff as CALLS below)
    for ext in extractions:
        for sym in ext.symbols:
            if sym.kind != "class":
                continue
            for base in sym.bases:
                base_name = base.split(".")[-1].split("(")[0].strip()
                if not base_name:
                    continue
                target, confidence = _pick_target(by_name.get(base_name, []), sym.file_path)
                if target and target.id != sym.id:
                    edges.append(GraphEdge(sym.id, target.id, "INHERITS", confidence))

    # CALLS: caller symbol -> callee symbol, resolved by name
    for ext in extractions:
        local_qualified_ids = {s.qualified_name: s.id for s in ext.symbols}
        for call in ext.calls:
            if call.caller_qualified_name is None:
                continue  # module-level statements aren't attributed to a symbol
            caller_id = local_qualified_ids.get(call.caller_qualified_name)
            if caller_id is None:
                continue
            target, confidence = _pick_target(by_name.get(call.callee_name, []), call.file_path)
            if target is None or target.id == caller_id:
                continue
            edges.append(GraphEdge(caller_id, target.id, "CALLS", confidence))

    # IMPORTS: file -> file, resolved by path (python) or relative specifier (js/ts)
    for ext in extractions:
        source_fid = file_node_id.get(ext.file_path)
        if source_fid is None:
            continue
        for imp in ext.imports:
            if ext.language == "python":
                resolved = _resolve_python_import(imp.source, all_files)
            else:
                resolved = _resolve_js_import(imp.source, ext.file_path, all_files)
            if resolved and resolved in file_node_id and resolved != ext.file_path:
                edges.append(GraphEdge(source_fid, file_node_id[resolved], "IMPORTS"))

    return nodes, edges
