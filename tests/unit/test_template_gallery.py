from pathlib import Path

import pytest

from tronic_printer.template_gallery import (
    copy_template,
    describe_templates,
    template_names,
)


def test_gallery_contains_every_documented_example() -> None:
    assert template_names() == [
        "checklist",
        "event-ticket",
        "inventory-label",
        "kitchen-ticket",
        "parcel-drop-in",
        "photo-note",
        "postcard-address",
        "receipt",
        "shipping-label",
    ]
    for template in describe_templates():
        assert Path(template["template"]).is_file()
        assert Path(template["data"]).is_file()


def test_copy_template_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown template"):
        copy_template("missing", tmp_path / "copy")
