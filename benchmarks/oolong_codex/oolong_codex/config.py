"""Frozen configuration and artifact layout for the OOLONG benchmark."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class BenchmarkConfig:
    dataset_name: str
    dataset_revision: str
    dataset_split: str
    dataset_subset: str
    context_len: int
    num_cases: int
    seed: int
    model_name: str
    reasoning_effort: str
    max_depth: int
    max_iterations: int
    max_timeout: int
    bootstrap_samples: int
    quality_threshold: float
    artifacts_dir: Path
    arms: Mapping[str, str]


@dataclass(frozen=True)
class BenchmarkPaths:
    """Derive every durable artifact location from one artifact root."""

    artifacts_dir: Path

    @property
    def dataset_dir(self) -> Path:
        return self.artifacts_dir / "dataset"

    @property
    def manifest_path(self) -> Path:
        return self.dataset_dir / "manifest.json"

    @property
    def raw_dir(self) -> Path:
        return self.artifacts_dir / "raw"

    @property
    def attempts_dir(self) -> Path:
        return self.artifacts_dir / "attempts"

    @property
    def scores_dir(self) -> Path:
        return self.artifacts_dir / "scores"

    @property
    def reports_dir(self) -> Path:
        return self.artifacts_dir / "reports"

    def case_dir(self, case_id: str) -> Path:
        return self.dataset_dir / "cases" / case_id

    def raw_path(self, arm: str, case_id: str) -> Path:
        return self.raw_dir / arm / f"{case_id}.json"

    def attempt_path(self, arm: str, case_id: str) -> Path:
        return self.attempts_dir / arm / f"{case_id}.json"

    def score_path(self, arm: str) -> Path:
        return self.scores_dir / f"{arm}.json"

    def report_path(self, run_id: str, suffix: str = ".json") -> Path:
        if suffix not in {".json", ".md"}:
            raise ValueError("report suffix must be .json or .md")
        return self.reports_dir / f"{run_id}{suffix}"


def load_config(path: Path) -> BenchmarkConfig:
    """Load benchmark TOML and resolve its artifact root next to the config file."""

    config_path = path.resolve()
    with config_path.open("rb") as handle:
        value = tomllib.load(handle)

    dataset = _section(value, "dataset")
    model = _section(value, "model")
    evaluation = _section(value, "evaluation")
    paths = _section(value, "paths")
    arms = _section(value, "arms")
    _validate_arms(arms)

    config = BenchmarkConfig(
        dataset_name=_string(dataset, "name"),
        dataset_revision=_string(dataset, "revision"),
        dataset_split=_string(dataset, "split"),
        dataset_subset=_string(dataset, "subset"),
        context_len=_integer(dataset, "context_len"),
        num_cases=_integer(dataset, "num_cases"),
        seed=_integer(dataset, "seed"),
        model_name=_string(model, "name"),
        reasoning_effort=_string(model, "reasoning_effort"),
        max_depth=_integer(model, "max_depth"),
        max_iterations=_integer(model, "max_iterations"),
        max_timeout=_integer(model, "max_timeout"),
        bootstrap_samples=_integer(evaluation, "bootstrap_samples"),
        quality_threshold=_number(evaluation, "quality_threshold"),
        artifacts_dir=(config_path.parent / _string(paths, "artifacts_dir")).resolve(),
        arms=MappingProxyType(dict(arms)),
    )
    _validate_limits(config)
    return config


def _section(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = value.get(name)
    if not isinstance(section, dict):
        raise ValueError(f"missing [{name}] configuration section")
    return section


def _string(value: Mapping[str, Any], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise ValueError(f"{name} must be a non-empty string")
    return item


def _integer(value: Mapping[str, Any], name: str) -> int:
    item = value.get(name)
    if not isinstance(item, int) or isinstance(item, bool):
        raise ValueError(f"{name} must be an integer")
    return item


def _number(value: Mapping[str, Any], name: str) -> float:
    item = value.get(name)
    if not isinstance(item, (int, float)) or isinstance(item, bool):
        raise ValueError(f"{name} must be a number")
    return float(item)


def _validate_arms(arms: Mapping[str, Any]) -> None:
    if set(arms) != {"A", "B"} or set(arms.values()) != {"baseline", "rlm"}:
        raise ValueError("arms must assign baseline and rlm exactly once to A and B")


def _validate_limits(config: BenchmarkConfig) -> None:
    positive_fields = (
        "context_len",
        "num_cases",
        "max_iterations",
        "max_timeout",
        "bootstrap_samples",
    )
    if any(getattr(config, name) <= 0 for name in positive_fields):
        raise ValueError("benchmark limits must be positive")
    if config.max_depth < 0:
        raise ValueError("max_depth must not be negative")
    if config.quality_threshold < 0:
        raise ValueError("quality_threshold must not be negative")
