# Demo samples

These synthetic product photos are ready to drag onto the Chromix upload area during a demo.

| File | Product | Product-color swatches typically extracted |
| --- | --- | --- |
| `coral-cup.png` | Injection-molded polypropylene cup | `#D0362B`, `#EE4C3A`, `#EB6B58` |
| `teal-crate.png` | HDPE storage crate | `#043B3C`, `#0C5A5C`, `#25787B` |
| `yellow-hard-hat.png` | ABS safety helmet | `#EEA806`, `#EFB748` |

## Suggested pitch flow

1. Start with `coral-cup.png` and upload it in **Color Capture**.
2. Point out that Chromix separates the neutral studio background, product midtones, highlights, and shadows into reusable swatches.
3. Click the bright coral product swatch (`#EE4C3A` or its nearest extracted value).
4. Keep the default 230 kg batch and material inventory.
5. Select **Calculate Formula** to show exact ingredient masses, inventory limits, estimated cost, and predicted ΔE.
6. Repeat with the crate or helmet to demonstrate that the same inventory can be optimized for very different targets.

The listed colors are extraction examples rather than certified product measurements. Lighting, compression, and surface reflections naturally create several visible colors on one physical object. Production calibration should use controlled lighting or spectrophotometer readings.

## Sample API request

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -F "file=@example/coral-cup.png" \
  -F "colors=5"
```
