from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str | None = None
