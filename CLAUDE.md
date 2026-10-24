# HDB 5-Room Renovation — Project Guide for Claude

This repo tracks the renovation of our HDB 5-room flat. It has two halves:

1. **`docs/`** — requirements and decisions in Markdown. This is the source of truth for *what we want*.
2. **`blender/`** — a 3D model of the flat, used to visualise the result. This is *what it will look like*.

## Working rules

- When the user states a preference or requirement, record it in the matching file under `docs/02-requirements/` (one file per room, plus `whole-house.md`).
- When something is decided (contractor, material, layout change), add a dated entry to `docs/03-decisions-log.md`.
- Floor-plan geometry lives in **one** place: `blender/data/floor_plan.json`. `docs/01-floor-plan.md` is the human-readable version — keep them in sync.
- Never hand-edit geometry only inside Blender. Change the JSON (or add a script), then rebuild, so the model stays reproducible.

## Model conventions

- Units in JSON: **millimetres**. Blender scene units: metres (script divides by 1000).
- Plan origin `(0, 0)` = top-left outer corner of the living room façade as drawn on the HDB plan. Plan `+x` = right, plan `+y` = down the page. In Blender, `Y = -y` so the model looks like the drawing from above.
- Floor-to-ceiling height 2600 mm. External walls 200 mm, internal 150 mm, shelter 250 mm (typical HDB values — assumptions, verify on site).
- All generated objects live in the Blender collection `Flat`. Renovation additions (furniture, carpentry) should go in separate collections, e.g. `Furniture`, `Carpentry`, so the shell can be rebuilt without losing them.

## Commands

Rebuild the model and render (headless):

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b -P blender/scripts/build_flat.py -P blender/scripts/render_views.py
```

Renders go to `blender/renders/`. The `.blend` file is saved to `blender/hdb-reno.blend`.

## Blender MCP (live editing)

The `blender` MCP server (open-source `blender-mcp`) lets Claude control a running Blender.
1. Open Blender, press `N` in the 3D viewport → **MCP for Blender** tab → **Connect** (add-on source: `blender/tools/blender_mcp_addon.py`, already installed).
2. In Claude, use the `blender` MCP tools (e.g. `get_scene_info`, `execute_blender_code`).
To rebuild via MCP, run the contents of `blender/scripts/build_flat.py` with `execute_blender_code` (it finds the JSON via the `HDB_RENO_ROOT` path set at the top of the script).
