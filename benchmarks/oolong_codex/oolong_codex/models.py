"""Immutable records exchanged between OOLONG benchmark stages."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CaseRecord:
    """The materialized, gold-separated files for one official case."""

    id: str
    context_path: Path
    question_path: Path
    gold_path: Path
    context_sha256: str
    question_sha256: str


@dataclass(frozen=True)
class RawResult:
    """A durable outcome from one benchmark arm for one case."""

    case_id: str
    arm: str
    response: str
    status: str
    wall_seconds: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    calls: int | None = None
    total_cost: float | None = None
    run_id: str | None = None
    pid: int | None = None
    original_pid: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None
