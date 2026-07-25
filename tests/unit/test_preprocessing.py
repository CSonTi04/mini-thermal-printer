from collections.abc import Mapping

import pytest
from PIL import Image

from tronic_printer import preprocessing
from tronic_printer.preprocessing import (
    DitherMode,
    EffectSpec,
    ImageEffectRegistry,
    ImagePreparationConfig,
    build_effect_registry,
    prepare_image,
)


class DarkenEffect:
    name = "darken-test"
    description = "test-only darkening effect"

    def apply(self, image: Image.Image, options: Mapping[str, str]) -> Image.Image:
        amount = int(options.get("amount", "20"))
        return image.point(lambda value: max(0, value - amount))


def test_effect_spec_parses_ordered_options() -> None:
    spec = EffectSpec.parse("contrast:factor=1.5,mode=strong")

    assert spec.name == "contrast"
    assert spec.options == (("factor", "1.5"), ("mode", "strong"))


@pytest.mark.parametrize(
    "value, message",
    [
        ("", "name"),
        ("contrast:factor", "key=value"),
        ("contrast:factor=1,factor=2", "duplicate"),
    ],
)
def test_effect_spec_rejects_invalid_syntax(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        EffectSpec.parse(value)


def test_registry_supports_custom_effects_and_ordered_chains() -> None:
    registry = ImageEffectRegistry([DarkenEffect()])
    image = Image.new("L", (1, 1), color=140)

    prepared = prepare_image(
        image,
        ImagePreparationConfig(
            width=1,
            threshold=128,
            effects=(EffectSpec.parse("darken-test:amount=20"),),
        ),
        registry=registry,
    )

    assert prepared.raster.data == b"\x80"
    assert prepared.summary()["effects"] == ["darken-test"]


def test_registry_rejects_unknown_effect_and_dimension_changes() -> None:
    registry = ImageEffectRegistry()
    with pytest.raises(ValueError, match="unknown image effect"):
        registry.apply(Image.new("L", (1, 1)), [EffectSpec("missing")])

    class ResizeEffect:
        name = "resize"
        description = "invalid test effect"

        def apply(self, image: Image.Image, _options: Mapping[str, str]) -> Image.Image:
            return image.resize((2, 2))

    registry.register(ResizeEffect())
    with pytest.raises(ValueError, match="changed dimensions"):
        registry.apply(Image.new("L", (1, 1)), [EffectSpec("resize")])


def test_entry_point_effect_is_discovered(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeEntryPoint:
        def load(self) -> type[DarkenEffect]:
            return DarkenEffect

    monkeypatch.setattr(preprocessing, "entry_points", lambda **_kwargs: [FakeEntryPoint()])

    registry = build_effect_registry()

    assert "darken-test" in registry.names()


def test_library_preparation_does_not_implicitly_import_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        preprocessing,
        "entry_points",
        lambda **_kwargs: pytest.fail("implicit plugin discovery"),
    )

    prepared = prepare_image(Image.new("L", (1, 1), color=255))

    assert prepared.black_pixels == 0


def test_transparent_pixels_are_composited_onto_white() -> None:
    image = Image.new("RGBA", (2, 1), color=(0, 0, 0, 0))
    image.putpixel((1, 0), (0, 0, 0, 255))

    prepared = prepare_image(image, ImagePreparationConfig(width=2))

    assert prepared.raster.data == b"\x40"
    assert list(prepared.preview.tobytes()) == [255, 0]


@pytest.mark.parametrize("mode", list(DitherMode))
def test_every_dither_mode_produces_exact_one_bit_preview(mode: DitherMode) -> None:
    image = Image.linear_gradient("L").resize((16, 16))

    prepared = prepare_image(
        image,
        ImagePreparationConfig(width=16, dither=mode),
    )

    assert prepared.raster.width == 16
    assert prepared.raster.height == 16
    assert set(prepared.preview.tobytes()) <= {0, 255}
    assert 0 < prepared.black_pixels < 256


def test_builtin_effect_options_are_validated() -> None:
    registry = build_effect_registry(discover_plugins=False)
    image = Image.new("L", (2, 1), color=128)

    with pytest.raises(ValueError, match="unknown effect option"):
        registry.apply(image, [EffectSpec.parse("contrast:unknown=1")])
    with pytest.raises(ValueError, match="less than 50"):
        registry.apply(image, [EffectSpec.parse("autocontrast:cutoff=50")])


@pytest.mark.parametrize(
    "spec",
    [
        "autocontrast:cutoff=1",
        "brightness:factor=1.1",
        "contrast:factor=1.2",
        "edge",
        "gamma:value=0.9",
        "invert",
        "blur:radius=0.5",
        "sharpen:factor=2",
    ],
)
def test_every_builtin_effect_preserves_grayscale_dimensions(spec: str) -> None:
    image = Image.linear_gradient("L").resize((8, 8))

    result = build_effect_registry(discover_plugins=False).apply(
        image,
        [EffectSpec.parse(spec)],
    )

    assert result.mode == "L"
    assert result.size == image.size


def test_preparation_config_enforces_print_head_width() -> None:
    with pytest.raises(ValueError, match="384"):
        ImagePreparationConfig(width=385)
