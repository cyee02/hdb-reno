# Renovation style copies

One `.blend` per style, each started from the base model.

## Start a new style

```bash
cp blender/base/hdb-reno-base.blend blender/styles/<style-name>.blend
```

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
