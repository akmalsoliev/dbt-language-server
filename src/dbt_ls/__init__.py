from pygls.lsp.server import LanguageServer
import logging
import os
import sys
from lsprotocol import types
from importlib.metadata import version
from dbt_ls.pattern import completion_context
from dbt_ls.model import discover_models, enrich_models_from_catalog
from dbt_ls.source import discover_sources, enrich_sources_from_catalog
from pathlib import Path
from dbt_ls.alias import parse_aliases
from dbt_ls.project import Project

logging.basicConfig(
    stream=sys.stderr,
    level=os.environ.get("DBT_LS_LOG_LEVEL", "INFO").upper(),
    force=True,  # tear down pygls' root handler and use ours
)

logging.getLogger("pygls").setLevel(logging.WARNING)
log = logging.getLogger("dbt_ls")

__version__ = version("dbt-ls")

server = LanguageServer("dbt-ls", __version__)


def find_dbt_project_root(root: str) -> str:
    for p in Path(root).rglob("dbt_project.yml"):
        if "target" not in p.parts:
            return str(p.parent)
    return "."


@server.feature(types.INITIALIZE)
def on_initialize(params: types.InitializeParams):
    global models
    global sources
    global dbt_root
    global project
    if params.root_path:
        dbt_root = find_dbt_project_root(params.root_path)
        project = Project(dbt_root)
        catalog_path = Path(f"{dbt_root}/target/catalog.json")
        models = discover_models(root=params.root_path, model_paths=project.model_paths)
        log.debug("Finished parsing documented models")
        sources = discover_sources(params.root_path)
        log.debug("Finished parsing documented sources")
        models = enrich_models_from_catalog(models, catalog_path)
        log.debug("Finished parsing column info for models from catalog")
        sources = enrich_sources_from_catalog(sources, catalog_path)
        log.debug("Finished parsing column info for sources from catalog")


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=["'", '"', "(", "."]),
)
def completions(params: types.CompletionParams):
    document = server.workspace.get_text_document(params.text_document.uri)
    current_line = document.lines[params.position.line].strip()
    pos = params.position
    line = document.lines[pos.line] if pos.line < len(document.lines) else ""
    line_prefix = line[: pos.character]

    ctx = completion_context(line_prefix)
    if ctx is None:
        log.debug("no pattern matched for %r", current_line, " (early exit)")
        return None

    log.debug("completion @ %d:%d | line=%r", pos.line, pos.character, current_line)

    kind, info = ctx

    if kind == "ref":
        log.info(
            "REF path matched %r → serving %d models: %s",
            current_line,
            len(models),
            [m.name for m in models[:15]],
        )
        return [
            types.CompletionItem(
                m.name,
                kind=types.CompletionItemKind(18),
                label_details=types.CompletionItemLabelDetails(m.path),
            )
            for m in models
        ]
    elif kind == "source_name":
        [log.debug(c) for m in (*models, *sources) for c in m.columns]
        log.info(
            "SOURCE path matched %r → serving %d sources: %s",
            current_line,
            len(sources),
            [s.name for s in sources[:15]],
        )
        return [
            types.CompletionItem(
                s.name,
                kind=types.CompletionItemKind(10),
                label_details=types.CompletionItemLabelDetails(s.database),
                insert_text=f'{s.source_name}", "{s.name}',
                insert_text_format=types.InsertTextFormat.PlainText,
            )
            for s in sources
        ]
    elif kind == "column":
        alias = info["alias"]
        alias_map = parse_aliases(document.source)
        model_name = alias_map.get(alias)
        log.info("COLUMN path: alias=%r → model=%r", alias, model_name)
        # for m in (*models, *sources):
        #     for c in m.columns:
        #         log.debug(f"COLUMN found: {c}")

        return [
            types.CompletionItem(
                label=c.name,
                kind=types.CompletionItemKind(5),
                label_details=types.CompletionItemLabelDetails(c.data_type),
            )
            for m in (*models, *sources)
            for c in m.columns
            if m.name == model_name
        ]
    else:
        log.debug("no pattern matched for %r", current_line)
        return []


def main():
    banner = f"""
   ╔═══════════════════════════════════════╗
   ║                                       ║
   ║      _ _     _        _               ║
   ║   __| | |__ | |_     | |___           ║
   ║  / _` | '_ \\| __|____| / __|          ║
   ║ | (_| | |_) | ||_____| \\__ \\          ║
   ║  \\__,_|_.__/ \\__|    |_|___/          ║
   ║                                       ║
   ║   {__version__:^5} · Language Server · stdio     ║
   ║                                       ║
   ╚═══════════════════════════════════════╝
    """
    print(banner)
    logging.info("DBT Language Server started")
    server.start_io()


if __name__ == "__main__":
    main()
