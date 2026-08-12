"""OOLONG answer scoring ported from training/environments/oolong/oolong/env.py.

The parsing and per-answer scoring behavior below intentionally matches the
official upstream OOLONG environment.  The paired bootstrap is benchmark
reporting logic layered on top of those official per-case scores.
"""

from __future__ import annotations

import ast
import random
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import dateutil.parser

COMPARISON_PHRASES = (
    "more common than",
    "less common than",
    "same frequency as",
)


def find_comparison_phrase(output: str) -> str | None:
    output_lower = output.lower()
    hits = [
        (output_lower.rfind(phrase), phrase)
        for phrase in COMPARISON_PHRASES
        if phrase in output_lower
    ]
    return max(hits)[1] if hits else None


def parse_answer(output: str) -> str:
    comparison_phrase = find_comparison_phrase(output)
    if comparison_phrase is not None:
        return comparison_phrase
    if ":" not in output:
        if len(output) < 20:
            return output
        return output.split()[-1]
    candidate = output.split(":")[-1].strip().replace("*", "").replace("[", "").replace("]", "")
    return candidate


def score_answer(gold: str, answer_type: str, output: str) -> float:
    try:
        if "datetime" in gold:
            parsed_gold: Any = datetime.strptime(gold, "[datetime.date(%Y, %m, %d)]")
        else:
            parsed_gold = ast.literal_eval(gold)[0]
    except Exception:
        parsed_gold = gold

    trimmed = parse_answer(output)
    gold_string = str(parsed_gold)

    if trimmed == gold_string or trimmed.lower() == gold_string.lower():
        return 1.0

    if answer_type == "ANSWER_TYPE.NUMERIC":
        try:
            return 0.75 ** abs(int(parsed_gold) - int(trimmed))
        except Exception:
            return 0.0
    if answer_type == "ANSWER_TYPE.DATE":
        try:
            return 1.0 if dateutil.parser.parse(trimmed) == parsed_gold else 0.0
        except Exception:
            return 0.0

    if gold_string and gold_string.lower() not in [phrase.lower() for phrase in COMPARISON_PHRASES]:
        if gold_string.lower() in output.lower():
            return 1.0

    return 0.0


def paired_bootstrap(deltas: Sequence[float], samples: int, seed: int) -> tuple[float, float]:
    if not deltas:
        raise ValueError("deltas must not be empty")
    if samples <= 0:
        raise ValueError("samples must be positive")

    generator = random.Random(seed)
    sample_means = sorted(
        sum(generator.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(samples)
    )
    return sample_means[int(samples * 0.025)], sample_means[min(int(samples * 0.975), samples - 1)]
