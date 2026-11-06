# Renovation style copies

One `.blend` per style.

## Start a new style

From the full agreed design (all rooms furnished, cameras, movable doors) — the usual start for a theme:

```bash
cp blender/saved_versions/hdb-reno-template.blend blender/styles/<style-name>.blend
```

Or from the bare shell (walls + WC fixtures only):

```bash
cp blender/saved_versions/hdb-reno-base.blend blender/styles/<style-name>.blend
```

A theme mostly changes finishes: the colours in each room's `finishes` block (`blender/data/*.json`) and the materials they create (prefixes `KT_`, `LV_`, `ST_`, `EN_`, `WC_`, `BR_`, …). Change materials in the style file itself so the shared JSON (and the other styles) stay as they are. Note: re-running a room's build script in a style file resets that room's materials to the JSON colours.

Open it in Blender and add furniture, carpentry and finishes in **new collections** (`Furniture`, `Carpentry`, …). Leave `Flat` and `Fixtures` alone: the build scripts rebuild those from `blender/data/floor_plan.json`.

## Render a style

```bash
RENDER_TAG=<style-name> /Applications/Blender.app/Contents/MacOS/Blender -b blender/styles/<style-name>.blend -P blender/scripts/render_views.py
```

Images land in `blender/renders/<style-name>_*.png`.

## If the floor plan changes

Rebuild the shell inside the style file. Your style collections are kept:

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b blender/styles/<style-name>.blend -P blender/scripts/build_flat.py -P blender/scripts/build_fixtures.py
```

To add the service-yard carpentry and appliances to a style, also run `-P blender/scripts/build_service_yard.py` (finishes come from `blender/data/service_yard.json`).
