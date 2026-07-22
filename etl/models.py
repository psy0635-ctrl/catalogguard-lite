from dataclasses import dataclass


@dataclass(frozen=True)
class ETLProfile:
    name: str
    version: str
    source_columns: dict[str, str | tuple[str, ...]]
    required_source_columns: tuple[str, ...]
    defaults: dict[str, str]
