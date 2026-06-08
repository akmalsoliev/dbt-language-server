import pytest
from lsprotocol import types

import src.dbt_ls as dbt_ls
from src.dbt_ls.model import Model


class FakeDoc:
    """Stand-in for pygls' TextDocument: the handler only reads `.lines`."""

    def __init__(self, text: str):
        self.lines = text.splitlines(keepends=True)


class FakeServer:
    """Minimal server exposing workspace.get_text_document(uri) -> FakeDoc."""

    def __init__(self, doc: FakeDoc):
        self.workspace = type(
            "FakeWorkspace", (), {"get_text_document": lambda self, uri: doc}
        )()


def make_params(line: str, character: int) -> types.DefinitionParams:
    return types.DefinitionParams(
        text_document=types.TextDocumentIdentifier(uri="file:///query.sql"),
        position=types.Position(line=0, character=character),
    )


@pytest.fixture
def model_file(tmp_path):
    f = tmp_path / "stg_customers.sql"
    f.write_text("select 1\n")
    return f


def _setup(monkeypatch, line: str, models: list[Model]):
    monkeypatch.setattr(dbt_ls, "server", FakeServer(FakeDoc(line)))
    # `models` is created lazily in on_initialize, so it may not exist yet.
    monkeypatch.setattr(dbt_ls, "models", models, raising=False)


def test_definition_jumps_to_model_file(monkeypatch, model_file):
    line = "select * from {{ ref('stg_customers') }}"
    _setup(monkeypatch, line, [Model(name="stg_customers", path=str(model_file))])

    cursor = line.index("stg_customers") + 2
    result = dbt_ls.definition(make_params(line, cursor))

    assert result is not None
    assert result.uri == model_file.as_uri()
    # We always point at the top of the target file.
    assert result.range.start == types.Position(line=0, character=0)
    assert result.range.end == types.Position(line=0, character=0)


def test_definition_returns_none_when_cursor_not_on_ref(monkeypatch, model_file):
    line = "select * from {{ ref('stg_customers') }}"
    _setup(monkeypatch, line, [Model(name="stg_customers", path=str(model_file))])

    # cursor on the `select` keyword, outside any ref()
    result = dbt_ls.definition(make_params(line, 2))
    assert result is None


def test_definition_returns_none_for_unknown_model(monkeypatch):
    line = "{{ ref('does_not_exist') }}"
    _setup(monkeypatch, line, [Model(name="stg_customers", path="/somewhere.sql")])

    cursor = line.index("does_not_exist") + 2
    result = dbt_ls.definition(make_params(line, cursor))
    assert result is None


def test_definition_returns_none_when_model_has_no_path(monkeypatch):
    line = "{{ ref('stg_customers') }}"
    _setup(monkeypatch, line, [Model(name="stg_customers", path=None)])

    cursor = line.index("stg_customers") + 2
    result = dbt_ls.definition(make_params(line, cursor))
    assert result is None
