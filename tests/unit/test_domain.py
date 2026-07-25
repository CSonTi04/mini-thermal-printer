import pytest

from tronic_printer.domain import PrinterStatus, RasterImage


def test_status_decodes_all_known_bits() -> None:
    status = PrinterStatus.from_byte(0b0111_1111)

    assert status.printing
    assert status.cover_open
    assert status.paper_absent
    assert status.low_battery
    assert status.overheated
    assert status.charging
    assert not status.can_print


@pytest.mark.parametrize("overheat_bit", [0x10, 0x40])
def test_either_overheat_bit_blocks_printing(overheat_bit: int) -> None:
    assert PrinterStatus.from_byte(overheat_bit).overheated
    assert not PrinterStatus.from_byte(overheat_bit).can_print


def test_raster_packs_msb_first_and_leaves_padding_white() -> None:
    raster = RasterImage.from_rows(
        [
            [True, False, True, False, False, False, False, True, True],
            [False] * 9,
        ]
    )

    assert raster.width == 9
    assert raster.height == 2
    assert raster.row_bytes == 2
    assert raster.data == bytes((0xA1, 0x80, 0x00, 0x00))


def test_raster_rejects_ragged_rows() -> None:
    with pytest.raises(ValueError, match="equal width"):
        RasterImage.from_rows([[True], [True, False]])


def test_test_pattern_is_deterministic() -> None:
    first = RasterImage.test_pattern(384, 32)
    second = RasterImage.test_pattern(384, 32)

    assert first == second
    assert len(first.data) == 48 * 32


def test_test_pattern_supports_thicker_calibration_lines() -> None:
    raster = RasterImage.test_pattern(384, 96, line_width=3)

    assert raster.data[: 48 * 3] == bytes([0xFF]) * (48 * 3)
    with pytest.raises(ValueError, match="line width"):
        RasterImage.test_pattern(8, 8, line_width=5)
