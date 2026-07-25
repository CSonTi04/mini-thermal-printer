import pytest

from tronic_printer import protocol
from tronic_printer.domain import ProtocolError, RasterImage


def test_verified_query_bytes() -> None:
    assert protocol.QUERY_MODEL.hex(" ") == "10 ff 20 f0"
    assert protocol.QUERY_FIRMWARE.hex(" ") == "10 ff 20 f1"
    assert protocol.QUERY_BATTERY.hex(" ") == "10 ff 50 f1"
    assert protocol.QUERY_STATUS.hex(" ") == "10 ff 40"


def test_uncompressed_raster_header_is_little_endian() -> None:
    raster = RasterImage(width=384, height=37, data=bytes(48 * 37))

    frame = protocol.encode_uncompressed_raster(raster)

    assert frame[:8] == bytes.fromhex("1D 76 30 00 30 00 25 00")
    assert len(frame) == 8 + 48 * 37


def test_uncompressed_raster_rejects_more_than_384_dots() -> None:
    raster = RasterImage(width=385, height=1, data=bytes(49))

    with pytest.raises(ValueError, match="384-dot"):
        protocol.encode_uncompressed_raster(raster)


@pytest.mark.parametrize(
    ("response", "expected"),
    [(bytes.fromhex("00 5A"), 90), (bytes.fromhex("00 5C"), 92)],
)
def test_decode_captured_battery_responses(response: bytes, expected: int) -> None:
    assert protocol.decode_battery(response) == expected


def test_decode_battery_rejects_short_response() -> None:
    with pytest.raises(ProtocolError, match="too short"):
        protocol.decode_battery(b"\x5A")


@pytest.mark.parametrize("response", [b"\xAA\r\n", b"OK", b"OK\x00"])
def test_success_responses(response: bytes) -> None:
    assert protocol.is_success(response)


def test_density_range_is_validated() -> None:
    assert protocol.set_density(2) == bytes.fromhex("10 FF 10 00 02")
    with pytest.raises(ValueError, match="density"):
        protocol.set_density(3)


def test_job_mode_is_encoded() -> None:
    assert protocol.start_job(3) == protocol.START_JOB
    assert protocol.start_job(7) == bytes.fromhex("10 FF F1 07")

    with pytest.raises(ValueError, match="job mode"):
        protocol.start_job(256)


def test_captured_ascii_responses_decode_without_terminators() -> None:
    assert protocol.decode_ascii(b"A2Y", "model") == "A2Y"
    assert protocol.decode_ascii(b"V1.06LY\r\n", "firmware") == "V1.06LY"


def test_non_ascii_response_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="non-ASCII"):
        protocol.decode_ascii(b"\xFF", "model")
