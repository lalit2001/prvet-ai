from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

Kind = Literal["function", "method", "class", "interface", "const", "type", "var"]
Precision = Literal["precise", "heuristic"]
RefKind = Literal["call", "import", "inherit", "implement", "read", "write", "type_ref"]


@dataclass(frozen=True)
class Symbol:
    id: UUID
    repo_id: UUID
    file_id: UUID
    symbol_key: str
    name: str
    kind: Kind
    start_line: int
    end_line: int
    signature: str | None = None
    visibility: str | None = None
    docstring: str | None = None
    precision: Precision = "heuristic"


@dataclass(frozen=True)
class SymbolReference:
    from_symbol_id: UUID | None
    to_symbol_id: UUID
    file_id: UUID
    line: int
    ref_kind: RefKind
    precision: Precision = "heuristic"
