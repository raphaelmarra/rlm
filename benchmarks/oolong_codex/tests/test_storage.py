from pathlib import Path

from oolong_codex.storage import read_json, write_json_atomic


def test_atomic_json_round_trip_leaves_no_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "result.json"

    write_json_atomic(target, {"response": "approximately ≈"})

    assert read_json(target) == {"response": "approximately ≈"}
    assert list(tmp_path.iterdir()) == [target]
