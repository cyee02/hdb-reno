# Kitchen

> Status: draft — fill in as we decide. Claude: append new requirements here, keep the headings.

## Must have
- Layout per owner's sketch (2026-10-26): **one straight run** of top & bottom cabinets along the south (external) wall only — no cabinets on the west wall; **island in the middle**; fridge against the yard wall on the kitchen side; C1 cupboard just outside on the dining side.
- **Island is movable** — on lockable castors, **2000 × 700**, 900 high (level with the counters), pushed up close to the glass partition (~50 mm gap). Leaves a ~1.37 m aisle to the counter and ~755 mm to the fridge front so its doors can open.
- **No carpentry above the fridge.**
- **Full-height glass partition** sealing the kitchen from the dining area (slim black frames, like the BANGYUAN "semi-open kitchen" reference). 6 sliding panels on 6 tracks (telescopic): when opened, **all panels slide east and stack flush against the side of the fridge**, in the ~200 mm slot between the fridge and C1, leaving the full kitchen width open.
- **Bottom cabinets 90 cm high** (incl. worktop) so items can sit on the counter. **Top cabinets go all the way to the ceiling.**
- **Cupboard C1** (dining side, along the east wall **from the glass partition to just before the corridor**, ~1400 W × 600 D — stops ~200 mm short of the fridge to leave the slot for the 6 stacked glass panels) = coffee / tea / matcha station: wine cellar (600 W, corridor end) + cabinet doors at the bottom, full-width drawer above, coffee machine + tea / matcha set on the counter. Top cabinet (to ceiling, 3 columns) stores **whisky** (bottom row, glass doors), tea / matcha items (middle, solid doors) and **wine glasses** (top row, glass doors).

## Nice to have
- LED strips under the top cabinets and inside C1's glass rows.

## Avoid / don't want
- _TODO_

## Room-specific questions
- Open or closed kitchen (dashed line on plan)?
- Layout: L-shape / galley / island?
- Appliances: fridge size, built-in oven, dishwasher, hob type
- Countertop material (quartz / sintered stone / solid surface)

## Materials & finishes
| Element | Choice | Notes |
|---|---|---|
| Floor | _TODO_ | |
| Walls | _TODO_ | |
| Ceiling / lighting | _TODO_ | |

## Model notes
- Data: `blender/data/kitchen.json` → `blender/scripts/build_kitchen.py` (collections `Carpentry.Kitchen`, `Appliances.Kitchen`, `Furniture.Kitchen`, `Furniture.Dining`, `Accessories.Kitchen`). The glass panels and the yard door are movable in Blender (HDB Reno tab > Doors: slider, Open / Close, Shift+Alt+O, Make Animation); `partition.open` (0–1) is the starting position after a rebuild.
- **Hob, oven, sink and dishwasher positions are suggestions** (not on the sketch): hob + oven + slim hood on the south run left of centre, sink + dishwasher at the east end near the yard.
- The south cabinet run (x 4300–8395) stops ~60 mm short of the yard wall so the yard door's south sliding leaf can still open. The top cabinets there sit in front of the small window south of the yard door.
- The fridge (830 W × 700 D assumed) ends just clear of the yard door's north leaf, but covers part of the small window north of the door. **Check the actual fridge width** — anything wider than ~850 mm clashes with the door.
- C1 counter is 900 high, so the wine cellar must be a low (~700 mm) under-counter model, or the drawer goes.

## Open questions
- Hob type (gas / induction) and where it goes; hood ducting route (no window).
- Fridge model + width (≤ ~850 mm to clear the yard door).
- Wine cellar model and bottle count.
- Kitchen has **no window** (per HDB layout), so plan for a good cooker hood and ventilation/lighting via the service yard.
