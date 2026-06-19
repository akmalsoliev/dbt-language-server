from pathlib import Path
from dataclasses import dataclass, fields, field
import yaml
from typing import Any


class Secret:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "********"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return self.__repr__()


@dataclass(kw_only=True)
class ProfileTarget:
    type: str
    threads: int = 1

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileTarget":
        target_cls = _TARGET_REGISTRY.get(data.get("type", ""), cls)
        allowed = {f.name for f in fields(target_cls)}
        kwargs = {k: v for k, v in data.items() if k in allowed}
        if isinstance(kwargs.get("password"), str):
            kwargs["password"] = Secret(kwargs["password"])
        return target_cls(**kwargs)


@dataclass(kw_only=True)
class DuckDBTarget(ProfileTarget):
    path: str


@dataclass(kw_only=True)
class DatabaseTarget(ProfileTarget):
    user: str
    password: Secret
    host: str
    port: int
    dbname: str
    schema: str


@dataclass(kw_only=True)
class MySQLTarget(ProfileTarget):
    user: str
    password: Secret
    server: str  # TODO: Fix so takes server or host key
    port: int
    schema: str


@dataclass(kw_only=True)
class MSSQLTarget(ProfileTarget):
    user: str
    password: Secret
    server: str  # TODO: Fix so takes server or host key
    port: int
    database: str
    schema: str
    driver: str
    encrypt: bool


_TARGET_REGISTRY: dict[str, type[ProfileTarget]] = {
    "duckdb": DuckDBTarget,
    "postgres": DatabaseTarget,
    "mysql": MySQLTarget,
    "sqlserver": MSSQLTarget,
}


class Profiles:
    def __init__(self, path: Path):
        self.path = path
        self.config: dict[str, Any] = yaml.safe_load(self.path.read_text()) or {}

    @classmethod
    def locate(cls, project_root: str) -> "Profiles | None":
        candidate = cls._search_dirs(project_root)
        if not candidate:
            return None
        if candidate.exists():
            return cls(candidate)

        return None

    @staticmethod
    def _search_dirs(project_root: str) -> Path | None:
        profile_paths = [Path(project_root), Path.home().joinpath(".dbt")]

        for profile_path in profile_paths:
            if Path(profile_path.joinpath("profiles.yml")).exists():
                return Path(profile_path.joinpath("profiles.yml"))

        return None

    def resolve(self, profile_name: str, target: str | None = None) -> ProfileTarget:
        if not target:
            target = self.config[profile_name]["target"]

        profile_target = self.config[profile_name]["outputs"][target]

        return ProfileTarget.from_dict(profile_target)
