from dataclasses import dataclass
from pathlib import Path
from dbt_ls.column import Column
import json


@dataclass(frozen=True)
class Model:
    name: str
    path: str
    columns: tuple[Column, ...] = ()


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
