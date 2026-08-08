"""
"Zero incoming CALLS edges" (graph_store.unreferenced_symbols) is a starting
point, not an answer -- plenty of legitimately-used code has no *in-repo*
caller: route handlers invoked by a framework, dunder methods invoked by the
language runtime, test functions invoked by a test runner, CLI entry points.
This module filters those out and returns what's left as dead-code
candidates, each with a plain-language reason.

This is the same category of heuristic real tools use (vulture for Python,
ts-prune for TypeScript): a static, non-dynamic-dispatch-aware signal that
is useful for triage, not a proof of unreachability. Framework magic
(dependency injection, string-based routing, reflection) can still produce
false positives; the confidence field says which edges the finding rests on.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.storage.graph_store import GraphNode, GraphStore

DUNDER_PREFIX_SUFFIX = "__"

# Decorators that mean "the framework calls this for you" -- seeing any of
# these substrings on a symbol means it's an entrypoint, not dead code.
ENTRYPOINT_DECORATOR_HINTS = (
    "route", "get", "post", "put", "patch", "delete", "websocket",
    "task", "shared_task", "periodic_task", "listener", "handler",
    "fixture", "hook", "cli", "command", "app.", "click", "event",
)

ENTRYPOINT_NAME_HINTS = {"main", "__main__", "setup", "teardown", "constructor"}


def _looks_like_dunder(name: str) -> bool:
    return name.startswith(DUNDER_PREFIX_SUFFIX) and name.endswith(DUNDER_PREFIX_SUFFIX)


def _is_test_file(file_path: str) -> bool:
    lower = file_path.lower()
    return "test" in lower.split("/") or lower.split("/")[-1].startswith("test_") or lower.endswith(
        (".test.ts", ".test.js", ".spec.ts", ".spec.js")
    )


@dataclass
class DeadCodeFinding:
    node: GraphNode
    reason: str


def _is_likely_entrypoint(node: GraphNode, decorators: list[str]) -> str | None:
    if _looks_like_dunder(node.name):
        return None  # not a finding at all -- dunders aren't "dead", skip silently
    if node.name in ENTRYPOINT_NAME_HINTS:
        return "invoked implicitly by the language runtime or framework (e.g. main/constructor), not by an explicit call"
    if _is_test_file(node.file_path):
        return "defined in a test file -- likely invoked by the test runner"
    for dec in decorators:
        lowered = dec.lower()
        if any(hint in lowered for hint in ENTRYPOINT_DECORATOR_HINTS):
            return f"decorated with {dec.strip()}, likely invoked by a framework"
    return None


async def find_dead_code(
    graph_store: GraphStore, repo_id: str, decorators_by_symbol_id: dict[str, list[str]]
) -> list[DeadCodeFinding]:
    candidates = await graph_store.unreferenced_symbols(repo_id)
    findings: list[DeadCodeFinding] = []
    for node in candidates:
        if _looks_like_dunder(node.name):
            continue
        decorators = decorators_by_symbol_id.get(node.id, [])
        likely_entrypoint_reason = _is_likely_entrypoint(node, decorators)
        if likely_entrypoint_reason is not None:
            continue
        reason = "no calls to it were found anywhere else in the indexed codebase"
        findings.append(DeadCodeFinding(node=node, reason=reason))
    return findings
