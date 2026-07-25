import hashlib
import zlib
from pathlib import Path

from tronic_printer.domain import RasterImage
from tronic_printer.protocol import compress_code_esc, encode_compressed_raster


def test_code_esc_exactly_reproduces_captured_native_payload() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "codeesc-hello-world.hex"
    captured = bytes.fromhex(fixture_path.read_text(encoding="ascii"))

    raw = zlib.decompress(captured, wbits=10)

    assert len(captured) == 217
    assert hashlib.sha256(captured).hexdigest().upper() == (
        "8E72234F7B247B067D2E4F08A0023B42190D6436BEE4DD23F32146B9267586F6"
    )
    assert len(raw) == 48 * 37
    assert hashlib.sha256(raw).hexdigest().upper() == (
        "72D4FED9D387831DC6F3BEC1750372BDE59AEEBC25D0F186F2A8A754D44FF400"
    )
    assert compress_code_esc(raw) == captured


def test_compressed_raster_uses_big_endian_envelope() -> None:
    raster = RasterImage.test_pattern(384, 32, line_width=3)

    frame = encode_compressed_raster(raster)
    payload_length = int.from_bytes(frame[6:10], "big")

    assert frame[:6] == bytes.fromhex("1F 10 00 30 00 20")
    assert payload_length == len(frame) - 10
    assert zlib.decompress(frame[10:], wbits=10) == raster.data
