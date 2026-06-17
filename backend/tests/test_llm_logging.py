"""Free unit tests for llm.py's token-usage logging helper. NO API calls."""

from __future__ import annotations

import json
import types

import llm


def test_usage_dict_extracts_token_counts_including_cache_fields():
    usage = types.SimpleNamespace(
        input_tokens=1200,
        output_tokens=340,
        cache_read_input_tokens=1000,
        cache_creation_input_tokens=0,
    )
    d = llm._usage_dict(types.SimpleNamespace(usage=usage))
    assert d == {
        "input_tokens": 1200,
        "output_tokens": 340,
        "cache_read_input_tokens": 1000,
        "cache_creation_input_tokens": 0,
    }
    # The merged log line must still serialize as one JSON object.
    json.dumps({"status": "success", **d})


def test_usage_dict_missing_cache_fields_default_to_none():
    usage = types.SimpleNamespace(input_tokens=10, output_tokens=5)
    d = llm._usage_dict(types.SimpleNamespace(usage=usage))
    assert d["input_tokens"] == 10 and d["output_tokens"] == 5
    assert d["cache_read_input_tokens"] is None
    assert d["cache_creation_input_tokens"] is None


def test_usage_dict_is_empty_when_no_usage():
    assert llm._usage_dict(types.SimpleNamespace(usage=None)) == {}
    assert llm._usage_dict(types.SimpleNamespace()) == {}
