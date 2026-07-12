import logging
import os
import sys
import uuid
from pathlib import Path

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path

from dbt_ls import __version__
from dbt_ls.alias import parse_aliases
from dbt_ls.model import (
    discover_models,
    enrich_models_from_database,
    filter_documented_database_sources,
)
from dbt_ls.pattern import completion_context, ref_model_at
from dbt_ls.profiles import Profiles
from dbt_ls.project import Project
from dbt_ls.source import discover_sources, enrich_sources_from_catalog
from dbt_ls.state import ProjectState

logging.basicConfig(
    stream=sys.stderr,
    level=os.environ.get("DBT_LS_LOG_LEVEL", "INFO").upper(),
    force=True,  # tear down pygls' root handler and use ours
)

logging.getLogger("pygls").setLevel(logging.WARNING)
log = logging.getLogger("dbt_ls")


class DbtLanguageServer(LanguageServer):
    """Language server that carries the discovered dbt project on `.state`."""

    def __init__(self):
        super().__init__("dbt-ls", __version__)
        self.state = ProjectState()


server = DbtLanguageServer()


def find_dbt_project_root(root: str) -> str:
    for p in Path(root).rglob("dbt_project.yml"):
        if "target" not in p.parts:
            return str(p.parent)
    return "."


def load_project(ls: DbtLanguageServer):

    # Progress report setup
    token = "reload-project" + str(uuid.uuid4())

    if (
        ls.client_capabilities.window
        and ls.client_capabilities.window.work_done_progress
    ):
        ls.work_done_progress.create(token)
        ls.work_done_progress.begin(
            token,
            types.WorkDoneProgressBegin(
                title="Loading dbt project", cancellable=False, percentage=0
            ),
        )

    root_path = ls.workspace.root_path

    if not root_path:
        log.warning("Initialize received no root_path; skipping project discovery")
        return

    dbt_root = find_dbt_project_root(root_path)
    if not dbt_root:
        log.warning("No dbt project root found under %s; skipping discovery", root_path)
        return

    project = Project(dbt_root)

    # Models and sources don't need the profile, so resolve them unconditionally.
    models = discover_models(root=root_path, model_paths=project.model_paths)
    log.debug("Finished parsing documented models")

    sources = discover_sources(root_path)
    log.debug("Finished parsing documented sources")

    # Catalog enrichment — only if the catalog has actually been generated.
    catalog_path = Path(dbt_root) / "target" / "catalog.json"
    if catalog_path.is_file():
        sources = enrich_sources_from_catalog(sources, catalog_path)
        log.debug("Finished parsing column info for sources from catalog")
    else:
        log.info("No catalog.json at %s; skipping catalog enrichment", catalog_path)

    ls.state.dbt_root = dbt_root
    ls.state.project = project
    ls.state.models = models
    ls.state.sources = sources

    # Database enrichment — needs a fully resolved profile target.
    profile = Profiles.locate(project.root)
    if not profile:
        log.info("No dbt profile located; skipping database enrichment")
        ls.work_done_progress.end(
            token, types.WorkDoneProgressEnd(message="❌No profile found")
        )
        return

    profile_target = profile.resolve(project.profile)
    if not profile_target:
        log.info(
            "Profile %r resolved to an empty target; skipping database enrichment",
            project.profile,
        )
        ls.work_done_progress.end(
            token, types.WorkDoneProgressEnd(message="❌Target empty")
        )
        return

    try:
        database_models, leftover_sources = enrich_models_from_database(
            models, profile_target, project.root
        )
    except ImportError:
        log.warning(
            "Database enrichment skipped: the backend for this profile isn't "
            "installed. Install the matching extra, e.g. "
            "`pip install dbt-ls[postgres]`, then restart. "
            "Continuing with documented models only."
        )
        ls.work_done_progress.end(
            token, types.WorkDoneProgressEnd(message="❌ImportError")
        )
    except Exception:  # noqa: BLE001 — enrichment must never crash initialize
        log.exception(
            "Database enrichment failed; continuing with documented models only"
        )
    else:
        if database_models:
            ls.state.models = database_models
        if leftover_sources:
            documented_sources, undocumented_sources = (
                filter_documented_database_sources(sources, leftover_sources)
            )
            ls.state.sources = documented_sources
            log.debug("Replaced sources with leftover sources")
        log.info("Finished parsing column info for models from database")

    ls.work_done_progress.end(token, types.WorkDoneProgressEnd(message="Finished"))


@server.feature(types.INITIALIZE)
def on_initialize(ls: DbtLanguageServer, params: types.ParameterInformation):
    load_project(ls)


@server.command("dbt-ls.reload")
def reload(ls: DbtLanguageServer):
    load_project(ls)


@server.command("dbt-ls.current_model")
def current_model(ls: DbtLanguageServer, model_uri):
    path = to_fs_path(model_uri)
    candidate_model = [model for model in ls.state.models if path == str(model.path)]
    return (
        {
            "dbt_root": ls.state.dbt_root,
            "exec_path": candidate_model[0].get_exec_path(
                candidate_model[0].path, ls.state.project
            ),
        }
        if candidate_model
        else None
    )


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=["'", '"', "(", "."]),
)
def completions(ls: DbtLanguageServer, params: types.CompletionParams):
    models = ls.state.models
    sources = ls.state.sources
    dbt_root = ls.state.dbt_root

    document = ls.workspace.get_text_document(params.text_document.uri)
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
                label_details=types.CompletionItemLabelDetails(
                    description=str(m.path).split(dbt_root)[-1]
                ),
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
                label_details=types.CompletionItemLabelDetails(
                    description=s.source_name
                ),
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

        return [
            types.CompletionItem(
                label=c.name,
                kind=types.CompletionItemKind(5),
                label_details=types.CompletionItemLabelDetails(
                    description=c.data_type
                ),
            )
            for m in (*models, *sources)
            for c in m.columns
            if m.name == model_name
        ]
    else:
        log.debug("no pattern matched for %r", current_line)
        return []


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls: DbtLanguageServer, params: types.DefinitionParams):
    """Jump from a ref('model') to that model's .sql file."""
    document = ls.workspace.get_text_document(params.text_document.uri)
    pos = params.position
    line = document.lines[pos.line] if pos.line < len(document.lines) else ""

    model_name = ref_model_at(line, pos.character)
    if model_name is None:
        return None

    target = next((m for m in ls.state.models if m.name == model_name and m.path), None)
    if target is None:
        log.info("DEFINITION: no model file found for %r", model_name)
        return None

    log.info("DEFINITION: %r → %s", model_name, target.path)
    start = types.Position(line=0, character=0)
    return types.Location(
        uri=Path(target.path).as_uri(),
        range=types.Range(start=start, end=start),
    )
