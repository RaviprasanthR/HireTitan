"""The shipped seed files are found in a source checkout and in the Docker image."""

from __future__ import annotations

from pathlib import Path

from hiretitan.seed_dir import resolve_seed_dir


def test_the_environment_setting_wins(tmp_path: Path) -> None:
    assert resolve_seed_dir({"HIRETITAN_SEED_DIR": str(tmp_path)}) == tmp_path


def test_a_blank_setting_falls_back_to_the_checkout_folder() -> None:
    folder = resolve_seed_dir({"HIRETITAN_SEED_DIR": ""})

    assert folder == resolve_seed_dir({})
    assert (folder / "title_synonyms.yaml").is_file()
