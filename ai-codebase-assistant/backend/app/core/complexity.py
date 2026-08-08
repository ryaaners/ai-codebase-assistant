"""
Cyclomatic complexity, computed directly off the AST rather than shelling
out to a per-language tool: count 1 + one per decision point (branches,
loops, boolean operators, exception handlers) within a symbol's body.
Same metric definition McCabe(1976) uses; same one `radon`/`eslint
complexity` report, just computed once here across every language we
already parse instead of needing a separate tool per language.
"""
from __future__ import annotations

from dataclasses import dataclass

from tree_sitter import Node

from app.core.extractor import Symbol
from app.core.parser import ParsedFile

DECISION_NODE_TYPES = {
    # branching
    "if_statement", "elif_clause", "else_clause", "conditional_expression",
    "ternary_expression", "case_clause", "switch_case", "switch_default",
    # loops
    "for_statement", "for_in_statement", "for_in_clause", "while_statement", "do_statement",
    # exceptions
    "except_clause", "catch_clause",
    # boolean short-circuit adds a path
    "boolean_operator", "binary_expression",
}
BOOLEAN_OPERATORS = {"and", "or", "&&", "||"}


@dataclass
class ComplexityResult:
    symbol_id: str
    qualified_name: str
    file_path: str
    complexity: int
    line_count: int
    max_nesting_depth: int


def _decision_count(node: Node) -> int:
    count = 0
    if node.type in ("boolean_operator", "binary_expression"):
        op_child = node.child_by_field_name("operator")
        if op_child is not None and op_child.type in BOOLEAN_OPERATORS:
            count += 1
    elif node.type in DECISION_NODE_TYPES:
        count += 1
    for child in node.children:
        count += _decision_count(child)
    return count


def _max_nesting(node: Node, current: int = 0) -> int:
    nesting_types = {
        "if_statement", "for_statement", "for_in_statement", "while_statement",
        "do_statement", "try_statement", "switch_statement",
    }
    next_level = current + 1 if node.type in nesting_types else current
    if not node.children:
        return next_level
    return max(_max_nesting(c, next_level) for c in node.children)


def compute_complexity(pf: ParsedFile, symbols: list[Symbol]) -> list[ComplexityResult]:
    root = pf.tree.root_node
    results = []
    for sym in symbols:
        if sym.kind not in ("function", "method"):
            continue
        # Byte-exact lookup -- a point-range lookup keyed on (line, column 0)
        # would land in leading indentation whenever the def isn't at column
        # 0, which resolves to the *enclosing* block instead of the function
        # itself and silently inflates every sibling's score to match.
        node = root.descendant_for_byte_range(sym.start_byte, sym.end_byte)
        if node is None:
            continue
        complexity = 1 + _decision_count(node)
        results.append(
            ComplexityResult(
                symbol_id=sym.id, qualified_name=sym.qualified_name, file_path=sym.file_path,
                complexity=complexity, line_count=sym.end_line - sym.start_line + 1,
                max_nesting_depth=_max_nesting(node),
            )
        )
    return results


def rank_hotspots(results: list[ComplexityResult], top_n: int = 15) -> list[ComplexityResult]:
    return sorted(results, key=lambda r: (-r.complexity, -r.line_count))[:top_n]
