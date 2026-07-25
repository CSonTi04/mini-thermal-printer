"""Extensible, transport-independent image preparation for thermal output."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import entry_points
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from tronic_printer.domain import RasterImage
from tronic_printer.protocol import MAX_PRINT_WIDTH

ENTRY_POINT_GROUP = "tronic_printer.image_effects"
IMAGE_EFFECT_API_VERSION = 1


class DitherMode(StrEnum):
    THRESHOLD = "threshold"
    FLOYD_STEINBERG = "floyd-steinberg"
    ORDERED_4X4 = "ordered-4x4"


@dataclass(frozen=True, slots=True)
class EffectSpec:
    """A named image effect plus string options suitable for CLI and web APIs."""

    name: str
    options: tuple[tuple[str, str], ...] = ()

    @classmethod
    def parse(cls, value: str) -> EffectSpec:
        name, separator, raw_options = value.partition(":")
        name = name.strip().lower()
        if not name:
            raise ValueError("effect name cannot be empty")
        if not separator:
            return cls(name)

        options: list[tuple[str, str]] = []
        seen: set[str] = set()
        for assignment in raw_options.split(","):
            key, equals, option_value = assignment.partition("=")
            key = key.strip().lower()
            option_value = option_value.strip()
            if not equals or not key or not option_value:
                raise ValueError(f"invalid option in effect {value!r}; expected key=value")
            if key in seen:
                raise ValueError(f"duplicate option {key!r} in effect {name!r}")
            seen.add(key)
            options.append((key, option_value))
        return cls(name=name, options=tuple(options))

    def as_mapping(self) -> dict[str, str]:
        return dict(self.options)


@runtime_checkable
class ImageEffect(Protocol):
    """Plugin contract. Effects receive and return a same-sized Pillow image."""

    name: str
    description: str

    def apply(self, image: Image.Image, options: Mapping[str, str]) -> Image.Image: ...


@dataclass(frozen=True, slots=True)
class FunctionEffect:
    name: str
    description: str
    function: Callable[[Image.Image, Mapping[str, str]], Image.Image]

    def apply(self, image: Image.Image, options: Mapping[str, str]) -> Image.Image:
        return self.function(image, options)


class ImageEffectRegistry:
    def __init__(self, effects: Iterable[ImageEffect] = ()) -> None:
        self._effects: dict[str, ImageEffect] = {}
        for effect in effects:
            self.register(effect)

    def register(self, effect: ImageEffect, *, replace: bool = False) -> None:
        if not isinstance(effect, ImageEffect):
            raise TypeError("image effect must implement name, description, and apply")
        name = effect.name.strip().lower()
        if not name:
            raise ValueError("image effect name cannot be empty")
        if name in self._effects and not replace:
            raise ValueError(f"image effect {name!r} is already registered")
        self._effects[name] = effect

    def get(self, name: str) -> ImageEffect:
        try:
            return self._effects[name.lower()]
        except KeyError as error:
            available = ", ".join(self.names())
            raise ValueError(f"unknown image effect {name!r}; available: {available}") from error

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._effects))

    def describe(self) -> list[dict[str, str]]:
        return [
            {"name": name, "description": self._effects[name].description}
            for name in self.names()
        ]

    def apply(self, image: Image.Image, specs: Iterable[EffectSpec]) -> Image.Image:
        result = image.copy()
        expected_size = result.size
        for spec in specs:
            effect = self.get(spec.name)
            transformed = effect.apply(result, spec.as_mapping())
            if not isinstance(transformed, Image.Image):
                raise TypeError(f"image effect {effect.name!r} did not return a Pillow image")
            if transformed.size != expected_size:
                raise ValueError(
                    f"image effect {effect.name!r} changed dimensions from "
                    f"{expected_size} to {transformed.size}"
                )
            result = ImageOps.grayscale(transformed)
        return result


@dataclass(frozen=True, slots=True)
class ImagePreparationConfig:
    width: int = MAX_PRINT_WIDTH
    threshold: int = 128
    dither: DitherMode = DitherMode.THRESHOLD
    effects: tuple[EffectSpec, ...] = ()
    preserve_aspect_ratio: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.width <= MAX_PRINT_WIDTH:
            raise ValueError(f"width must be between 1 and {MAX_PRINT_WIDTH} dots")
        if self.threshold not in range(256):
            raise ValueError("threshold must be between 0 and 255")


@dataclass(frozen=True, slots=True)
class PreparedImage:
    raster: RasterImage
    preview: Image.Image
    source_width: int
    source_height: int
    black_pixels: int
    effects: tuple[EffectSpec, ...]
    dither: DitherMode
    threshold: int

    @property
    def black_percent(self) -> float:
        return self.black_pixels * 100 / (self.raster.width * self.raster.height)

    @property
    def estimated_height_mm(self) -> float:
        return self.raster.height / 8

    def save_preview(self, path: str | Path) -> None:
        self.preview.save(path)

    def summary(self) -> dict[str, object]:
        return {
            "source_width": self.source_width,
            "source_height": self.source_height,
            "width": self.raster.width,
            "height": self.raster.height,
            "estimated_height_mm": round(self.estimated_height_mm, 3),
            "raster_bytes": len(self.raster.data),
            "black_pixels": self.black_pixels,
            "black_percent": round(self.black_percent, 3),
            "dither": self.dither.value,
            "threshold": self.threshold,
            "effects": [spec.name for spec in self.effects],
        }


def _reject_unknown(options: Mapping[str, str], allowed: set[str]) -> None:
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ValueError(f"unknown effect option(s): {', '.join(unknown)}")


def _float_option(
    options: Mapping[str, str],
    name: str,
    default: float,
    *,
    minimum: float = 0,
) -> float:
    try:
        value = float(options.get(name, default))
    except ValueError as error:
        raise ValueError(f"effect option {name!r} must be a number") from error
    if value < minimum:
        raise ValueError(f"effect option {name!r} must be at least {minimum}")
    return value


def _contrast(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"factor"})
    return ImageEnhance.Contrast(image).enhance(_float_option(options, "factor", 1.4))


def _brightness(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"factor"})
    return ImageEnhance.Brightness(image).enhance(_float_option(options, "factor", 1.0))


def _sharpen(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"factor"})
    return ImageEnhance.Sharpness(image).enhance(_float_option(options, "factor", 1.8))


def _blur(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"radius"})
    return image.filter(ImageFilter.GaussianBlur(_float_option(options, "radius", 1.0)))


def _gamma(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"value"})
    value = _float_option(options, "value", 1.0, minimum=0.01)
    lookup = [round(255 * ((level / 255) ** value)) for level in range(256)]
    return image.point(lookup)


def _autocontrast(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, {"cutoff"})
    cutoff = _float_option(options, "cutoff", 1.0)
    if cutoff >= 50:
        raise ValueError("effect option 'cutoff' must be less than 50")
    return ImageOps.autocontrast(image, cutoff=cutoff)


def _invert(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, set())
    return ImageOps.invert(image)


def _edge(image: Image.Image, options: Mapping[str, str]) -> Image.Image:
    _reject_unknown(options, set())
    return ImageOps.invert(image.filter(ImageFilter.FIND_EDGES))


BUILTIN_EFFECTS: tuple[ImageEffect, ...] = (
    FunctionEffect("autocontrast", "stretch tones; option: cutoff=1", _autocontrast),
    FunctionEffect("brightness", "adjust brightness; option: factor=1.0", _brightness),
    FunctionEffect("contrast", "adjust contrast; option: factor=1.4", _contrast),
    FunctionEffect("edge", "extract dark outlines", _edge),
    FunctionEffect("gamma", "tone curve; option: value=1.0", _gamma),
    FunctionEffect("invert", "swap light and dark", _invert),
    FunctionEffect("blur", "Gaussian blur; option: radius=1.0", _blur),
    FunctionEffect("sharpen", "adjust sharpness; option: factor=1.8", _sharpen),
)


def build_effect_registry(*, discover_plugins: bool = True) -> ImageEffectRegistry:
    registry = ImageEffectRegistry(BUILTIN_EFFECTS)
    if discover_plugins:
        for entry_point in entry_points(group=ENTRY_POINT_GROUP):
            loaded = entry_point.load()
            effect = loaded() if isinstance(loaded, type) else loaded
            registry.register(effect)
    return registry


def _normalize_source(image: Image.Image) -> Image.Image:
    oriented = ImageOps.exif_transpose(image)
    if "A" in oriented.getbands() or "transparency" in oriented.info:
        rgba = oriented.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        oriented = Image.alpha_composite(white, rgba).convert("RGB")
    return ImageOps.grayscale(oriented)


def _resize_to_width(
    image: Image.Image,
    width: int,
    *,
    preserve_aspect_ratio: bool,
) -> Image.Image:
    height = (
        max(1, round(image.height * width / image.width))
        if preserve_aspect_ratio
        else image.height
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _shift_for_threshold(image: Image.Image, threshold: int) -> Image.Image:
    offset = 128 - threshold
    if offset == 0:
        return image
    return image.point(lambda value: max(0, min(255, value + offset)))


def _flattened_pixels(image: Image.Image) -> list[int]:
    modern_getter = getattr(image, "get_flattened_data", None)
    if modern_getter is not None:
        return list(modern_getter())
    return list(image.getdata())


def _black_rows(image: Image.Image, mode: DitherMode, threshold: int) -> list[list[bool]]:
    width, height = image.size
    pixels = _flattened_pixels(image)
    if mode is DitherMode.THRESHOLD:
        return [
            [pixels[y * width + x] < threshold for x in range(width)]
            for y in range(height)
        ]
    if mode is DitherMode.FLOYD_STEINBERG:
        monochrome = _shift_for_threshold(image, threshold).convert(
            "1", dither=Image.Dither.FLOYDSTEINBERG
        )
        values = _flattened_pixels(monochrome)
        return [
            [values[y * width + x] == 0 for x in range(width)]
            for y in range(height)
        ]
    if mode is DitherMode.ORDERED_4X4:
        matrix = (
            (0, 8, 2, 10),
            (12, 4, 14, 6),
            (3, 11, 1, 9),
            (15, 7, 13, 5),
        )
        return [
            [
                pixels[y * width + x]
                < max(0, min(255, round(threshold + (matrix[y % 4][x % 4] - 7.5) * 16)))
                for x in range(width)
            ]
            for y in range(height)
        ]
    raise ValueError(f"unsupported dither mode: {mode}")


def prepare_image(
    image: Image.Image,
    config: ImagePreparationConfig | None = None,
    *,
    registry: ImageEffectRegistry | None = None,
) -> PreparedImage:
    config = config or ImagePreparationConfig()
    source_width, source_height = image.size
    grayscale = _resize_to_width(
        _normalize_source(image),
        config.width,
        preserve_aspect_ratio=config.preserve_aspect_ratio,
    )
    # Library calls are deterministic and do not import third-party code unless
    # the caller explicitly supplies a discovery-enabled registry. The CLI does.
    active_registry = registry or build_effect_registry(discover_plugins=False)
    processed = active_registry.apply(grayscale, config.effects)
    rows = _black_rows(processed, config.dither, config.threshold)
    raster = RasterImage.from_rows(rows)
    black_pixels = sum(sum(row) for row in rows)
    preview = Image.new("L", (raster.width, raster.height), color=255)
    preview.putdata([0 if is_black else 255 for row in rows for is_black in row])
    return PreparedImage(
        raster=raster,
        preview=preview,
        source_width=source_width,
        source_height=source_height,
        black_pixels=black_pixels,
        effects=config.effects,
        dither=config.dither,
        threshold=config.threshold,
    )


def load_prepared_image(
    path: str | Path,
    config: ImagePreparationConfig | None = None,
    *,
    registry: ImageEffectRegistry | None = None,
) -> PreparedImage:
    with Image.open(path) as image:
        return prepare_image(image, config, registry=registry)
