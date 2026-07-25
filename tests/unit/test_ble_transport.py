from collections.abc import Callable

from tronic_printer.application import build_application
from tronic_printer.infrastructure.ble import FF01_RESPONSE, FF03_CONTROL, BleTransport
from tronic_printer.messages import GetDeviceInfo
from tronic_printer.protocol import (
    QUERY_BATTERY,
    QUERY_DENSITY,
    QUERY_FIRMWARE,
    QUERY_MODEL,
    QUERY_STATUS,
)


class FakeCharacteristic:
    max_write_without_response_size = 100


class FakeServices:
    def get_characteristic(self, _uuid: str) -> FakeCharacteristic:
        return FakeCharacteristic()


class FakeBleakClient:
    def __init__(self, _address: str, **_options: object) -> None:
        self.is_connected = False
        self.services = FakeServices()
        self.callbacks: dict[str, Callable[[object, bytearray], None]] = {}
        self.writes: list[bytes] = []
        self.responses = {
            QUERY_MODEL: b"A2Y",
            QUERY_FIRMWARE: b"V1.06LY",
            QUERY_BATTERY: bytes.fromhex("00 5C"),
            QUERY_DENSITY: bytes.fromhex("01 0C 10"),
            QUERY_STATUS: b"\x00",
        }

    async def connect(self) -> None:
        self.is_connected = True

    async def start_notify(
        self,
        characteristic: str,
        callback: Callable[[object, bytearray], None],
    ) -> None:
        self.callbacks[characteristic] = callback
        if characteristic == FF03_CONTROL:
            callback(characteristic, bytearray((0x01, 10)))
            callback(characteristic, bytearray((0x02, 20, 0)))

    async def write_gatt_char(
        self,
        _characteristic: str,
        payload: bytes,
        *,
        response: bool,
    ) -> None:
        assert not response
        request = bytes(payload)
        self.writes.append(request)
        self.callbacks[FF01_RESPONSE](FF01_RESPONSE, bytearray(self.responses[request]))
        self.callbacks[FF03_CONTROL](FF03_CONTROL, bytearray((0x01, 1)))

    async def disconnect(self) -> None:
        self.is_connected = False


def test_ble_transport_runs_cqrs_queries_with_credit_flow() -> None:
    fake = FakeBleakClient("mock")

    with BleTransport("mock", client_factory=lambda *_args, **_kwargs: fake) as transport:
        info = build_application(transport).queries.ask(GetDeviceInfo())
        connection = transport.connection_info

    assert info.model == "A2Y"
    assert info.firmware == "V1.06LY"
    assert info.battery_percent == 92
    assert info.density == 1
    assert info.status.raw == 0
    assert connection["packet_size"] == 20
    assert connection["host_write_limit"] == 100
    assert fake.writes == [
        QUERY_MODEL,
        QUERY_FIRMWARE,
        QUERY_BATTERY,
        QUERY_DENSITY,
        QUERY_STATUS,
    ]
