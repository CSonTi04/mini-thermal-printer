import json
from pathlib import Path

from tronic_printer import protocol


def test_sanitized_capture_fixture_matches_protocol_constants() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "official_app_session.json"
    capture = json.loads(fixture_path.read_text(encoding="utf-8"))
    exchanges = capture["exchanges"]

    assert bytes.fromhex(exchanges[0]["request"]) == protocol.QUERY_MODEL
    assert bytes.fromhex(exchanges[1]["request"]) == protocol.QUERY_FIRMWARE
    assert bytes.fromhex(exchanges[2]["request"]) == protocol.QUERY_BATTERY
    assert bytes.fromhex(exchanges[3]["request"]) == protocol.QUERY_STATUS
    assert bytes.fromhex(exchanges[4]["request"]) == protocol.set_density(2)
    assert bytes.fromhex(exchanges[5]["request"]) == protocol.QUERY_DENSITY
    assert capture["print"]["width_bytes"] == protocol.MAX_PRINT_WIDTH // 8
    assert bytes.fromhex(capture["print"]["completion_hex"])[0] == 0xAA
