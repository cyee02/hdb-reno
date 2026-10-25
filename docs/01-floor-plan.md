# Floor Plan

Source: HDB 5-room layout sheet — [assets/floor-plan-original.jpg](assets/floor-plan-original.jpg).
Machine-readable version used by Blender: [`blender/data/floor_plan.json`](../blender/data/floor_plan.json). Keep both in sync.

![HDB plan](assets/floor-plan-original.jpg)

## Dimensions printed on the plan (mm)

- **Top (façade), left → right:** 3425 · 2400 · 3000 · 3000 · 3300 = **15125**
- **Right side, top → bottom:** 4450 · 1950 · 2600 = **9000**
- **Left side, top → bottom:** 4850 · 2900 = 7750
- **Bottom, left → right:** 1850 · 2400 · 4525 · 1455
- **Middle verticals:** Bedroom depth 3350 · corridor 1100 · 1650 (to kitchen) · kitchen depth 2900
- **Bathroom row:** 1950 (Bath 2) · 2250 (Bath 1) · 1625 (to façade)

## Coordinate system
Origin `(0,0)` is the top-left outer corner of the living room on the drawing. `x` goes right, `y` goes down the page. Units mm.

## Rooms

Values with **~** were scaled from the photo rather than read from a printed dimension — **approximate, verify on site with a tape measure**.

| Room | x from–to | y from–to | Size (approx) | Notes |
|---|---|---|---|---|
| Living/Dining | 0–3425 (+ dining hall 3425–8550) | 0–~4720 (hall ~3350–~6000) | — | Open plan; flows into study, foyer and kitchen |
| Suggested Study | 3425–5825 | 0–3350 | 2.40 × 3.35 m | Dashed walls on plan = optional, can be left open to living |
| Bedroom 3 | 5825–8825 | 0–3350 | 3.00 × 3.35 m | Door from corridor |
| Bedroom 2 | 8825–11825 | 0–3350 | 3.00 × 3.35 m | Door from corridor |
| Main Bedroom | 11825–15125 (+ lobby 10725–11825) | 0–4450 (lobby 3350–4450) | 3.30 × 4.45 m + lobby | Door sits **across the corridor** at x ≈ 10725, hinged on the Bedroom 2 side; opens into a small lobby that leads to the bedroom and en-suite Bath 1. Only window is on the façade; no window on the south wall beside Bath 1 |
| Corridor | ~8530–10725 | 3350–4450 | 1.1 m wide | Serves Bed 2, Bed 3, Main, Bath 2 |
| Bath/WC 2 (common) | ~9170–11160 | 4450–~6380 | ~1.95 × 1.95 m | Bi-fold door from corridor at x ≈ 9240–9940 (right at the WC's west wall, per HDB plan); small high window to air-con ledge side |
| Bath/WC 1 (main) | ~11160–13570 | 4450–~6380 | ~2.25 × 1.95 m | Bi-fold door from main bedroom at x ≈ 11950–12650 (towards the WC's west side, per HDB plan — ~920 mm to the left as you enter); window over air-con ledge |
| Air-con ledge | ~10770–13860 | ~6380–~7250 | — | Outdoor condenser units |
| Kitchen | ~4100–~8530 | ~6000–~8900 | ~4.5 × 2.9 m | Top edge dashed = can be open to dining. **No windows** |
| Service Yard | ~8530–~9980 | ~6380–~8900 | ~1.45 × 2.5 m | Laundry; bi-parting glass **sliding** door from the kitchen (leaves slide on the kitchen side) with a half-height window on each side (sill ~1100, top level with the door head); open (no grille) opening on east side to a drying ledge (to x ≈ 10650) with a 1 m parapet |
| Household Shelter | ~-100–~1750 (outer) | ~4720–~7780 (outer) | ~1.35 × 2.56 m (int.) | Outer face flush with living-room west wall and entrance wall. Reinforced concrete — **cannot be hacked or drilled** |
| Entrance / Foyer | ~1750–~4100 | ~4720–~7680 | ~2.4 m wide | Main door + gate on bottom edge |

## Structural notes
- Dark filled blocks on the façade (at roughly x ≈ 0, 5900, 9200 and the right edge) are columns/fins — structural, cannot be removed. Modelled as `columns` in the JSON, sticking out ~450 mm past the façade.
- The thick block between the dining area and Bath 2 (~x 8455–9170, y 4450–6380) is likely a structural wall / service duct. Modelled as `rc_wall_bath2`: kept thick, but trimmed flush with the bath walls and lined up with the kitchen/service-yard wall so it reads as one straight wall (as in HDB's 3D render).
- Household shelter walls, door and ceiling must not be altered (SCDF rules).
- Note on plan: *"Please refer to block plan for position of fins/walls at external façade where applicable."*

## Assumptions used in the 3D model
- Ceiling height 2600 mm.
- External walls 200 mm, internal 150 mm, shelter 250 mm.
- Doors 900 × 2100 mm (main door 1000 mm). Bathroom doors 700 mm bi-fold. Service-yard door is framed glass.
- Façade windows: sill 900 mm, head 2300 mm, black frames with 4 (main bedroom 5) vertical panes and a top transom — based on HDB's 3D render. WC windows are small and high (WC 2 ~400 × 450, WC 1 ~800 × 800).
- Toilet bowls and sinks in the WCs follow the positions drawn on the HDB plan (`fixtures` in the JSON, built by `build_fixtures.py`).
