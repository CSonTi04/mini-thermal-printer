import hashlib
import time
from pathlib import Path

import pytest
from PIL import Image

from tronic_printer.application import build_application
from tronic_printer.messages import PrintRaster
from tronic_printer.ports import PrinterTransport
from tronic_printer.showcase import ShowcasePage, build_showcase_pages

RESOURCE = Path(__file__).parents[1] / "resources" / "astronaut.png"
RESOURCE_SHA256 = "88431CD9653CCD539741B555FB0A46B61558B301D4110412B5BC28B5E3EA6CB5"


@pytest.fixture
def labeled_showcase(
    four_image_showcase_allowed: float,
) -> tuple[tuple[ShowcasePage, ...], float]:
    assert hashlib.sha256(RESOURCE.read_bytes()).hexdigest().upper() == RESOURCE_SHA256
    with Image.open(RESOURCE) as source:
        pages = build_showcase_pages(source)
    return pages, four_image_showcase_allowed


@pytest.mark.hil
@pytest.mark.printing
def test_live_ble_four_labeled_image_styles(
    labeled_showcase: tuple[tuple[ShowcasePage, ...], float],
    hil_ble_transport: PrinterTransport,
) -> None:
    pages, pause_seconds = labeled_showcase
    app = build_application(hil_ble_transport)
    completions: list[bytes] = []
    for index, page in enumerate(pages):
        summary = page.summary()
        print(f"showcase page {index + 1}/{len(pages)}: {summary}")
        result = app.commands.execute(PrintRaster(page.raster, feed_dots=160))
        completions.append(result.completion)
        if index + 1 < len(pages) and pause_seconds:
            time.sleep(pause_seconds)

    assert len(completions) == 4
    assert all(response[0] == 0xAA or response.startswith(b"OK") for response in completions)
