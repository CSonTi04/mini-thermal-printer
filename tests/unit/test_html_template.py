import base64
import io
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
    assert ".receipt--padded" in document
    assert ".photo" in document
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
