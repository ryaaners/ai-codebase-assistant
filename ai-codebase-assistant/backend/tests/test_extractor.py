from pathlib import Path

from app.core.extractor import extract
from app.core.parser import parse_source

FIXTURES = Path(__file__).parent / "fixtures" / "sample_repo"


def _extract_file(rel_path: str):
    full = FIXTURES / rel_path
    pf = parse_source(str(full), full.read_bytes())
    assert pf is not None, f"parser did not recognize {rel_path}"
    return extract(pf)


def test_python_extracts_class_and_methods():
    ext = _extract_file("app/auth.py")
    names = {s.qualified_name: s for s in ext.symbols}

    assert "AuthService" in names
    assert names["AuthService"].kind == "class"

    assert "AuthService.authenticate_user" in names
    assert names["AuthService.authenticate_user"].kind == "method"
    assert names["AuthService.authenticate_user"].parent_qualified_name == "AuthService"
    assert "returns a token" in names["AuthService.authenticate_user"].docstring

    assert "hash_password" in names
    assert names["hash_password"].kind == "function"

    assert "unused_helper" in names


def test_python_extracts_imports():
    ext = _extract_file("app/auth.py")
    sources = {imp.source for imp in ext.imports}
    assert "hashlib" in sources
    assert "app.models" in sources
    from_models = next(i for i in ext.imports if i.source == "app.models")
    assert from_models.imported_names == ["User"]


def test_python_call_edges_attribute_and_bare():
    ext = _extract_file("app/auth.py")
    callers_of_check_password = [
        c for c in ext.calls if c.callee_name == "_check_password"
    ]
    assert len(callers_of_check_password) == 1
    assert callers_of_check_password[0].caller_qualified_name == "AuthService.authenticate_user"

    # hash_password() is called from the (private) method _check_password
    bare_calls = [c for c in ext.calls if c.callee_name == "hash_password"]
    assert len(bare_calls) == 1
    assert bare_calls[0].caller_qualified_name == "AuthService._check_password"


def test_cross_file_call_names_match_across_files():
    # main.py calls auth_service.authenticate_user(...) -- extractor records
    # the *name* "authenticate_user"; resolving it to AuthService's method
    # (defined in a different file) is graph_builder's job, tested separately.
    main_ext = _extract_file("app/main.py")
    names_called = {c.callee_name for c in main_ext.calls}
    assert "authenticate_user" in names_called


def test_typescript_extracts_class_interface_and_arrow_fn():
    ext = _extract_file("utils/payments.ts")
    kinds = {s.qualified_name: s.kind for s in ext.symbols}

    assert kinds.get("PaymentResult") == "interface"
    assert kinds.get("PaymentService") == "class"
    assert kinds.get("PaymentService.processPayment") == "method"
    assert kinds.get("formatResult") == "function"
    assert kinds.get("unusedFormatter") == "function"


def test_typescript_import_source_is_unquoted():
    ext = _extract_file("utils/payments.ts")
    assert ext.imports[0].source == "./charge_client"
    assert ext.imports[0].imported_names == ["ChargeClient"]


def test_typescript_call_edge_inside_async_method():
    ext = _extract_file("utils/payments.ts")
    calls = [c for c in ext.calls if c.callee_name in ("charge", "formatResult")]
    callers = {c.caller_qualified_name for c in calls}
    assert "PaymentService.processPayment" in callers


def test_unsupported_extension_returns_none():
    pf = parse_source("README.md", b"# hello")
    assert pf is None
