# HTML template gallery

Each folder contains a self-contained Jinja HTML template and sample JSON data.
Installed packages include the same gallery; use `tronic-printer templates` to
list it and `tronic-printer copy-template NAME DESTINATION` to make an editable
copy.

Render any example with:

```powershell
.venv\Scripts\tronic-printer.exe prepare-html `
  examples\checklist\checklist.html `
  --data examples\checklist\data.json `
  --output analysis-work\checklist.png
```

The gallery includes:

- `receipt`: itemized retail receipt and local SVG asset;
- `shipping-label`: compact parcel/address label with Code 128 and QR symbols;
- `postcard-address`: four-part recipient address with rules under the first three lines;
- `parcel-drop-in`: sender/receiver contact form with a plain tracking number;
- `checklist`: grouped tasks with conditional completion and priority states;
- `kitchen-ticket`: order items, modifiers, allergy warning, and payment state;
- `inventory-label`: SKU, storage location, stock level, barcode, and QR code;
- `event-ticket`: attendee details, admission information, and validation QR;
- `photo-note`: a captioned illustration demonstrating whole-page dithering.

The shipping example is a compact parcel organizer, not a standards-compliant
carrier label. Barcode readability varies with printer density, paper, scaling,
and scanner. Verify codes on the physical printer before operational use.

For the photo note, Floyd–Steinberg is a useful starting point:

```powershell
.venv\Scripts\tronic-printer.exe prepare-html `
  examples\photo-note\photo-note.html `
  --data examples\photo-note\data.json `
  --dither floyd-steinberg --threshold 128 `
  --output analysis-work\photo-note.png
```

To use a bitmap photo with independent dithering, place it beside the template
and set `photo_prepared` to its relative filename. The template then uses
`printer_image(...)`; otherwise it renders the supplied local illustration via
the whole-page dither pass.
