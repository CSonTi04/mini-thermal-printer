import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from tronic_printer import html_template
from tronic_printer.html_template import (
    HtmlTemplateConfig,
    _as_document,
    _request_is_allowed,
    parse_template_values,
    prepare_html,
    render_template,
)
from tronic_printer.preprocessing import DitherMode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_template_values_accept_json_scalars_and_plain_strings() -> None:
    assert parse_template_values(["count=3", "enabled=true", "label=hello"]) == {
        "count": 3,
        "enabled": True,
        "label": "hello",
    }

    with pytest.raises(ValueError, match="NAME=VALUE"):
        parse_template_values(["missing-separator"])


def test_jinja_template_supports_loops_and_escapes_data(tmp_path: Path) -> None:
    template = tmp_path / "receipt.html"
    template.write_text(
        '<main class="receipt">{% for item in items %}<b>{{ item }}</b>{% endfor %}</main>',
        encoding="utf-8",
    )

    rendered = render_template(template, {"items": ["tea", "<script>bad</script>"]})

    assert "<b>tea</b>" in rendered
    assert "&lt;script&gt;bad&lt;/script&gt;" in rendered
    assert "<script>bad</script>" not in rendered


def test_missing_template_value_is_an_error(tmp_path: Path) -> None:
    template = tmp_path / "receipt.html"
    template.write_text('<main class="receipt">{{ missing }}</main>', encoding="utf-8")

    with pytest.raises(ValueError, match="cannot render Jinja template"):
        render_template(template)


def test_printer_image_embeds_one_bit_local_asset_and_rejects_escape(tmp_path: Path) -> None:
    image = Image.new("L", (4, 1))
    image.putdata([0, 80, 180, 255])
    image.save(tmp_path / "photo.png")
    template = tmp_path / "receipt.html"
    template.write_text(
        "{{ printer_image('photo.png', width=4, dither='threshold') }}",
        encoding="utf-8",
    )

    uri = render_template(template)
    encoded = uri.removeprefix("data:image/png;base64,")
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as embedded:
        assert embedded.size == (4, 1)
        assert set(embedded.convert("L").tobytes()) <= {0, 255}

    template.write_text("{{ printer_image('../outside.png', width=4) }}", encoding="utf-8")
    with pytest.raises(ValueError, match="asset"):
        render_template(template)


def test_qr_and_barcode_helpers_embed_local_data_uris(tmp_path: Path) -> None:
    template = tmp_path / "codes.html"
    template.write_text(
        "{{ qr_code('https://example.test/42', scale=2) }}\n"
        "{{ barcode('PKG-0042', include_text=false) }}",
        encoding="utf-8",
    )

    qr_uri, barcode_uri = render_template(template).splitlines()
    qr_data = base64.b64decode(qr_uri.removeprefix("data:image/png;base64,"))
    with Image.open(io.BytesIO(qr_data)) as qr:
        assert qr.width == qr.height
        assert set(qr.convert("L").tobytes()) <= {0, 255}

    barcode_data = base64.b64decode(
        barcode_uri.removeprefix("data:image/svg+xml;base64,")
    )
    assert b"<svg" in barcode_data
    assert b"DOCTYPE" not in barcode_data
    assert b"PKG-0042" not in barcode_data


@pytest.mark.parametrize(
    "expression, message",
    [
        ("qr_code('', scale=4)", "cannot be empty"),
        ("qr_code('value', scale=0)", "scale"),
        ("barcode('', include_text=false)", "cannot be empty"),
        ("barcode('42', symbology='ean13')", "symbology"),
    ],
)
def test_machine_code_helpers_validate_options(
    expression: str,
    message: str,
    tmp_path: Path,
) -> None:
    template = tmp_path / "invalid.html"
    template.write_text("{{ " + expression + " }}", encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        render_template(template)


def test_browser_policy_allows_only_document_and_template_assets(tmp_path: Path) -> None:
    root = (tmp_path / "assets").resolve()
    root.mkdir()
    asset = root / "logo.svg"
    asset.write_text("<svg/>", encoding="utf-8")
    document = (tmp_path / "rendered.html").resolve()
    document.write_text("", encoding="utf-8")

    assert _request_is_allowed(document.as_uri(), root, document)
    assert _request_is_allowed(asset.as_uri(), root, document)
    assert _request_is_allowed("data:image/png;base64,AA==", root, document)
    assert not _request_is_allowed("https://example.com/tracker.png", root, document)
    assert not _request_is_allowed((tmp_path / "secret.txt").as_uri(), root, document)


def test_builtin_document_css_defines_384_dot_contract(tmp_path: Path) -> None:
    document = _as_document('<main class="receipt"></main>', tmp_path.resolve(), 384)

    assert "--printer-width: 384px" in document
    assert "--paper-center-offset: 8px" in document
    assert ".receipt--padded" in document
    assert ".receipt--paper-centered" in document
    assert ".photo" in document
    assert ".machine-code" in document
    assert ".qr-code" in document
    assert ".barcode" in document
    assert ".no-break" in document


def test_prepare_html_uses_browser_capture_then_shared_dithering(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    template = tmp_path / "receipt.html"
    template.write_text('<main class="receipt">{{ title }}</main>', encoding="utf-8")
    screenshot = Image.new("L", (384, 2), color=255)
    screenshot.paste(0, (0, 0, 192, 2))
    output = io.BytesIO()
    screenshot.save(output, format="PNG")

    def capture(rendered: str, root: Path, width: int) -> bytes:
        assert "Hello" in rendered
        assert root == tmp_path.resolve()
        assert width == 384
        return output.getvalue()

    monkeypatch.setattr(html_template, "_capture_receipt_png", capture)
    prepared = prepare_html(
        template,
        {"title": "Hello"},
        HtmlTemplateConfig(dither=DitherMode.THRESHOLD, threshold=128),
    )

    assert prepared.raster.width == 384
    assert prepared.raster.height == 2
    assert prepared.prepared.black_pixels == 384
    assert set(prepared.prepared.preview.tobytes()) <= {0, 255}


@pytest.mark.parametrize(
    "demo, template_name",
    [
        ("receipt", "receipt.html"),
        ("shipping-label", "shipping-label.html"),
        ("postcard-address", "postcard-address.html"),
        ("parcel-drop-in", "parcel-drop-in.html"),
        ("checklist", "checklist.html"),
        ("kitchen-ticket", "kitchen-ticket.html"),
        ("inventory-label", "inventory-label.html"),
        ("event-ticket", "event-ticket.html"),
        ("photo-note", "photo-note.html"),
    ],
)
def test_every_example_template_renders_from_sample_data(
    demo: str,
    template_name: str,
) -> None:
    example = REPOSITORY_ROOT / "examples" / demo
    data = json.loads((example / "data.json").read_text(encoding="utf-8"))

    rendered = render_template(example / template_name, data)

    assert 'class="receipt ' in rendered
    assert "{{" not in rendered
    assert "{%" not in rendered


def test_postcard_example_has_four_parts_and_three_rules() -> None:
    example = REPOSITORY_ROOT / "examples" / "postcard-address"
    data = json.loads((example / "data.json").read_text(encoding="utf-8"))

    rendered = render_template(example / "postcard-address.html", data)

    assert len(data["address_lines"]) == 4
    assert rendered.count('class="address-line address-line--ruled"') == 3
    assert rendered.count('class="address-line"') == 1
    assert "Return address" not in rendered
    assert "AIR MAIL" not in rendered


def test_parcel_drop_in_example_has_no_banner_or_barcode() -> None:
    example = REPOSITORY_ROOT / "examples" / "parcel-drop-in"
    data = json.loads((example / "data.json").read_text(encoding="utf-8"))

    rendered = render_template(example / "parcel-drop-in.html", data)

    assert "PARCEL DROP-IN" not in rendered
    assert "Simple shipping form" not in rendered
    assert "data:image/svg+xml" not in rendered
    assert "<img" not in rendered
    assert data["tracking_number"] in rendered
