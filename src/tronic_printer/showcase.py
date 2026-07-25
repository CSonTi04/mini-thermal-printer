"""Reusable labeled pages for image-processing demonstrations and HIL tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tronic_printer.domain import RasterImage
from tronic_printer.preprocessing import (
    DitherMode,
    EffectSpec,
    ImageEffectRegistry,
    ImagePreparationConfig,
    PreparedImage,
    build_effect_registry,
    prepare_image,
)


@dataclass(frozen=True, slots=True)
class ImageRecipe:
    slug: str
    name: str
    dither: DitherMode
    threshold: int = 128
    effects: tuple[EffectSpec, ...] = ()

    def config(self, *, width: int = 384) -> ImagePreparationConfig:
        return ImagePreparationConfig(
            width=width,
            threshold=self.threshold,
            dither=self.dither,
            effects=self.effects,
        )

    def effect_text(self) -> str:
        if not self.effects:
            return "none"
        return " > ".join(
            spec.name
            + (
                "(" + ",".join(f"{key}={value}" for key, value in spec.options) + ")"
                if spec.options
                else ""
            )
            for spec in self.effects
        )


SHOWCASE_RECIPES: tuple[ImageRecipe, ...] = (
    ImageRecipe(
        slug="floyd-photo",
        name="Floyd photo",
        dither=DitherMode.FLOYD_STEINBERG,
        effects=(EffectSpec.parse("autocontrast:cutoff=2"),),
    ),
    ImageRecipe(
        slug="ordered-newsprint",
        name="Ordered newsprint",
        dither=DitherMode.ORDERED_4X4,
        effects=(
            EffectSpec.parse("autocontrast:cutoff=2"),
            EffectSpec.parse("contrast:factor=1.2"),
        ),
    ),
    ImageRecipe(
        slug="gritty-noir",
        name="Gritty noir",
        dither=DitherMode.THRESHOLD,
        threshold=145,
        effects=(
            EffectSpec.parse("autocontrast:cutoff=2"),
            EffectSpec.parse("contrast:factor=1.8"),
            EffectSpec.parse("gamma:value=1.15"),
        ),
    ),
    ImageRecipe(
        slug="outline-sketch",
        name="Outline sketch",
        dither=DitherMode.THRESHOLD,
        threshold=180,
        effects=(EffectSpec.parse("edge"),),
    ),
)


@dataclass(frozen=True, slots=True)
class ShowcasePage:
    recipe: ImageRecipe
    image: PreparedImage
    preview: Image.Image
    raster: RasterImage
    header_height: int

    @property
    def estimated_height_mm(self) -> float:
        return self.raster.height / 8

    def summary(self) -> dict[str, object]:
        return {
            "slug": self.recipe.slug,
            "name": self.recipe.name,
            "dither": self.recipe.dither.value,
            "threshold": self.recipe.threshold,
            "effects": self.recipe.effect_text(),
            "image_black_percent": round(self.image.black_percent, 3),
            "image_height": self.image.raster.height,
            "header_height": self.header_height,
            "page_height": self.raster.height,
            "estimated_page_height_mm": round(self.estimated_height_mm, 3),
        }


def _wrap_line(draw: ImageDraw.ImageDraw, text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_header(lines: Iterable[str], width: int) -> Image.Image:
    scale = 2
    logical_width = width // scale
    font = ImageFont.load_default()
    measuring = ImageDraw.Draw(Image.new("L", (logical_width, 1), "white"))
    wrapped = [
        wrapped_line
        for line in lines
        for wrapped_line in _wrap_line(measuring, line, logical_width - 8)
    ]
    line_height = 11
    logical_height = 7 + len(wrapped) * line_height
    header = Image.new("L", (logical_width, logical_height), "white")
    draw = ImageDraw.Draw(header)
    for index, line in enumerate(wrapped):
        draw.text((4, 3 + index * line_height), line, fill="black", font=font)
    return header.resize((width, logical_height * scale), Image.Resampling.NEAREST)


def _pack_preview(preview: Image.Image) -> RasterImage:
    grayscale = preview.convert("L")
    width, height = grayscale.size
    pixels = grayscale.tobytes()
    return RasterImage.from_rows(
        [
            [pixels[y * width + x] < 128 for x in range(width)]
            for y in range(height)
        ]
    )


def _binarize_preview(preview: Image.Image) -> Image.Image:
    return preview.convert("L").point(lambda value: 0 if value < 128 else 255)


def build_showcase_page(
    source: Image.Image,
    recipe: ImageRecipe,
    *,
    width: int = 384,
    registry: ImageEffectRegistry | None = None,
) -> ShowcasePage:
    active_registry = registry or build_effect_registry(discover_plugins=False)
    prepared = prepare_image(source, recipe.config(width=width), registry=active_registry)
    header = _render_header(
        (
            recipe.name,
            f"dither={recipe.dither.value} threshold={recipe.threshold}",
            f"effects={recipe.effect_text()}",
            (
                f"image={prepared.raster.width}x{prepared.raster.height} "
                f"black={prepared.black_percent:.2f}%"
            ),
        ),
        width,
    )
    gap = 8
    preview = Image.new(
        "L",
        (width, header.height + gap + prepared.preview.height),
        "white",
    )
    preview.paste(header, (0, 0))
    preview.paste(prepared.preview, (0, header.height + gap))
    exact_preview = _binarize_preview(preview)
    return ShowcasePage(
        recipe=recipe,
        image=prepared,
        preview=exact_preview,
        raster=_pack_preview(exact_preview),
        header_height=header.height + gap,
    )


def build_showcase_pages(
    source: Image.Image,
    recipes: Iterable[ImageRecipe] = SHOWCASE_RECIPES,
    *,
    width: int = 384,
    registry: ImageEffectRegistry | None = None,
) -> tuple[ShowcasePage, ...]:
    active_registry = registry or build_effect_registry(discover_plugins=False)
    return tuple(
        build_showcase_page(source, recipe, width=width, registry=active_registry)
        for recipe in recipes
    )


def load_showcase_pages(
    path: str | Path,
    recipes: Iterable[ImageRecipe] = SHOWCASE_RECIPES,
    *,
    width: int = 384,
    registry: ImageEffectRegistry | None = None,
) -> tuple[ShowcasePage, ...]:
    with Image.open(path) as source:
        return build_showcase_pages(source, recipes, width=width, registry=registry)
