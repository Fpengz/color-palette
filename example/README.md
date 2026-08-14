# Demo samples

These synthetic product photos are ready to drag onto the Chromix upload area during a demo.

| File | Product | Product-color swatches typically extracted |
| --- | --- | --- |
| `coral-cup.png` | Injection-molded polypropylene cup | `#D0362B`, `#EE4C3A`, `#EB6B58` |
| `teal-crate.png` | HDPE storage crate | `#043B3C`, `#0C5A5C`, `#25787B` |
| `yellow-hard-hat.png` | ABS safety helmet | `#EEA806`, `#EFB748` |

## Suggested pitch flow

1. Start with `coral-cup.png` and upload it in **Color Capture**.
2. Point out that Chromix keeps the full-frame palette available but does not silently treat its largest cluster as the product.
3. Click **Select Region**, drag over the cup, and choose the bright coral swatch (`#EE4C3A` or its nearest extracted value).
4. Keep the default 230 kg batch and material inventory.
5. Select **Calculate Formula** to show ingredient masses, inventory limits, estimated cost, and predicted digital ΔE.
6. Repeat with the crate or helmet to demonstrate that the same inventory can be optimized for very different targets.

The listed colors are extraction examples rather than certified product measurements. Lighting, compression, and surface reflections naturally create several visible colors on one physical object. Production calibration should use controlled lighting or spectrophotometer readings.

## Sample API request

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -F "file=@example/coral-cup.png" \
  -F "colors=5"
```

To analyze only the cup after inspecting the full-frame palette, include an
ROI in original-image pixel coordinates:

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -F "file=@example/coral-cup.png" \
  -F "colors=5" \
  -F "roi_x=120" -F "roi_y=80" -F "roi_width=640" -F "roi_height=640"
```

The returned palette records `source` as `full_frame` or `roi` and preserves
the full-frame palette as context. A target must still be explicitly chosen
from a swatch, manually entered, or selected through the interface before a
formulation request is enabled.
