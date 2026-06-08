from typing import Literal
import pytest
from src.dbt_ls.pattern import completion_context, ref_model_at


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


@pytest.mark.parametrize(
    "marked, expected",
    [
        # `|` marks the cursor; it is stripped before the call.
        ("ref('stg_cust|omers')", "stg_customers"),  # inside the name
        ("ref('|stg_customers')", "stg_customers"),  # at the start boundary
        ("ref('stg_customers|')", "stg_customers"),  # at the end boundary
        ('ref("stg_cust|omers")', "stg_customers"),  # double quotes
        ("select * from {{ ref('ord|ers') }} o", "orders"),  # embedded in SQL
        ("se|lect * from {{ ref('orders') }}", None),  # cursor outside the ref
        ("ref('orders') join ref('cust|omers')", "customers"),  # 2nd of two refs
        ("ref('ord|ers') join ref('customers')", "orders"),  # 1st of two refs
        ("source('raw', 'ord|ers')", None),  # source(), not ref()
        ("|", None),  # empty line
    ],
)
def test_ref_model_at(marked, expected):
    character = marked.index("|")
    line = marked.replace("|", "")
    assert ref_model_at(line, character) == expected
