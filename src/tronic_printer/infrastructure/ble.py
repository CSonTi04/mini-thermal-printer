"""Read-only BLE discovery helpers; no printer writes are implemented here."""

from __future__ import annotations

from dataclasses import dataclass

from bleak import BleakClient, BleakScanner


@dataclass(frozen=True, slots=True)
class BleDevice:
    name: str | None
    address: str
    rssi: int | None


async def discover(
    timeout: float = 5.0,
    name_prefix: str = "Mini Pocket Printer",
) -> list[BleDevice]:
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    matches: list[BleDevice] = []
    for device, advertisement in devices.values():
        name = advertisement.local_name or device.name
        if name and name.startswith(name_prefix):
            matches.append(BleDevice(name=name, address=device.address, rssi=advertisement.rssi))
    return sorted(matches, key=lambda item: item.address)


async def inspect_gatt(address: str) -> list[dict[str, object]]:
    """Connect and enumerate GATT metadata without reading or writing values."""
    async with BleakClient(address) as client:
        return [
            {
                "service": service.uuid,
                "characteristic": characteristic.uuid,
                "properties": sorted(characteristic.properties),
            }
            for service in client.services
            for characteristic in service.characteristics
        ]
