from pathlib import Path

from app.core.complexity import compute_complexity, rank_hotspots
from app.core.extractor import extract
from app.core.parser import parse_source

FIXTURES = Path(__file__).parent / "fixtures" / "sample_repo"


def test_complexity_is_scoped_to_each_symbol_not_a_shared_sibling_value():
    """Regression test: an earlier version located each symbol's node via a
    (line, column=0) point range, which lands in leading indentation and
    resolves to the *enclosing* block for any def not starting at column 0
    -- silently giving every method in a class the same (wrong) inflated
    score. Byte-exact lookup fixed it; this pins the fix."""
    p = FIXTURES / "app" / "auth.py"
    pf = parse_source(str(p), p.read_bytes())
    ext = extract(pf)
    results = {r.qualified_name: r for r in compute_complexity(pf, ext.symbols)}

    # trivial one-liner assignment: no branches at all
    assert results["AuthService.__init__"].complexity == 1
    # two `if ... : return None` guard clauses
    assert results["AuthService.authenticate_user"].complexity == 3
    # single return expression, no branches
    assert results["AuthService._check_password"].complexity == 1

    # crucially, these must all differ -- the bug made them identical
    values = {r.complexity for r in results.values()}
    assert len(values) > 1


def test_rank_hotspots_orders_by_complexity_desc():
    p = FIXTURES / "app" / "auth.py"
    pf = parse_source(str(p), p.read_bytes())
    ext = extract(pf)
    results = compute_complexity(pf, ext.symbols)
    ranked = rank_hotspots(results, top_n=3)
    assert ranked[0].qualified_name == "AuthService.authenticate_user"
    assert all(ranked[i].complexity >= ranked[i + 1].complexity for i in range(len(ranked) - 1))
