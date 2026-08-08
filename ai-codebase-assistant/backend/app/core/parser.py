"""
Thin wrapper around tree-sitter that hides per-language setup.

Adding a new language means: pip install its tree-sitter-<lang> package,
register it in LANGUAGES below, and add an adapter in extractor.py.
That boundary is deliberate -- parser.py only knows how to turn bytes
into a tree; it has no opinion about what a "function" is in a given
language.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from tree_sitter import Language, Node, Parser, Tree

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts

# Map file extension -> canonical language id
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
}

# Files/directories we never want to walk into.
IGNORED_DIR_NAMES = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".turbo", "target", ".mypy_cache",
    ".pytest_cache", "coverage", ".idea", ".vscode", "vendor",
}


@lru_cache(maxsize=None)
def _language(lang_id: str) -> Language:
    if lang_id == "python":
        return Language(tspython.language())
    if lang_id == "javascript":
        return Language(tsjs.language())
    if lang_id == "typescript":
        return Language(tsts.language_typescript())
    if lang_id == "tsx":
        return Language(tsts.language_tsx())
    raise ValueError(f"Unsupported language: {lang_id}")


@lru_cache(maxsize=None)
def _parser(lang_id: str) -> Parser:
    return Parser(_language(lang_id))


def detect_language(file_path: str) -> str | None:
    for ext, lang in EXTENSION_TO_LANGUAGE.items():
        if file_path.endswith(ext):
            return lang
    return None


def is_supported(file_path: str) -> bool:
    return detect_language(file_path) is not None


@dataclass
class ParsedFile:
    path: str
    language: str
    source: bytes
    tree: Tree

    def text(self, node: Node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def parse_source(path: str, source: bytes) -> ParsedFile | None:
    """Parse a single file's bytes. Returns None for unsupported languages
    or files tree-sitter can't handle (it never throws on malformed code --
    it produces a best-effort tree with ERROR nodes, which we just skip
    when walking)."""
    lang = detect_language(path)
    if lang is None:
        return None
    tree = _parser(lang).parse(source)
    return ParsedFile(path=path, language=lang, source=source, tree=tree)
