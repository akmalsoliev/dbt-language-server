from typing import Literal
import pytest
from src.dbt_ls.pattern import completion_context


@pytest.mark.parametrize(
    "text, should_match",
    [
        ("ref('", True),
        ('ref("', True),
        ("source('", False),
        ("", False),
    ],
)
def test_match_ref(text, should_match):
    ctx = completion_context(text)
    result = ctx is not None and ctx[0] == "ref"
    assert result == should_match


@pytest.mark.parametrize(
    "text, should_match",
    [
        ('source("', True),
        ("source(src, tbl", False),  # no quotes
        ("ref('model", False),
        ("", False),
    ],
)
def test_match_source(text, should_match):
    ctx = completion_context(text)
    result = ctx is not None and ctx[0] == "source_name"
    assert result == should_match
