"""Discovery and copying for the bundled HTML template gallery."""

from __future__ import annotations

import shutil
import sysconfig
from pathlib import Path


def gallery_root() -> Path:
    """Return the gallery root in a source checkout or installed environment."""

    source_gallery = Path(__file__).resolve().parents[2] / "examples"
    installed_gallery = (
        Path(sysconfig.get_path("data")) / "share" / "tronic-mini-printer" / "examples"
    )
    for candidate in (source_gallery, installed_gallery):
        if (candidate / "README.md").is_file():
            return candidate
    raise FileNotFoundError(
        "template gallery is unavailable; reinstall tronic-mini-printer 0.3.0 or newer"
    )


def template_names() -> list[str]:
    """List bundled examples that contain both a template and sample data."""

    root = gallery_root()
    return sorted(
        directory.name
        for directory in root.iterdir()
        if directory.is_dir()
        and (directory / f"{directory.name}.html").is_file()
        and (directory / "data.json").is_file()
    )


def describe_templates() -> list[dict[str, str]]:
    """Describe the files available for each bundled example."""

    root = gallery_root()
    return [
        {
            "name": name,
            "template": str(root / name / f"{name}.html"),
            "data": str(root / name / "data.json"),
        }
        for name in template_names()
    ]


def copy_template(name: str, destination: str | Path) -> Path:
    """Copy one bundled example into a new editable directory."""

    if name not in template_names():
        available = ", ".join(template_names())
        raise ValueError(f"unknown template {name!r}; available templates: {available}")
    target = Path(destination).resolve()
    if target.exists():
        raise FileExistsError(f"destination already exists: {target}")
    shutil.copytree(gallery_root() / name, target)
    return target
