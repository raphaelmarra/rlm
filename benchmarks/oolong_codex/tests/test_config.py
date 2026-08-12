from pathlib import Path

import pytest
from oolong_codex.config import load_config


def test_load_config_resolves_artifacts_relative_to_project(tmp_path: Path) -> None:
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(
        """
[dataset]
name = "oolongbench/oolong-synth"
revision = "f0d59eaf0febf130664cfceb710436c8e3216b2b"
split = "validation"
subset = "trec_coarse"
context_len = 131072
num_cases = 25
seed = 42
[model]
name = "gpt-5.6-terra"
reasoning_effort = "medium"
max_depth = 1
max_iterations = 12
max_timeout = 1800
[evaluation]
bootstrap_samples = 10000
quality_threshold = 0.10
[paths]
artifacts_dir = "artifacts"
[arms]
A = "baseline"
B = "rlm"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.num_cases == 25
    assert config.dataset_revision == "f0d59eaf0febf130664cfceb710436c8e3216b2b"
    assert config.artifacts_dir == tmp_path / "artifacts"
    assert config.arms == {"A": "baseline", "B": "rlm"}


def test_load_config_rejects_wrong_arm_assignment(tmp_path: Path) -> None:
    source = (Path(__file__).parents[1] / "benchmark.toml").read_text(encoding="utf-8")
    path = tmp_path / "benchmark.toml"
    path.write_text(source.replace('B = "rlm"', 'B = "baseline"'), encoding="utf-8")

    with pytest.raises(ValueError, match="baseline and rlm"):
        load_config(path)
