import pytest

from tronic_printer import protocol
from tronic_printer.domain import ProtocolError, RasterImage


def test_verified_query_bytes() -> None:
    assert protocol.QUERY_MODEL.hex(" ") == "10 ff 20 f0"
    assert protocol.QUERY_FIRMWARE.hex(" ") == "10 ff 20 f1"
    assert protocol.QUERY_SERIAL.hex(" ") == "10 ff 20 f2"
    assert protocol.QUERY_BOOT_INFO.hex(" ") == "10 ff 20 ef"
    assert protocol.QUERY_BATTERY.hex(" ") == "10 ff 50 f1"
    assert protocol.QUERY_STATUS.hex(" ") == "10 ff 40"
    assert protocol.QUERY_SHUTDOWN_TIME.hex(" ") == "10 ff 13"
    assert protocol.QUERY_SPEED.hex(" ") == "10 ff 20 a0"
    assert protocol.QUERY_TIME_FORMAT.hex(" ") == "10 ff b0"


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


def test_shutdown_time_uses_recovered_big_endian_minutes() -> None:
    assert protocol.set_shutdown_time(30) == bytes.fromhex("10 FF 12 00 1E")
    with pytest.raises(ValueError, match="5, 10, 20, 30, or 60"):
        protocol.set_shutdown_time(15)


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


@pytest.mark.parametrize(("response", "expected"), [(b"\x1e", 30), (b"\x00\x3c", 60)])
def test_shutdown_time_matches_recovered_sdk_decoder(response: bytes, expected: int) -> None:
    assert protocol.decode_shutdown_time(response) == expected


def test_optional_single_byte_values_are_validated() -> None:
    assert protocol.decode_speed(b"\x02") == 2
    assert protocol.decode_time_format(b"\x01") == 1

    with pytest.raises(ProtocolError, match="empty speed"):
        protocol.decode_speed(b"")
    with pytest.raises(ProtocolError, match="exactly one byte"):
        protocol.decode_time_format(b"\x00\x01")
