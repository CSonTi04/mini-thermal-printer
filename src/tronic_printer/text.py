"""Transport-independent Unicode text layout and font discovery."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tronic_printer.preprocessing import (
    DitherMode,
    ImagePreparationConfig,
    PreparedImage,
    prepare_image,
)
from tronic_printer.protocol import MAX_PRINT_WIDTH

FONT_SUFFIXES = frozenset({".otf", ".ttc", ".ttf"})
DEFAULT_FONT_NAMES = {
    (False, False): "DejaVuSans.ttf",
    (True, False): "DejaVuSans-Bold.ttf",
    (False, True): "DejaVuSans-Oblique.ttf",
    (True, True): "DejaVuSans-BoldOblique.ttf",
}


class TextAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class FontFace:
    path: Path
    family: str
    style: str

    @property
    def bold(self) -> bool:
        style = self.style.casefold()
        return any(word in style for word in ("bold", "black", "demi", "heavy", "semibold"))

    @property
    def italic(self) -> bool:
        style = self.style.casefold()
        return "italic" in style or "oblique" in style

    def summary(self) -> dict[str, object]:
        return {
            "family": self.family,
            "style": self.style,
            "path": str(self.path),
            "bold": self.bold,
            "italic": self.italic,
        }


@dataclass(frozen=True, slots=True)
class FontSpec:
    size: int = 28
    family: str | None = None
    path: str | Path | None = None
    bold: bool = False
    italic: bool = False

    def __post_init__(self) -> None:
        if not 4 <= self.size <= 256:
            raise ValueError("font size must be between 4 and 256 dots")
        if self.family is not None and not self.family.strip():
            raise ValueError("font family cannot be empty")
        if self.family is not None and self.path is not None:
            raise ValueError("choose either a font family or a font file, not both")


@dataclass(frozen=True, slots=True)
class TextLayoutConfig:
    width: int = MAX_PRINT_WIDTH
    margin: int = 12
    line_spacing: int = 4
    align: TextAlign = TextAlign.LEFT
    max_height: int = 4096

    def __post_init__(self) -> None:
        if not 1 <= self.width <= MAX_PRINT_WIDTH:
            raise ValueError(f"width must be between 1 and {MAX_PRINT_WIDTH} dots")
        if self.margin < 0 or self.margin * 2 >= self.width:
            raise ValueError("margin leaves no printable text width")
        if not 0 <= self.line_spacing <= 256:
            raise ValueError("line spacing must be between 0 and 256 dots")
        if self.max_height <= 0:
            raise ValueError("maximum height must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedFont:
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    family: str
    style: str
    source: str

    def summary(self) -> dict[str, object]:
        return {"family": self.family, "style": self.style, "source": self.source}


@dataclass(frozen=True, slots=True)
class RenderedText:
    image: Image.Image
    lines: tuple[str, ...]
    font: ResolvedFont
    config: TextLayoutConfig

    def summary(self) -> dict[str, object]:
        return {
            "font": self.font.summary(),
            "font_size": getattr(self.font.font, "size", None),
            "align": self.config.align.value,
            "margin": self.config.margin,
            "line_spacing": self.config.line_spacing,
            "line_count": len(self.lines),
            "rendered_width": self.image.width,
            "rendered_height": self.image.height,
        }


@dataclass(frozen=True, slots=True)
class PreparedText:
    rendered: RenderedText
    prepared: PreparedImage

    def summary(self) -> dict[str, object]:
        return self.prepared.summary() | self.rendered.summary()


def system_font_directories() -> tuple[Path, ...]:
    """Return platform font roots without requiring fontconfig or a GUI API."""

    candidates: list[Path] = []
    windows_dir = os.getenv("WINDIR")
    if windows_dir:
        candidates.append(Path(windows_dir) / "Fonts")
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Microsoft" / "Windows" / "Fonts")

    candidates.extend(
        [
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
            Path.home() / "Library" / "Fonts",
        ]
    )
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).casefold()
        if key not in seen and path.is_dir():
            seen.add(key)
            unique.append(path)
    return tuple(unique)


def _inspect_font(path: Path) -> FontFace | None:
    try:
        loaded = ImageFont.truetype(str(path), size=12)
        family, style = loaded.getname()
    except OSError:
        return None
    return FontFace(path=path, family=family, style=style)


class FontCatalog:
    """Discover font faces and resolve a family/style request to a concrete file."""

    def __init__(self, roots: tuple[Path, ...] | None = None) -> None:
        self.roots = roots if roots is not None else system_font_directories()
        self._faces: tuple[FontFace, ...] | None = None

    def faces(self) -> tuple[FontFace, ...]:
        if self._faces is None:
            paths = sorted(
                {
                    path
                    for root in self.roots
                    for path in root.rglob("*")
                    if path.is_file() and path.suffix.casefold() in FONT_SUFFIXES
                },
                key=lambda path: str(path).casefold(),
            )
            faces = (face for path in paths if (face := _inspect_font(path)) is not None)
            self._faces = tuple(
                sorted(faces, key=lambda face: (face.family.casefold(), face.style.casefold()))
            )
        return self._faces

    def resolve(self, family: str, *, bold: bool = False, italic: bool = False) -> FontFace:
        requested = family.strip().casefold()
        exact = [face for face in self.faces() if face.family.casefold() == requested]
        matches = exact or [face for face in self.faces() if requested in face.family.casefold()]
        if not matches:
            raise ValueError(f"font family {family!r} was not found")

        preferred_styles = {
            (False, False): ("regular", "book", "normal", "roman"),
            (True, False): ("bold", "semibold", "demibold", "black", "heavy"),
            (False, True): ("italic", "oblique"),
            (True, True): ("bold italic", "bold oblique", "semibold italic"),
        }[(bold, italic)]

        def score(face: FontFace) -> tuple[int, int, str, str]:
            style_penalty = int(face.bold != bold) + int(face.italic != italic)
            style = face.style.casefold()
            try:
                preference = preferred_styles.index(style)
            except ValueError:
                preference = len(preferred_styles)
            return style_penalty, preference, face.family.casefold(), style

        return min(matches, key=score)

    def describe(self, family: str | None = None) -> list[dict[str, object]]:
        faces = self.faces()
        if family:
            wanted = family.casefold()
            faces = tuple(face for face in faces if wanted in face.family.casefold())
        return [face.summary() for face in faces]


def _loaded_font_summary(
    loaded: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    source: str,
) -> ResolvedFont:
    getname = getattr(loaded, "getname", None)
    family, style = getname() if getname is not None else ("Pillow default", "Regular")
    return ResolvedFont(font=loaded, family=family, style=style, source=source)


def resolve_font(spec: FontSpec, catalog: FontCatalog | None = None) -> ResolvedFont:
    if spec.path is not None:
        path = Path(spec.path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"font file does not exist: {path}")
        if path.suffix.casefold() not in FONT_SUFFIXES:
            raise ValueError("font file must be TTF, OTF, or TTC")
        try:
            return _loaded_font_summary(ImageFont.truetype(str(path), spec.size), str(path))
        except OSError as error:
            raise ValueError(f"cannot load font file {path}: {error}") from error

    if spec.family is not None:
        face = (catalog or FontCatalog()).resolve(
            spec.family,
            bold=spec.bold,
            italic=spec.italic,
        )
        return _loaded_font_summary(ImageFont.truetype(str(face.path), spec.size), str(face.path))

    default_name = DEFAULT_FONT_NAMES[(spec.bold, spec.italic)]
    try:
        loaded = ImageFont.truetype(default_name, spec.size)
        source = str(getattr(loaded, "path", default_name))
    except OSError:
        try:
            loaded = ImageFont.load_default(size=spec.size)
        except TypeError:  # Pillow 10.0 compatibility
            loaded = ImageFont.load_default()
        source = "Pillow embedded default"
    return _loaded_font_summary(loaded, source)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def _split_long_token(
    draw: ImageDraw.ImageDraw,
    token: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    pieces: list[str] = []
    current = ""
    for character in token:
        if _text_width(draw, character, font) > max_width:
            raise ValueError("font size and margins leave a glyph wider than the text area")
        candidate = current + character
        if current and _text_width(draw, candidate, font) > max_width:
            pieces.append(current)
            current = character
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _wrap_paragraph(
    draw: ImageDraw.ImageDraw,
    paragraph: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    if not paragraph:
        return [""]
    tokens: list[str] = []
    for word in paragraph.split():
        if _text_width(draw, word, font) <= max_width:
            tokens.append(word)
        else:
            tokens.extend(_split_long_token(draw, word, font, max_width))

    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = token if not current else f"{current} {token}"
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = token
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_text(
    text: str,
    font_spec: FontSpec | None = None,
    layout: TextLayoutConfig | None = None,
    *,
    catalog: FontCatalog | None = None,
) -> RenderedText:
    if not text or not text.strip():
        raise ValueError("text cannot be empty")
    if len(text) > 100_000:
        raise ValueError("text is too long")

    font_spec = font_spec or FontSpec()
    layout = layout or TextLayoutConfig()
    resolved = resolve_font(font_spec, catalog)
    measuring = ImageDraw.Draw(Image.new("L", (layout.width, 1), "white"))
    available_width = layout.width - 2 * layout.margin
    lines = tuple(
        line
        for paragraph in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for line in _wrap_paragraph(measuring, paragraph, resolved.font, available_width)
    )

    getmetrics = getattr(resolved.font, "getmetrics", None)
    if getmetrics is not None:
        ascent, descent = getmetrics()
        line_height = ascent + descent
    else:
        bounds = resolved.font.getbbox("Ag")
        line_height = bounds[3] - bounds[1]
    height = 2 * layout.margin + len(lines) * line_height
    height += max(0, len(lines) - 1) * layout.line_spacing
    if height > layout.max_height:
        raise ValueError(f"rendered text height {height} exceeds maximum {layout.max_height}")

    image = Image.new("L", (layout.width, max(1, height)), "white")
    draw = ImageDraw.Draw(image)
    y = layout.margin
    for line in lines:
        width = _text_width(draw, line, resolved.font)
        if layout.align is TextAlign.LEFT:
            x = layout.margin
        elif layout.align is TextAlign.CENTER:
            x = (layout.width - width) / 2
        else:
            x = layout.width - layout.margin - width
        draw.text((round(x), y), line, fill="black", font=resolved.font)
        y += line_height + layout.line_spacing
    return RenderedText(image=image, lines=lines, font=resolved, config=layout)


def prepare_text(
    text: str,
    font_spec: FontSpec | None = None,
    layout: TextLayoutConfig | None = None,
    *,
    threshold: int = 180,
    catalog: FontCatalog | None = None,
) -> PreparedText:
    rendered = render_text(text, font_spec, layout, catalog=catalog)
    prepared = prepare_image(
        rendered.image,
        ImagePreparationConfig(
            width=rendered.image.width,
            threshold=threshold,
            dither=DitherMode.THRESHOLD,
            preserve_aspect_ratio=False,
        ),
    )
    return PreparedText(rendered=rendered, prepared=prepared)
