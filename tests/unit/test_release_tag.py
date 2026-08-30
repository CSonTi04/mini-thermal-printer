from pathlib import Path

import pytest

from scripts import check_release_tag
from scripts.check_release_tag import read_project_version, validate_tag


def test_project_version_is_read(tmp_path: Path) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

    assert read_project_version(pyproject_path) == "1.2.3"


def test_matching_release_tag_is_accepted() -> None:
    validate_tag("v0.1.0", "0.1.0")


@pytest.mark.parametrize("tag", ["0.1.0", "v0.1.1", "release-0.1.0"])
def test_nonmatching_release_tag_is_rejected(tag: str) -> None:
    with pytest.raises(ValueError, match="does not match expected tag"):
        validate_tag(tag, "0.1.0")


def test_main_reports_a_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")
    monkeypatch.setattr(check_release_tag, "REPOSITORY_ROOT", tmp_path)

    assert check_release_tag.main(["v9.9.9"]) == 1
    assert "release validation failed" in capsys.readouterr().err
