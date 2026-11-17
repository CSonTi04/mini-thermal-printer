import pytest

from tronic_printer.domain import ProtocolError, RasterImage
from tronic_printer.niimbot import NIIMBOT_ROW_BYTES
from tronic_printer.niimbot_client import (
    NiimbotClient,
    NiimbotError,
    RequestCode,
    encode_raster_rows,
)
from tronic_printer.testing import EmulatedNiimbotTransport

ROW = NIIMBOT_ROW_BYTES


def make_raster(rows: list[bytes]) -> RasterImage:
    return RasterImage(width=384, height=len(rows), data=b"".join(rows))


def client_for(**options) -> tuple[NiimbotClient, EmulatedNiimbotTransport]:
    transport = EmulatedNiimbotTransport(**options)
    return NiimbotClient(transport, sleep=lambda _s: None), transport


def test_device_info_decodes_the_answers_observed_on_hardware() -> None:
    client, _ = client_for()
    info = client.device_info()
    assert info.model == "NIIMBOT B1"
    assert (info.device_type, info.software_version, info.hardware_version) == (
        4096,
        "6.19",
        "6.01",
    )
    assert info.serial_number == "I612120126"
    assert (info.battery_level, info.density, info.label_type) == (4, 3, 3)


def test_heartbeat_decodes_the_13_byte_layout() -> None:
    beat = client_for()[0].heartbeat()
    assert (beat.lid_state, beat.power_level, beat.paper_state, beat.rfid_state) == (0, 4, 0, 0)
    assert beat.cover_closed is True and beat.paper_present is True
    assert len(beat.raw) == 13


def test_heartbeat_reports_open_cover_and_missing_paper() -> None:
    beat = client_for(lid_open=True, paper_out=True)[0].heartbeat()
    assert beat.cover_closed is False and beat.paper_present is False


def test_an_error_packet_from_the_printer_aborts_the_job_with_its_payload() -> None:
    client, printer = client_for(errors=frozenset({RequestCode.SET_DIMENSION}))
    with pytest.raises(NiimbotError, match="0x13.*01"):
        client.print_raster(make_raster([bytes([1] * ROW)]), feed_rows=0)
    assert printer.commands[-1] == RequestCode.PRINT_END


def job_commands(printer: EmulatedNiimbotTransport) -> list[int]:
    """Commands of the print job itself, without the info queries."""
    return [c for c in printer.commands if c != RequestCode.GET_INFO]


def test_print_follows_the_job_lifecycle_and_rebuilds_the_exact_page() -> None:
    client, printer = client_for()
    pattern = [bytes([0xFF] * ROW), bytes([0x0F] * ROW), bytes(ROW), bytes([0xA5] * ROW)]

    result = client.print_raster(make_raster(pattern), feed_rows=10)

    assert job_commands(printer)[:7] == [0x21, 0x23, 0x01, 0x03, 0x13, 0xE3, 0xA3]
    assert printer.commands[-1] == RequestCode.PRINT_END
    assert printer.commands.count(RequestCode.PRINT_STATUS) == 3  # two busy polls, then done
    assert (printer.page_rows, printer.page_cols) == (14, 384)
    assert printer.bitmap == b"".join(pattern) + bytes(ROW * 10)
    assert result.rows == 14


def test_continuous_paper_type_reported_by_the_printer_is_preserved() -> None:
    client, printer = client_for(label_type=3)
    client.print_raster(make_raster([bytes([0xFF] * ROW)]), feed_rows=0)
    assert printer.payloads[RequestCode.SET_LABEL_TYPE] == b"\x03"


def test_explicit_density_and_label_type_override_the_defaults() -> None:
    client, printer = client_for()
    client.print_raster(make_raster([bytes([1] * ROW)]), density=5, label_type=1, feed_rows=0)
    assert printer.payloads[RequestCode.SET_DENSITY] == b"\x05"
    assert printer.payloads[RequestCode.SET_LABEL_TYPE] == b"\x01"


def test_identical_rows_collapse_into_repeats_and_blank_rows_use_the_empty_command() -> None:
    packets = list(encode_raster_rows([bytes([0xAA] * ROW)] * 300 + [bytes(ROW)] * 5))
    # 300 identical rows -> repeat 255 then 45; trailing blanks -> one empty-row packet
    assert [p[2] for p in packets] == [0x85, 0x85, 0x84]
    assert packets[0][9] == 255 and packets[1][9] == 45  # repeat byte of a bitmap row
    assert packets[2][6] == 5  # repeat byte of the empty-row packet
    assert packets[2][4:6] == (300).to_bytes(2, "big")


def test_legacy_variant_uses_the_short_start_and_dimension_payloads() -> None:
    client, printer = client_for()
    client.print_raster(make_raster([bytes([1] * ROW)]), start_variant="legacy", feed_rows=0)
    assert printer.payloads[RequestCode.START_PRINT] == b"\x01"
    assert printer.payloads[RequestCode.SET_DIMENSION] == bytes.fromhex("00010180")


def test_v3_variant_sends_the_seven_byte_start_and_six_byte_page_size() -> None:
    client, printer = client_for()
    client.print_raster(make_raster([bytes([1] * ROW)]), feed_rows=0)
    assert printer.payloads[RequestCode.START_PRINT] == bytes.fromhex("00010000000000")
    assert printer.payloads[RequestCode.SET_DIMENSION] == bytes.fromhex("000101800001")


def test_a_rejected_command_aborts_the_job_and_still_ends_the_print() -> None:
    client, printer = client_for(rejected=frozenset({RequestCode.START_PAGE}))
    with pytest.raises(NiimbotError, match="start page"):
        client.print_raster(make_raster([bytes([1] * ROW)]), feed_rows=0)
    assert printer.commands[-1] == RequestCode.PRINT_END
    assert RequestCode.PAGE_END not in printer.commands


def test_nothing_is_sent_when_the_job_is_rejected_before_it_starts() -> None:
    client, printer = client_for(rejected=frozenset({RequestCode.SET_DENSITY}))
    with pytest.raises(NiimbotError):
        client.print_raster(make_raster([bytes([1] * ROW)]))
    assert job_commands(printer) == [RequestCode.SET_DENSITY]  # never started: no END_PRINT


def test_a_printer_that_never_finishes_times_out() -> None:
    clock = iter(range(0, 10_000, 5))
    transport = EmulatedNiimbotTransport(status_polls_until_done=10**6)
    client = NiimbotClient(transport, sleep=lambda _s: None, monotonic=lambda: float(next(clock)))
    with pytest.raises(TimeoutError):
        client.print_raster(make_raster([bytes([1] * ROW)]), feed_rows=0, progress_timeout=20)
    assert transport.commands[-1] == RequestCode.PRINT_END


def test_invalid_jobs_are_refused_before_any_bytes_are_written() -> None:
    client, printer = client_for()
    narrow = RasterImage(width=64, height=1, data=bytes(8))
    with pytest.raises(ValueError, match="384"):
        client.print_raster(narrow)
    with pytest.raises(ValueError, match="density"):
        client.print_raster(make_raster([bytes(ROW)]), density=9)
    assert printer.commands == []


def test_silent_printer_raises_a_timeout() -> None:
    class Silent(EmulatedNiimbotTransport):
        def exchange(self, payload: bytes, **_options: object) -> bytes:
            raise TimeoutError("printer response timed out")

    with pytest.raises(TimeoutError):
        NiimbotClient(Silent()).device_info()


def test_unexpected_response_is_a_protocol_error() -> None:
    class Wrong(EmulatedNiimbotTransport):
        def exchange(self, payload: bytes, **_options: object) -> bytes:
            return bytes.fromhex("555531010131AAAA")

    with pytest.raises(ProtocolError, match="expected response"):
        NiimbotClient(Wrong()).heartbeat()
