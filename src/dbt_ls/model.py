from dataclasses import dataclass
from pathlib import Path
from dbt_ls.column import Column
import json
from dbt_ls.profiles import ProfileTarget
import ibis
from ibis.expr.schema import Schema
from ibis.expr.types.relations import (
    Table,
)
from dbt_ls.profiles import DuckDBTarget, DatabaseTarget, MySQLTarget, MSSQLTarget
from typing import Callable, Any
from ibis import BaseBackend

from dbt_ls.source import SourceTable
import os


@dataclass(frozen=True)
class Model:
    name: str
    path: str
    columns: tuple[Column, ...] = ()

    def __repr__(self):
        return f"Model: {self.name}, Path: {self.path}, Exec path: {self.exec_path}"

    @property
    def exec_path(self) -> str:
        return self.path.split("models/")[-1].split(".sql")[0].replace(os.sep, ".")


def discover_models(root: str, model_paths: list[str]) -> list[Model]:
    return [
        Model(name=p.stem, path=str(p))
        for model_path in model_paths
        for p in (Path(root) / model_path).rglob("*.sql")
    ]


def enrich_models_from_catalog(models: list[Model], catalog_path: Path) -> list[Model]:
    path = Path(catalog_path)
    if not path.is_file():
        return models

    catalog = json.loads(path.read_text())
    nodes = catalog.get("nodes", {})

    # Build a lookup: model name -> columns
    columns_by_name: dict[str, tuple[Column, ...]] = {}
    for node in nodes.values():
        if not node.get("unique_id", "").startswith("model."):
            continue
        name = node["metadata"]["name"]
        columns_by_name[name] = tuple(
            Column(name=c["name"], data_type=c.get("type"))
            for c in node.get("columns", {}).values()
        )

    return [
        Model(name=m.name, path=m.path, columns=columns_by_name.get(m.name, m.columns))
        for m in models
    ]


def get_duckdb_models(
    models: list[Model], profile_target: DuckDBTarget, project_root: str | Path
) -> list[Model] | None:
    ibis.set_backend("duckdb")

    connection_path = (
        profile_target.path
        if Path(profile_target.path).is_absolute()
        else Path(project_root).joinpath(profile_target.path)
    )
    con = ibis.duckdb.connect(connection_path)

    return _get_database_schema(models, con)


def get_database_models(
    models: list[Model], profile_target: DatabaseTarget, project_root: str | Path
) -> list[Model] | None:

    # TODO: Make this work on every database
    con = ibis.postgres.connect(
        user=profile_target.user,
        password=profile_target.password.reveal(),
        host=profile_target.host,
        port=profile_target.port,
        database=profile_target.dbname,
        schema=profile_target.schema,
    )

    return _get_database_schema(models, con)


def get_mysql_models(
    models: list[Model], profile_target: MySQLTarget, project_root: str | Path
) -> list[Model] | None:

    con = ibis.mysql.connect(
        user=profile_target.user,
        password=profile_target.password.reveal(),
        host=profile_target.server,
        port=profile_target.port,
        database=profile_target.schema,
    )

    return _get_database_schema(models, con)


def get_mssql_models(
    models: list[Model], profile_target: MSSQLTarget, project_root: str | Path
) -> list[Model] | None:
    con = ibis.mssql.connect(
        user=profile_target.user,
        password=profile_target.password.reveal(),
        host=profile_target.server,
        port=profile_target.port,
        database=profile_target.database,
        schema=profile_target.schema,
        driver=profile_target.driver,
        TrustServerCertificate="yes" if not profile_target.encrypt else "no",
    )

    return _get_database_schema(models, con)


_DATABASE_METHOD_REGISTRY: dict[
    str,
    Callable[..., list[Model] | None],
] = {
    "duckdb": get_duckdb_models,
    "postgres": get_database_models,
    "mysql": get_mysql_models,
    "sqlserver": get_mssql_models,
}


def _get_database_schema(
    models: list[Model], con: BaseBackend
) -> tuple[list[Model], list[SourceTable]]:

    columns_by_name: dict[str, tuple[Column, ...]] = {}

    tables = con.list_tables()
    for t in tables:
        table: Table = con.table(t)
        schema: Schema = table.schema()

        columns_by_name[t] = tuple(
            Column(name=name, data_type=str(dtype)) for name, dtype in schema.items()
        )

    leftover_sources = columns_by_name.keys() - [m.name for m in models]

    return (
        [
            Model(name=m.name, path=m.path, columns=columns_by_name.get(m.name, ()))
            for m in models
        ],
        [
            SourceTable(name=s, source_name=s, columns=columns_by_name.get(s, ()))
            for s in leftover_sources
        ],
    )


def enrich_models_from_database(
    models: list[Model],
    profile_target: (
        DuckDBTarget | DatabaseTarget | MSSQLTarget | MySQLTarget | ProfileTarget
    ),
    project_root: str | Path,
) -> list[Model] | None:
    fn = _DATABASE_METHOD_REGISTRY.get(profile_target.type)
    if fn is None:
        return None
    return fn(models, profile_target, project_root)
