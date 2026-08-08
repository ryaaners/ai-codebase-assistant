import json

from app.core.extractor import Symbol
from app.core.llm import LLMProvider, LLMUnavailable, NullProvider
from app.core.summarizer import summarize_symbols


def _symbol(id_, name, docstring=None, kind="function"):
    return Symbol(
        id=id_, kind=kind, name=name, qualified_name=name, parent_qualified_name=None,
        file_path="x.py", language="python", start_line=1, end_line=2, start_byte=0, end_byte=10,
        signature=f"def {name}()", docstring=docstring,
    )


class FakeLLM(LLMProvider):
    """Echoes back a JSON summary per item, tagging which batch it saw --
    lets the test assert on batch size without depending on real network."""

    def __init__(self):
        self.calls: list[int] = []

    def generate(self, system, prompt, max_tokens=1024):
        payload = json.loads(prompt.split("Summarize each of these:\n\n")[1])
        self.calls.append(len(payload))
        return json.dumps([{"id": item["id"], "summary": f"Does something with {item['id']}."} for item in payload])


class BrokenLLM(LLMProvider):
    def generate(self, system, prompt, max_tokens=1024):
        return "not json at all, the model rambled instead"


def test_documented_symbols_skip_the_llm_entirely():
    llm = FakeLLM()
    symbols = [_symbol("1", "well_documented", docstring="Computes the thing precisely and clearly.")]
    result = summarize_symbols(llm, symbols, snippets={})
    assert llm.calls == []
    assert result["1"] == "Computes the thing precisely and clearly."


def test_undocumented_symbols_batch_through_the_llm():
    llm = FakeLLM()
    symbols = [_symbol(str(i), f"fn_{i}") for i in range(45)]
    result = summarize_symbols(llm, symbols, snippets={})
    # 45 symbols at BATCH_SIZE=20 -> batches of 20, 20, 5
    assert llm.calls == [20, 20, 5]
    assert result["0"] == "Does something with 0."
    assert len(result) == 45


def test_null_provider_falls_back_to_extractive_summary_for_everyone():
    symbols = [
        _symbol("1", "hp", docstring=None),
        _symbol("2", "compute_thing", docstring="Multi word docstring here. And more."),
    ]
    result = summarize_symbols(NullProvider(), symbols, snippets={})
    assert result["1"] == "Function `hp` (def hp())."
    assert result["2"] == "Multi word docstring here."


def test_unparseable_llm_response_falls_back_to_extractive_for_that_batch():
    symbols = [_symbol("1", "mystery_fn")]
    result = summarize_symbols(BrokenLLM(), symbols, snippets={})
    assert result["1"] == "Function `mystery_fn` (def mystery_fn())."


def test_max_symbols_caps_llm_spend_but_everyone_still_gets_a_summary():
    llm = FakeLLM()
    symbols = [_symbol(str(i), f"fn_{i}") for i in range(10)]
    result = summarize_symbols(llm, symbols, snippets={}, max_symbols=3)
    assert llm.calls == [3]
    assert len(result) == 10  # the other 7 still get extractive summaries
    assert result["9"] == "Function `fn_9` (def fn_9())."
