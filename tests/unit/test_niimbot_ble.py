import asyncio
from types import SimpleNamespace

import pytest
from bleak.exc import BleakError

from tronic_printer.domain import RasterImage
from tronic_printer.infrastructure.niimbot_ble import (
    NIIMBOT_SERVICE,
    NiimbotBleTransport,
)
from tronic_printer.niimbot import NIIMBOT_ROW_BYTES
from tronic_printer.niimbot_client import NiimbotClient
from tronic_printer.testing import EmulatedNiimbotTransport

ROW = NIIMBOT_ROW_BYTES
NOTIFY_FRAGMENT = 7  # replies arrive in tiny notifications, like a slow BLE link


def characteristic(properties, max_write=237):
    return SimpleNamespace(
        uuid="bef8d6c9", properties=properties, max_write_without_response_size=max_write
    )


def services(*groups):
    return [SimpleNamespace(uuid=uuid, characteristics=chars) for uuid, chars in groups]


class FakeBleakClient:
    """A bleak client whose GATT characteristic is backed by the emulated B1."""

    instances: list["FakeBleakClient"] = []

    def __init__(self, device, timeout=10.0, *, printer=None, layout=None):
        self.device = device
        self.printer = printer or EmulatedNiimbotTransport()
        self.is_connected = False
        self.writes: list[bytes] = []
        self.fail_connect: Exception | None = None
        self.char = characteristic({"notify", "write-without-response", "read", "write"})
        self.services = layout or services((NIIMBOT_SERVICE, [self.char]))
        self._callback = None
        FakeBleakClient.instances.append(self)

    async def connect(self):
        if self.fail_connect:
            raise self.fail_connect
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, char, callback):
        self._callback = callback

    async def write_gatt_char(self, char, data, response=True):
        if not self.is_connected:
            raise BleakError("not connected")
        assert response is False
        self.writes.append(bytes(data))
        self.printer.write(bytes(data))
        replies = self.printer.drain_replies()
        for i in range(0, len(replies), NOTIFY_FRAGMENT):
            self._callback(None, bytearray(replies[i : i + NOTIFY_FRAGMENT]))
            await asyncio.sleep(0)


async def find_fixed_device(address, name_prefix, timeout):
    return SimpleNamespace(address="12:06:12:F9:03:6A", name="B1-I612120126")


def transport(**options):
    FakeBleakClient.instances.clear()
    options.setdefault("client_factory", FakeBleakClient)
    options.setdefault("device_finder", find_fixed_device)
    options.setdefault("packet_interval", 0)
    return NiimbotBleTransport(**options)


def test_niimbot_client_queries_work_over_fragmented_notifications():
    with transport() as ble:
        info = NiimbotClient(ble).device_info()
        beat = NiimbotClient(ble).heartbeat()
    assert (info.model, info.serial_number, info.software_version) == (
        "NIIMBOT B1",
        "I612120126",
        "6.19",
    )
    assert beat.cover_closed is True and beat.paper_present is True


def test_a_full_print_over_ble_rebuilds_the_exact_page_in_small_ordered_writes():
    rows = [bytes([0xFF] * ROW), bytes(ROW), bytes([0x5A] * ROW)] * 20
    raster = RasterImage(width=384, height=len(rows), data=b"".join(rows))
    with transport(write_chunk=64) as ble:
        NiimbotClient(ble, sleep=lambda _s: None).print_raster(raster, feed_rows=4)
        client = FakeBleakClient.instances[0]
    assert client.printer.bitmap == b"".join(rows) + bytes(ROW * 4)
    assert client.printer.commands[-1] == 0xF3
    assert max(len(w) for w in client.writes) <= 64  # never one big burst


def test_write_chunk_is_capped_by_the_characteristics_own_limit():
    layout_char = characteristic({"notify", "write-without-response"}, max_write=20)
    layout = services((NIIMBOT_SERVICE, [layout_char]))
    with transport(
        client_factory=lambda device, timeout: FakeBleakClient(device, timeout, layout=layout),
        write_chunk=200,
    ) as ble:
        ble.write(bytes(100))
        assert [len(w) for w in FakeBleakClient.instances[0].writes] == [20] * 5


def test_the_b1_service_wins_over_other_notify_characteristics():
    decoy = characteristic({"notify", "write-without-response"}, max_write=11)
    real = characteristic({"notify", "write-without-response"}, max_write=99)
    layout = services(("49535343-fe7d-4ae5-8fa9-9fafd205e455", [decoy]), (NIIMBOT_SERVICE, [real]))
    with transport(
        client_factory=lambda device, timeout: FakeBleakClient(device, timeout, layout=layout)
    ) as ble:
        assert ble._characteristic is real


def test_the_resolved_address_is_exposed_so_callers_can_skip_the_scan_next_time():
    with transport() as ble:
        assert ble.address == "12:06:12:F9:03:6A"


def test_auto_means_scan_and_an_explicit_address_is_passed_to_the_finder():
    seen = []

    async def finder(address, name_prefix, timeout):
        seen.append((address, name_prefix))
        return "12:06:12:F9:03:6A"

    transport(address="auto", device_finder=finder).close()
    transport(address="AA:BB:CC:DD:EE:FF", device_finder=finder).close()
    assert seen == [(None, "B1-"), ("AA:BB:CC:DD:EE:FF", "B1-")]


def test_printer_not_found_is_an_oserror_like_a_missing_usb_port():
    async def nothing(address, name_prefix, timeout):
        return None

    with pytest.raises(OSError, match="not found over BLE"):
        transport(device_finder=nothing)


def test_bleak_failures_become_oserror_and_do_not_leak_a_connection():
    def factory(device, timeout):
        client = FakeBleakClient(device, timeout)
        client.fail_connect = BleakError("device busy")
        return client

    with pytest.raises(OSError, match="device busy"):
        transport(client_factory=factory)


def test_a_device_without_the_characteristic_is_refused_and_disconnected():
    layout = services(("0000180a-0000-1000-8000-00805f9b34fb", [characteristic({"read"})]))
    with pytest.raises(OSError, match="not a NIIMBOT"):
        transport(client_factory=lambda d, timeout: FakeBleakClient(d, timeout, layout=layout))
    assert not FakeBleakClient.instances[0].is_connected


def test_a_silent_printer_times_out_instead_of_hanging():
    class Mute(EmulatedNiimbotTransport):
        def drain_replies(self):
            return b""

    def mute_client(device, timeout):
        return FakeBleakClient(device, timeout, printer=Mute())

    with transport(client_factory=mute_client) as ble, pytest.raises(TimeoutError):
        ble.exchange(b"\x55\x55\xdc\x01\x01\xdc\xaa\xaa", timeout=0.3)


def test_dropping_the_link_mid_session_is_an_oserror():
    ble = transport()
    FakeBleakClient.instances[0].is_connected = False
    with pytest.raises(OSError, match="BLE error"):
        ble.write(b"x")
    ble.close()


def test_close_disconnects_and_is_idempotent_and_blocks_further_use():
    ble = transport()
    client = FakeBleakClient.instances[0]
    ble.close()
    ble.close()
    assert not client.is_connected
    with pytest.raises(OSError, match="closed"):
        ble.write(b"x")


def test_invalid_pacing_arguments_are_rejected():
    with pytest.raises(ValueError):
        NiimbotBleTransport(write_chunk=0)
