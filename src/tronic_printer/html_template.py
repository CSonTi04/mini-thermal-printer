"""Sandboxed Jinja templates rendered to the printer raster through Chromium."""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image

from tronic_printer.domain import RasterImage
from tronic_printer.preprocessing import (
    DitherMode,
    EffectSpec,
    ImagePreparationConfig,
    PreparedImage,
    build_effect_registry,
    prepare_image,
)
from tronic_printer.protocol import MAX_PRINT_WIDTH

PRINTER_CSS = """
:root {
  --printer-width: 384px;
  --page-padding: 16px;
  --paper-center-offset: 8px;
  --spacing-unit: 4px;
  --font-family: Arial, Helvetica, sans-serif;
  --font-size: 16px;
  color-scheme: light;
}

html, body {
  margin: 0;
  padding: 0;
  width: var(--printer-width);
  min-width: var(--printer-width);
  background: white;
}

*, *::before, *::after { box-sizing: border-box; }

.receipt {
  display: block;
  width: var(--printer-width);
  min-height: 1px;
  margin: 0;
  overflow: hidden;
  background: white;
  color: black;
  font-family: var(--font-family);
  font-size: var(--font-size);
}

.receipt--padded { padding: var(--page-padding); }
.receipt--paper-centered {
  padding-left: calc(var(--page-padding) + var(--paper-center-offset));
  padding-right: calc(var(--page-padding) - var(--paper-center-offset));
}
.full-width { display: block; width: 100%; max-width: 100%; }
.text-left { text-align: left; }
.text-center { text-align: center; }
.text-right { text-align: right; }
.row { display: flex; flex-direction: row; align-items: baseline; gap: var(--spacing-unit); }
.column { display: flex; flex-direction: column; gap: var(--spacing-unit); }
.space-between { justify-content: space-between; }
.no-break { break-inside: avoid; page-break-inside: avoid; }

.photo {
  display: block;
  width: 100%;
  height: auto;
  max-width: 100%;
  object-fit: contain;
  image-rendering: pixelated;
}

.machine-code {
  display: block;
  max-width: 100%;
  height: auto;
  margin-inline: auto;
  image-rendering: pixelated;
}

.qr-code { width: auto; }
.barcode { width: 100%; }

.p-0 { padding: 0; }
.p-1 { padding: var(--spacing-unit); }
.p-2 { padding: calc(2 * var(--spacing-unit)); }
.p-3 { padding: calc(3 * var(--spacing-unit)); }
.p-4 { padding: calc(4 * var(--spacing-unit)); }
.px-1 { padding-inline: var(--spacing-unit); }
.px-2 { padding-inline: calc(2 * var(--spacing-unit)); }
.py-1 { padding-block: var(--spacing-unit); }
.py-2 { padding-block: calc(2 * var(--spacing-unit)); }
.m-0 { margin: 0; }
.mt-1 { margin-top: var(--spacing-unit); }
.mt-2 { margin-top: calc(2 * var(--spacing-unit)); }
.mb-1 { margin-bottom: var(--spacing-unit); }
.mb-2 { margin-bottom: calc(2 * var(--spacing-unit)); }
""".strip()


@dataclass(frozen=True, slots=True)
class HtmlTemplateConfig:
    """HTML capture and final one-bit conversion settings."""

    width: int = MAX_PRINT_WIDTH
    threshold: int = 180
    dither: DitherMode = DitherMode.THRESHOLD
    effects: tuple[EffectSpec, ...] = ()

    def __post_init__(self) -> None:
        if self.width != MAX_PRINT_WIDTH:
            raise ValueError(f"HTML templates must be exactly {MAX_PRINT_WIDTH} dots wide")
        if self.threshold not in range(256):
            raise ValueError("threshold must be between 0 and 255")


@dataclass(frozen=True, slots=True)
class PreparedHtml:
    """A rendered HTML receipt and its exact printable result."""

    prepared: PreparedImage
    template: Path

    @property
    def raster(self) -> RasterImage:
        return self.prepared.raster

    def save_preview(self, path: str | Path) -> None:
        self.prepared.save_preview(path)

    def summary(self) -> dict[str, object]:
        return self.prepared.summary() | {"template": str(self.template)}


def load_template_data(path: str | Path | None) -> dict[str, Any]:
    """Load a JSON object used as the Jinja template context."""

    if path is None:
        return {}
    if str(path) == "-":
        value = json.load(sys.stdin)
    else:
        with Path(path).open(encoding="utf-8") as source:
            value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError("template data must be a JSON object")
    return value


def parse_template_values(values: Sequence[str]) -> dict[str, Any]:
    """Parse repeatable NAME=JSON_VALUE overrides for automation-friendly calls."""

    result: dict[str, Any] = {}
    for assignment in values:
        name, separator, raw_value = assignment.partition("=")
        name = name.strip()
        if not separator or not name:
            raise ValueError(f"invalid template value {assignment!r}; expected NAME=VALUE")
        try:
            result[name] = json.loads(raw_value)
        except json.JSONDecodeError:
            result[name] = raw_value
    return result


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_asset(root: Path, value: str | Path) -> Path:
    raw = str(value)
    if urlparse(raw).scheme or Path(raw).is_absolute():
        raise ValueError(f"asset path must be relative to the template directory: {raw!r}")
    resolved = (root / raw).resolve(strict=False)
    if not _is_within(resolved, root):
        raise ValueError(f"asset escapes the template directory: {raw!r}")
    if not resolved.exists():
        raise ValueError(f"asset does not exist: {raw!r}")
    if not resolved.is_file():
        raise ValueError(f"asset is not a file: {raw!r}")
    return resolved


def _printer_image_helper(root: Path) -> Callable[..., str]:
    def printer_image(
        path: str,
        *,
        width: int,
        dither: str = DitherMode.FLOYD_STEINBERG.value,
        threshold: int = 128,
        effects: Sequence[str] = (),
    ) -> str:
        """Embed a locally confined image after independent one-bit preparation."""

        asset = _resolve_asset(root, path)
        config = ImagePreparationConfig(
            width=width,
            threshold=threshold,
            dither=DitherMode(dither),
            effects=tuple(EffectSpec.parse(value) for value in effects),
        )
        with Image.open(asset) as image:
            prepared = prepare_image(image, config, registry=build_effect_registry())
        output = io.BytesIO()
        prepared.preview.save(output, format="PNG", optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    return printer_image


def _qr_code_helper() -> Callable[..., str]:
    def qr_code(
        value: object,
        *,
        scale: int = 4,
        border: int = 4,
        error: str = "m",
    ) -> str:
        """Generate a black-and-white QR code as an embedded PNG."""

        try:
            import segno
        except ImportError as import_error:
            raise ImportError(
                "QR generation requires Segno; install tronic-mini-printer[html]"
            ) from import_error
        text = str(value)
        if not text:
            raise ValueError("QR code value cannot be empty")
        if not isinstance(scale, int) or not 1 <= scale <= 16:
            raise ValueError("QR code scale must be an integer between 1 and 16")
        if not isinstance(border, int) or not 0 <= border <= 16:
            raise ValueError("QR code border must be an integer between 0 and 16")
        error_level = error.lower()
        if error_level not in {"l", "m", "q", "h"}:
            raise ValueError("QR code error level must be l, m, q, or h")
        code = segno.make_qr(text, error=error_level)
        return code.png_data_uri(
            scale=scale,
            border=border,
            dark="black",
            light="white",
        )

    return qr_code


def _barcode_helper() -> Callable[..., str]:
    def barcode(
        value: object,
        *,
        symbology: str = "code128",
        module_width: float = 0.25,
        module_height: float = 12.0,
        quiet_zone: float = 2.0,
        include_text: bool = True,
    ) -> str:
        """Generate a Code 128 or Code 39 barcode as an embedded SVG."""

        try:
            import barcode as barcode_library
            from barcode.errors import BarcodeError
            from barcode.writer import SVGWriter
        except ImportError as import_error:
            raise ImportError(
                "barcode generation requires python-barcode; "
                "install tronic-mini-printer[html]"
            ) from import_error
        text = str(value)
        if not text:
            raise ValueError("barcode value cannot be empty")
        normalized_symbology = symbology.lower()
        if normalized_symbology not in {"code128", "code39"}:
            raise ValueError("barcode symbology must be code128 or code39")
        dimensions = {
            "module_width": module_width,
            "module_height": module_height,
            "quiet_zone": quiet_zone,
        }
        if any(not isinstance(value, (int, float)) for value in dimensions.values()):
            raise ValueError("barcode dimensions must be numbers")
        if not 0.1 <= module_width <= 1:
            raise ValueError("barcode module_width must be between 0.1 and 1 mm")
        if not 4 <= module_height <= 40:
            raise ValueError("barcode module_height must be between 4 and 40 mm")
        if not 0 <= quiet_zone <= 10:
            raise ValueError("barcode quiet_zone must be between 0 and 10 mm")
        output = io.BytesIO()
        try:
            code = barcode_library.get(
                normalized_symbology,
                text,
                writer=SVGWriter(),
            )
            code.write(
                output,
                {
                    **dimensions,
                    "write_text": include_text,
                    "font_size": 8,
                    "text_distance": 1.5,
                    "background": "white",
                    "foreground": "black",
                    "center_text": True,
                    "with_doctype": False,
                },
            )
        except (BarcodeError, ValueError) as error:
            raise ValueError(f"cannot generate {normalized_symbology} barcode: {error}") from error
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    return barcode


def _halftone_qr_code_helper(root: Path) -> Callable[..., str]:
    def halftone_qr_code(
        text: object,
        image_path: str,
        *,
        grid: int = 6,
        core: int = 2,
        dither: str = "floyd-steinberg",
        error_level: str = "h",
        marks: str = "all",
        border: int = 4,
        contrast: float = 1.0,
        brightness: float = 1.0,
        invert: bool = False,
        mask: int | None = None,
    ) -> str:
        """Generate a halftone QR code as an embedded PNG data URI.

        The *image_path* must be a path relative to the template directory.
        The returned PNG is sized to the nearest fit in 384 printer dots.
        """
        from tronic_printer.halftone_qr import (
            HalftoneDither,
            HalftoneOptions,
            MarksMode,
            halftone_qr_to_raster,
            render_halftone_qr,
        )

        content = str(text)
        if not content:
            raise ValueError("halftone_qr_code: text cannot be empty")
        asset = _resolve_asset(root, image_path)
        options = HalftoneOptions(
            grid=grid,
            core=core,
            dither=HalftoneDither(dither),
            error_level=error_level,
            marks=MarksMode(marks),
            border=border,
            contrast=contrast,
            brightness=brightness,
            invert=invert,
            mask=mask,
        )
        with Image.open(asset) as img:
            img.load()
            rendered = render_halftone_qr(content, img, options)
        scaled, _dps = halftone_qr_to_raster(rendered)
        output = io.BytesIO()
        scaled.convert("L").save(output, format="PNG", optimize=True)
        encoded = base64.b64encode(output.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    return halftone_qr_code


def render_template(template_path: str | Path, data: Mapping[str, Any] | None = None) -> str:
    """Render one sandboxed Jinja template rooted at its own directory."""

    try:
        from jinja2 import (
            FileSystemLoader,
            StrictUndefined,
            TemplateError,
            TemplateNotFound,
            select_autoescape,
        )
        from jinja2.sandbox import SandboxedEnvironment
    except ImportError as error:
        raise ImportError(
            "HTML templates require Jinja2; install tronic-mini-printer[html]"
        ) from error

    source = Path(template_path).resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"template is not a file: {source}")
    root = source.parent.resolve()

    class ConfinedLoader(FileSystemLoader):
        def get_source(
            self,
            environment: Any,
            template: str,
        ) -> tuple[str, str, Callable[[], bool]]:
            contents, filename, current = super().get_source(environment, template)
            if not _is_within(Path(filename).resolve(strict=True), root):
                raise TemplateNotFound(template)
            return contents, filename, current

    environment = SandboxedEnvironment(
        loader=ConfinedLoader(root, followlinks=False),
        autoescape=select_autoescape(("html", "htm", "xml"), default=True),
        undefined=StrictUndefined,
        enable_async=False,
    )
    environment.globals["printer_image"] = _printer_image_helper(root)
    environment.globals["qr_code"] = _qr_code_helper()
    environment.globals["barcode"] = _barcode_helper()
    environment.globals["halftone_qr_code"] = _halftone_qr_code_helper(root)
    try:
        return environment.get_template(source.name).render(dict(data or {}))
    except TemplateError as error:
        raise ValueError(f"cannot render Jinja template: {error}") from error


def _as_document(rendered: str, root: Path, width: int) -> str:
    base = f'<base href="{root.as_uri().rstrip("/")}/">'
    style = PRINTER_CSS.replace("--printer-width: 384px", f"--printer-width: {width}px")
    additions = f"{base}<style data-tronic-printer>{style}</style>"
    head = re.search(r"<head(?:\s[^>]*)?>", rendered, flags=re.IGNORECASE)
    if head:
        return rendered[: head.end()] + additions + rendered[head.end() :]
    return f"<!doctype html><html><head>{additions}</head><body>{rendered}</body></html>"


def _file_url_path(url: str) -> Path:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return Path(path).resolve()


def _request_is_allowed(url: str, asset_root: Path, document: Path) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"data", "blob", "about"}:
        return True
    if parsed.scheme != "file":
        return False
    try:
        path = _file_url_path(url)
    except (OSError, ValueError):
        return False
    return path == document or _is_within(path, asset_root)


def _launch_browser(chromium: Any, playwright_error: type[Exception]) -> Any:
    """Prefer an installed Chromium browser before Playwright's optional download."""

    launch_options = {
        "headless": True,
        "args": ["--allow-file-access-from-files"],
    }
    channels = ("msedge", "chrome") if sys.platform == "win32" else ("chrome",)
    last_error: Exception | None = None
    for channel in channels:
        try:
            return chromium.launch(channel=channel, **launch_options)
        except playwright_error as error:
            last_error = error
    try:
        return chromium.launch(**launch_options)
    except playwright_error as error:
        raise RuntimeError(
            "no usable Chromium browser was found; install Chrome/Edge or run "
            "'playwright install chromium'"
        ) from (last_error or error)


def _capture_receipt_png(rendered: str, asset_root: Path, width: int) -> bytes:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise ImportError(
            "HTML rendering requires Playwright; install tronic-mini-printer[html] "
            "and run 'playwright install chromium'"
        ) from error

    document_html = _as_document(rendered, asset_root, width)
    try:
        with tempfile.TemporaryDirectory(prefix="tronic-html-") as temporary:
            document = Path(temporary).resolve() / "receipt.html"
            document.write_text(document_html, encoding="utf-8")
            with sync_playwright() as playwright:
                browser = _launch_browser(playwright.chromium, PlaywrightError)
                try:
                    context = browser.new_context(
                        viewport={"width": width, "height": 800},
                        device_scale_factor=1,
                        java_script_enabled=False,
                        color_scheme="light",
                        reduced_motion="reduce",
                    )

                    def route_request(route: Any) -> None:
                        if _request_is_allowed(route.request.url, asset_root, document):
                            route.continue_()
                        else:
                            route.abort("blockedbyclient")

                    context.route("**/*", route_request)
                    page = context.new_page()
                    page.goto(document.as_uri(), wait_until="load")
                    page.evaluate("() => document.fonts.ready")
                    receipt = page.locator(".receipt")
                    count = receipt.count()
                    if count != 1:
                        raise ValueError(
                            f"template must contain exactly one .receipt element; found {count}"
                        )
                    box = receipt.bounding_box()
                    if box is None or round(box["width"]) != width:
                        actual = "unknown" if box is None else round(box["width"])
                        raise ValueError(
                            f".receipt must render at exactly {width}px wide; got {actual}"
                        )
                    return receipt.screenshot(
                        type="png",
                        animations="disabled",
                        caret="hide",
                        scale="css",
                    )
                finally:
                    browser.close()
    except PlaywrightError as error:
        raise RuntimeError(f"Chromium could not render the template: {error}") from error


def prepare_html(
    template_path: str | Path,
    data: Mapping[str, Any] | None = None,
    config: HtmlTemplateConfig | None = None,
) -> PreparedHtml:
    """Render HTML, capture its receipt element, and run the shared raster pipeline."""

    config = config or HtmlTemplateConfig()
    template = Path(template_path).resolve(strict=True)
    rendered = render_template(template, data)
    screenshot = _capture_receipt_png(rendered, template.parent.resolve(), config.width)
    with Image.open(io.BytesIO(screenshot)) as image:
        prepared = prepare_image(
            image,
            ImagePreparationConfig(
                width=config.width,
                threshold=config.threshold,
                dither=config.dither,
                effects=config.effects,
            ),
            registry=build_effect_registry(),
        )
    return PreparedHtml(prepared=prepared, template=template)
