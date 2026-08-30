"""Ensure a release tag exactly matches the package version."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_project_version(pyproject_path: Path) -> str:
    """Read the PEP 621 project version from a pyproject file."""
    with pyproject_path.open("rb") as pyproject_file:
        document = tomllib.load(pyproject_file)

    try:
        version = document["project"]["version"]
    except KeyError as error:
        raise ValueError("pyproject.toml has no project.version") from error

    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml project.version must be a non-empty string")
    return version


def validate_tag(tag: str, version: str) -> None:
    """Raise when *tag* is not the canonical release tag for *version*."""
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"release tag {tag!r} does not match expected tag {expected_tag!r}")


def main(arguments: list[str] | None = None) -> int:
    """Validate the supplied tag and report the matching project version."""
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 1:
        print("usage: check_release_tag.py <tag>", file=sys.stderr)
        return 2

    version = read_project_version(REPOSITORY_ROOT / "pyproject.toml")
    try:
        validate_tag(arguments[0], version)
    except ValueError as error:
        print(f"release validation failed: {error}", file=sys.stderr)
        return 1

    print(f"release tag {arguments[0]!r} matches project version {version!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
