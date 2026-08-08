"""
Turns a parsed AST into structured facts: symbols (functions/methods/classes/
interfaces), imports, and call edges.

This is intentionally name-based rather than fully type-resolved -- we do not
run a real type checker, so a call to `.save()` is recorded as a call to a
symbol literally named `save`, and resolved against candidates at graph-build
time (see graph_builder.py). That's the same tradeoff lightweight code-intel
tools (ctags, early Sourcegraph, GitHub's old code nav) make: no build step
required, works on any subset of a repo, occasionally over- or under-links.
A "confidence" field on each edge reflects how it was resolved.

Each language gets its own adapter function below because the interesting
node types differ, but they all produce the same FileExtraction shape.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from tree_sitter import Node

from app.core.parser import ParsedFile

FUNCTION_KINDS = {"function", "method"}


@dataclass
class Symbol:
    id: str
    kind: str  # function | method | class | interface
    name: str
    qualified_name: str
    parent_qualified_name: str | None
    file_path: str
    language: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    signature: str
    docstring: str | None
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


@dataclass
class ImportRef:
    file_path: str
    source: str
    imported_names: list[str]
    line: int


@dataclass
class CallRef:
    file_path: str
    caller_qualified_name: str | None
    callee_name: str
    line: int


@dataclass
class FileExtraction:
    file_path: str
    language: str
    loc: int
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[ImportRef] = field(default_factory=list)
    calls: list[CallRef] = field(default_factory=list)
    parse_error_count: int = 0


@dataclass
class _Frame:
    kind: str  # "class" | "function"
    name: str
    qualified_name: str


def _symbol_id(file_path: str, qualified_name: str, kind: str, start_line: int) -> str:
    raw = f"{file_path}:{qualified_name}:{kind}:{start_line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _count_errors(node: Node) -> int:
    count = 1 if node.type == "ERROR" or node.has_error else 0
    # has_error is true for ancestors of an error too, so only count leaves
    # that are literally ERROR nodes to avoid inflating the number.
    count = 1 if node.type == "ERROR" else 0
    for child in node.children:
        count += _count_errors(child)
    return count


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------

def extract_python(pf: ParsedFile) -> FileExtraction:
    out = FileExtraction(
        file_path=pf.path,
        language=pf.language,
        loc=pf.source.count(b"\n") + 1,
        parse_error_count=_count_errors(pf.tree.root_node),
    )
    _walk_python(pf, pf.tree.root_node, out, [])
    return out


def _walk_python(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    for child in node.children:
        if child.type == "import_statement":
            _py_plain_import(pf, child, out)
        elif child.type == "import_from_statement":
            _py_from_import(pf, child, out)
        elif child.type == "decorated_definition":
            decorators = [pf.text(c) for c in child.children if c.type == "decorator"]
            inner = child.child_by_field_name("definition")
            if inner is not None:
                _py_definition(pf, inner, out, stack, decorators)
        elif child.type in ("function_definition", "class_definition"):
            _py_definition(pf, child, out, stack, [])
        elif child.type == "call":
            _py_call(pf, child, out, stack)
            _walk_python(pf, child, out, stack)
        else:
            _walk_python(pf, child, out, stack)


def _py_definition(
    pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame], decorators: list[str]
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = pf.text(name_node)
    qualified = ".".join([f.name for f in stack] + [name])
    parent_qualified = stack[-1].qualified_name if stack else None
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1

    if node.type == "function_definition":
        kind = "method" if stack and stack[-1].kind == "class" else "function"
        params_node = node.child_by_field_name("parameters")
        params_text = pf.text(params_node) if params_node else "()"
        signature = f"def {name}{params_text}"
        body_node = node.child_by_field_name("body")
        docstring = _py_docstring(pf, body_node)
        symbol = Symbol(
            id=_symbol_id(pf.path, qualified, kind, start_line),
            kind=kind, name=name, qualified_name=qualified,
            parent_qualified_name=parent_qualified, file_path=pf.path,
            language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
            signature=signature, docstring=docstring, decorators=decorators,
        )
        out.symbols.append(symbol)
        stack.append(_Frame("function", name, qualified))
        if body_node is not None:
            _walk_python(pf, body_node, out, stack)
        stack.pop()
    else:  # class_definition
        bases: list[str] = []
        superclasses = node.child_by_field_name("superclasses")
        if superclasses is not None:
            bases = [pf.text(c) for c in superclasses.children if c.type not in ("(", ")", ",")]
        body_node = node.child_by_field_name("body")
        docstring = _py_docstring(pf, body_node)
        symbol = Symbol(
            id=_symbol_id(pf.path, qualified, "class", start_line),
            kind="class", name=name, qualified_name=qualified,
            parent_qualified_name=parent_qualified, file_path=pf.path,
            language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
            signature=f"class {name}" + (f"({', '.join(bases)})" if bases else ""),
            docstring=docstring, decorators=decorators, bases=bases,
        )
        out.symbols.append(symbol)
        stack.append(_Frame("class", name, qualified))
        if body_node is not None:
            _walk_python(pf, body_node, out, stack)
        stack.pop()


def _py_docstring(pf: ParsedFile, body_node: Node | None) -> str | None:
    if body_node is None or body_node.child_count == 0:
        return None
    first = body_node.children[0]
    if first.type != "expression_statement" or first.child_count == 0:
        return None
    string_node = first.children[0]
    if string_node.type != "string":
        return None
    content = "".join(
        pf.text(c) for c in string_node.children if c.type == "string_content"
    )
    return content.strip() or None


def _py_plain_import(pf: ParsedFile, node: Node, out: FileExtraction) -> None:
    for child in node.children:
        if child.type == "dotted_name":
            out.imports.append(ImportRef(pf.path, pf.text(child), [], node.start_point[0] + 1))
        elif child.type == "aliased_import":
            dotted = child.children[0]
            out.imports.append(ImportRef(pf.path, pf.text(dotted), [], node.start_point[0] + 1))


def _py_from_import(pf: ParsedFile, node: Node, out: FileExtraction) -> None:
    source = ""
    names: list[str] = []
    seen_import_kw = False
    for child in node.children:
        if child.type == "import":
            seen_import_kw = True
            continue
        if child.type == "from":
            continue
        if not seen_import_kw:
            source = pf.text(child)
        else:
            if child.type == "dotted_name":
                names.append(pf.text(child))
            elif child.type == "aliased_import":
                names.append(pf.text(child.children[0]))
            elif child.type == "wildcard_import":
                names.append("*")
    out.imports.append(ImportRef(pf.path, source, names, node.start_point[0] + 1))


def _py_call(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return
    callee = _callee_name(pf, fn_node, attr_field="attribute")
    if callee:
        caller = stack[-1].qualified_name if stack else None
        out.calls.append(CallRef(pf.path, caller, callee, node.start_point[0] + 1))


def _callee_name(pf: ParsedFile, fn_node: Node, attr_field: str) -> str | None:
    if fn_node.type == "identifier":
        return pf.text(fn_node)
    if fn_node.type in ("attribute", "member_expression"):
        attr = fn_node.child_by_field_name(attr_field)
        return pf.text(attr) if attr is not None else None
    return None


# --------------------------------------------------------------------------
# JavaScript / TypeScript / TSX
# --------------------------------------------------------------------------

FUNCTION_LIKE = {"function_declaration", "function_expression", "generator_function_declaration"}


def extract_js_family(pf: ParsedFile) -> FileExtraction:
    out = FileExtraction(
        file_path=pf.path,
        language=pf.language,
        loc=pf.source.count(b"\n") + 1,
        parse_error_count=_count_errors(pf.tree.root_node),
    )
    _walk_js(pf, pf.tree.root_node, out, [])
    return out


def _unwrap_export(node: Node) -> Node:
    """`export`/`export default` wrap the real declaration; peel it off."""
    if node.type == "export_statement":
        decl = node.child_by_field_name("declaration")
        if decl is not None:
            return decl
        for c in node.children:
            if c.type not in ("export", "default", ";"):
                return c
    return node


def _walk_js(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    for raw_child in node.children:
        child = _unwrap_export(raw_child)

        if child.type == "import_statement":
            _js_import(pf, child, out)
        elif child.type in ("class_declaration", "class"):
            _js_class(pf, child, out, stack)
        elif child.type in FUNCTION_LIKE:
            _js_function(pf, child, out, stack, name_hint=None)
        elif child.type == "lexical_declaration" or child.type == "variable_declaration":
            _js_var_decl(pf, child, out, stack)
        elif child.type == "interface_declaration":
            _js_interface(pf, child, out, stack)
        elif child.type == "method_definition":
            _js_function(pf, child, out, stack, name_hint=None, kind_override="method")
        elif child.type == "call_expression":
            _js_call(pf, child, out, stack)
            _walk_js(pf, child, out, stack)
        else:
            _walk_js(pf, child, out, stack)


def _js_name_text(pf: ParsedFile, node: Node) -> str | None:
    name_field = node.child_by_field_name("name")
    if name_field is not None:
        return pf.text(name_field)
    for c in node.children:
        if c.type in ("identifier", "type_identifier", "property_identifier"):
            return pf.text(c)
    return None


def _js_class(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    name = _js_name_text(pf, node) or "<anonymous class>"
    qualified = ".".join([f.name for f in stack] + [name])
    start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
    bases: list[str] = []
    for c in node.children:
        if c.type == "class_heritage":
            bases.append(pf.text(c).replace("extends", "").strip())
    symbol = Symbol(
        id=_symbol_id(pf.path, qualified, "class", start_line),
        kind="class", name=name, qualified_name=qualified,
        parent_qualified_name=stack[-1].qualified_name if stack else None,
        file_path=pf.path, language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
        signature=f"class {name}" + (f" extends {bases[0]}" if bases else ""),
        docstring=None, bases=bases,
    )
    out.symbols.append(symbol)
    stack.append(_Frame("class", name, qualified))
    body = node.child_by_field_name("body")
    if body is not None:
        _walk_js(pf, body, out, stack)
    stack.pop()


def _js_function(
    pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame],
    name_hint: str | None, kind_override: str | None = None,
) -> None:
    name = name_hint or _js_name_text(pf, node) or "<anonymous>"
    qualified = ".".join([f.name for f in stack] + [name])
    start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
    kind = kind_override or ("method" if stack and stack[-1].kind == "class" else "function")
    params = node.child_by_field_name("parameters")
    params_text = pf.text(params) if params is not None else "()"
    is_async = any(c.type == "async" for c in node.children)
    signature = f"{'async ' if is_async else ''}function {name}{params_text}"
    symbol = Symbol(
        id=_symbol_id(pf.path, qualified, kind, start_line),
        kind=kind, name=name, qualified_name=qualified,
        parent_qualified_name=stack[-1].qualified_name if stack else None,
        file_path=pf.path, language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
        signature=signature, docstring=None,
    )
    out.symbols.append(symbol)
    stack.append(_Frame("function", name, qualified))
    body = node.child_by_field_name("body")
    if body is not None:
        _walk_js(pf, body, out, stack)
    stack.pop()


def _js_var_decl(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    """Handles `const foo = () => {...}` / `const Bar = function () {...}`."""
    for declarator in node.children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        if value_node.type in ("arrow_function", *FUNCTION_LIKE):
            _js_arrow_or_fn(pf, value_node, out, stack, name=pf.text(name_node))


def _js_arrow_or_fn(
    pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame], name: str
) -> None:
    qualified = ".".join([f.name for f in stack] + [name])
    start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
    kind = "method" if stack and stack[-1].kind == "class" else "function"
    params = node.child_by_field_name("parameters")
    if params is not None:
        params_text = pf.text(params)
    else:
        single = next((c for c in node.children if c.type == "identifier"), None)
        params_text = f"({pf.text(single)})" if single else "()"
    is_async = any(c.type == "async" for c in node.children)
    signature = f"{'async ' if is_async else ''}const {name} = {params_text} => ..."
    symbol = Symbol(
        id=_symbol_id(pf.path, qualified, kind, start_line),
        kind=kind, name=name, qualified_name=qualified,
        parent_qualified_name=stack[-1].qualified_name if stack else None,
        file_path=pf.path, language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
        signature=signature, docstring=None,
    )
    out.symbols.append(symbol)
    stack.append(_Frame("function", name, qualified))
    body = node.child_by_field_name("body")
    if body is not None:
        _walk_js(pf, body, out, stack)
    stack.pop()


def _js_interface(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    name = _js_name_text(pf, node) or "<anonymous interface>"
    qualified = ".".join([f.name for f in stack] + [name])
    start_line, end_line = node.start_point[0] + 1, node.end_point[0] + 1
    symbol = Symbol(
        id=_symbol_id(pf.path, qualified, "interface", start_line),
        kind="interface", name=name, qualified_name=qualified,
        parent_qualified_name=stack[-1].qualified_name if stack else None,
        file_path=pf.path, language=pf.language, start_line=start_line, end_line=end_line, start_byte=node.start_byte, end_byte=node.end_byte,
        signature=f"interface {name}", docstring=None,
    )
    out.symbols.append(symbol)


def _js_import(pf: ParsedFile, node: Node, out: FileExtraction) -> None:
    """Handles default, named, aliased-named, and namespace imports.
    `import_clause` isn't exposed as a named field in the grammar, so we
    find it positionally, then read each import shape explicitly -- no
    generic recursion, so a name can't be picked up twice."""
    source_node = node.child_by_field_name("source")
    source = pf.text(source_node).strip("'\"") if source_node is not None else ""
    names: list[str] = []

    clause = next((c for c in node.children if c.type == "import_clause"), None)
    if clause is not None:
        for c in clause.children:
            if c.type == "identifier":  # default import: `import Foo from ...`
                names.append(pf.text(c))
            elif c.type == "namespace_import":  # `import * as ns from ...`
                ident = next((g for g in c.children if g.type == "identifier"), None)
                if ident is not None:
                    names.append(pf.text(ident))
            elif c.type == "named_imports":  # `import { a, b as c } from ...`
                for spec in c.children:
                    if spec.type != "import_specifier":
                        continue
                    chosen = spec.child_by_field_name("alias") or spec.child_by_field_name("name")
                    if chosen is not None:
                        names.append(pf.text(chosen))
    out.imports.append(ImportRef(pf.path, source, names, node.start_point[0] + 1))


def _js_call(pf: ParsedFile, node: Node, out: FileExtraction, stack: list[_Frame]) -> None:
    fn_node = node.child_by_field_name("function")
    if fn_node is None:
        return
    callee = _callee_name(pf, fn_node, attr_field="property")
    if callee:
        caller = stack[-1].qualified_name if stack else None
        out.calls.append(CallRef(pf.path, caller, callee, node.start_point[0] + 1))


# --------------------------------------------------------------------------
# Dispatch
# --------------------------------------------------------------------------

def extract(pf: ParsedFile) -> FileExtraction:
    if pf.language == "python":
        return extract_python(pf)
    if pf.language in ("javascript", "typescript", "tsx"):
        return extract_js_family(pf)
    raise ValueError(f"No extractor registered for language: {pf.language}")
