from __future__ import annotations

import pytest
from oolong_codex.scorer import paired_bootstrap, parse_answer, score_answer


@pytest.mark.parametrize(
    ("gold", "answer_type", "output", "expected"),
    [
        ("['entity']", "ANSWER_TYPE.LABEL", "Label: entity", 1.0),
        ("[10]", "ANSWER_TYPE.NUMERIC", "Answer: 12", 0.5625),
        ("[10]", "ANSWER_TYPE.NUMERIC", "Answer: 15", 0.2373046875),
        (
            "['more common than']",
            "ANSWER_TYPE.LABEL",
            "more common than",
            1.0,
        ),
    ],
)
def test_score_answer_matches_upstream_literals(
    gold: str, answer_type: str, output: str, expected: float
) -> None:
    assert score_answer(gold, answer_type, output) == expected


def test_parse_answer_prefers_the_last_comparison_phrase() -> None:
    assert parse_answer("First: less common than; final: same frequency as") == "same frequency as"


def test_score_answer_parses_upstream_date_format() -> None:
    assert (
        score_answer(
            "[datetime.date(2024, 2, 29)]",
            "ANSWER_TYPE.DATE",
            "Answer: February 29, 2024",
        )
        == 1.0
    )


def test_score_answer_accepts_label_embedded_in_a_long_response() -> None:
    assert (
        score_answer(
            "['description and abstract concept']",
            "ANSWER_TYPE.LABEL",
            "The correct classification is description and abstract concept because it is not a person or place.",
        )
        == 1.0
    )


def test_paired_bootstrap_of_uniform_gain_has_exact_interval() -> None:
    assert paired_bootstrap([0.25] * 25, samples=1_000, seed=42) == (0.25, 0.25)


def test_paired_bootstrap_is_deterministic_for_nonuniform_deltas() -> None:
    assert paired_bootstrap([0.0, 1.0], samples=10, seed=7) == (0.0, 1.0)
