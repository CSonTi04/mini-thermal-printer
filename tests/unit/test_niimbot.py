import pytest

from tronic_printer.domain import ProtocolError
from tronic_printer.niimbot import (
    B1_PROFILE,
    NiimbotFrameBuffer,
    NiimbotPacket,
    decode_row,
    encode_empty_row,
    encode_print_start,
    encode_row,
    encode_set_page_size,
)


def test_b1_profile_tracks_upstream_model() -> None:
    assert B1_PROFILE.model_id == 4096
    assert B1_PROFILE.dpi == 203
    assert B1_PROFILE.printhead_pixels == 384
    assert B1_PROFILE.row_bytes == 48
    assert B1_PROFILE.paper_types == (1, 2, 5)


def test_packet_round_trip_and_checksum() -> None:
    packet = NiimbotPacket(0x31, b"\x01")
    wire = packet.to_bytes()
    assert wire == bytes.fromhex("555531010131AAAA")
    assert NiimbotPacket.from_bytes(wire) == packet

    connect = NiimbotPacket(0xC1, b"\x01", prefix=b"\x03")
    assert connect.to_bytes(include_connect_prefix=True) == bytes.fromhex("035555C10101C1AAAA")
    assert NiimbotPacket.from_bytes(connect.to_bytes(include_connect_prefix=True)) == connect


def test_frame_buffer_handles_fragmented_and_concatenated_streams() -> None:
    stream = NiimbotFrameBuffer()
    assert stream.feed(bytes.fromhex("555531010131AAAA555533010133AAAA")) == [
        NiimbotPacket(0x31, b"\x01"),
        NiimbotPacket(0x33, b"\x01"),
    ]

    fragmented = stream.feed(bytes.fromhex("5555B304000164"))
    assert fragmented == []
    assert stream.feed(bytes.fromhex("64B6AAAA")) == [
        NiimbotPacket(0xB3, bytes.fromhex("00016464"))
    ]


def test_encode_row_payload_matches_upstream_split_and_total_modes() -> None:
    row = bytes.fromhex("FF00DF0F")
    split_payload = encode_row(row_index=0, row_bits=row, page_cols=32, black_count_mode="split")
    total_payload = encode_row(row_index=0, row_bits=row, page_cols=32, black_count_mode="total")

    assert split_payload == bytes.fromhex("000013000001FF00DF0F")
    assert total_payload == bytes.fromhex("000000130001FF00DF0F")

    decoded = decode_row(split_payload)
    assert decoded["row_index"] == 0
    assert decoded["count_segment"] == [19, 0, 0]
    assert decoded["repeat"] == 1
    assert decoded["black_total"] == 19


def test_print_job_helpers_match_upstream_b1_variants() -> None:
    assert encode_print_start(1) == bytes.fromhex("555501070001000000000007AAAA")
    assert encode_set_page_size(200, 384, 1) == bytes.fromhex("5555130600C8018000015DAAAA")
    assert encode_empty_row(5, repeat=3) == bytes.fromhex("5555840300050381AAAA")


def test_bad_checksum_is_rejected() -> None:
    with pytest.raises(ProtocolError):
        NiimbotPacket.from_bytes(bytes.fromhex("5555310101CEAAAA"))
