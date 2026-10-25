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

## Base model and style copies

- `blender/hdb-reno.blend` — the working model that the build scripts update.
- `blender/base/hdb-reno-base.blend` — frozen snapshot of the agreed layout (shell + WC fixtures, no styling). **Don't edit it**; copy it to start a new style.
- `blender/styles/<style-name>.blend` — one file per renovation style (e.g. `scandi.blend`, `japandi.blend`). Put styling in its own collections (`Furniture`, `Carpentry`, `Materials`…), never inside `Flat` or `Fixtures`, so a rebuild keeps it.
- Render a style with `RENDER_TAG=<style-name>` so its images in `blender/renders/` don't overwrite others.
- If the layout changes later, update the JSON, rebuild each style file (command below with that file instead of `hdb-reno.blend`), and refresh the base snapshot.

## Commands

Rebuild the model and render (headless):

```bash
/Applications/Blender.app/Contents/MacOS/Blender -b blender/hdb-reno.blend -P blender/scripts/build_flat.py -P blender/scripts/build_fixtures.py -P blender/scripts/build_service_yard.py -P blender/scripts/build_household_shelter.py -P blender/scripts/build_main_bedroom.py -P blender/scripts/build_kitchen.py -P blender/scripts/render_views.py
```

Open the `.blend` (as above) so other collections are kept; without it Blender starts from an empty scene and the save overwrites the file with only what the scripts build. Close the file in the Blender app first, or use the MCP route below, so the two don't overwrite each other.
Bathroom fixtures (toilets, sinks) come from `fixtures` in the JSON and are built into the `Fixtures` collection by `build_fixtures.py`.
Room renovations each get a data file + script, e.g. `blender/data/service_yard.json` → `build_service_yard.py`, building into `Carpentry.<Room>` and `Appliances.<Room>` (children of `Carpentry` / `Appliances`). Each script only rebuilds its own collections.
The main bedroom has layout options: `blender/data/main_bedroom_design<N>.json`, chosen with env `MB_DESIGN=<N>` (default 2) when running `build_main_bedroom.py`. Room scripts can register extra camera views in `scene["room_cameras"]`; `render_views.py` renders them.

Renders go to `blender/renders/`. Render cameras + the sun live in the `Cameras` collection, hidden in the viewport after each render (eye icon in the Outliner to show them). The `.blend` file is saved to `blender/hdb-reno.blend`.

## Viewing tools

`blender/tools/hdb_view_tools.py` (installed add-on): **Alt+W** in the 3D viewport toggles the walls + windows on/off; **Shift+Alt+P** jumps to the plan view (top-down orthographic, north up, framed on the whole flat). Viewport only, renders unaffected. Also buttons in the N panel > **HDB Reno** tab.

## Blender MCP (live editing)

The `blender` MCP server (open-source `blender-mcp`) lets Claude control a running Blender.
1. Open Blender, press `N` in the 3D viewport → **MCP for Blender** tab → **Connect** (add-on source: `blender/tools/blender_mcp_addon.py`, already installed).
2. In Claude, use the `blender` MCP tools (e.g. `get_scene_info`, `execute_blender_code`).
To rebuild via MCP, run `blender/scripts/build_flat.py`, `build_fixtures.py`, then any room scripts (e.g. `build_service_yard.py`, `build_household_shelter.py`, `build_main_bedroom.py`, `build_kitchen.py`) with `execute_blender_code`, then save the file (it finds the JSON via the `HDB_RENO_ROOT` path set at the top of the script).
