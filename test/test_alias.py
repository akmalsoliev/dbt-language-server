import pytest
from dbt_ls.alias import parse_aliases


@pytest.mark.parametrize(
    "text, expected",
    [
        ("{{ ref('accounts') }} a", {"a": "accounts"}),
        ('{{ ref("orders") }} o', {"o": "orders"}),
        ("{{ source('src', 'my_table') }} t", {"t": "my_table"}),
        (
            "{{ ref('accounts') }} a join {{ ref('orders') }} o",
            {"a": "accounts", "o": "orders"},
        ),
        ("select 1", {}),
    ],
)
def test_parse_aliases(text, expected):
    assert parse_aliases(text) == expected
