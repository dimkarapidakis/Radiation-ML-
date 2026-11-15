# Shielding

`shielding.py` is the whole shielding in ONE file. It runs **automatically every 5 minutes from
`live/06_live.py`** (after every new forecast), or by hand:

```
python shielding/shielding.py
```

1. **Anatomy**: Orion as a 3D grid of 5 cm cubes, every cube with a material and a density
   (Avcoat / tiles -> aluminium 4 mm + ribs -> HDPE 5 cm everywhere; storm shelter HDPE 15 cm).
2. **Rays**: from the centre of every room, 400 rays in all directions (Fibonacci sphere); along every ray
   `shielding = sum(density x aluminium equivalence x length)` in g/cm2.
   Steps 1-2 depend only on the spacecraft: made once and kept in `data/` (`REBUILD = True` to make them again).
3. **Storm**: the WORST CASE of the newest forecast (forecast + 1.65 x error of the model; scaled up if the
   flux is already above the forecast). `STORM = "October 1989"` = the NASA design reference storm instead.
4. **Dose**: protons -> through every ray + the body (6.5 g/cm2 to the blood-forming organs) -> energy left
   (NIST PSTAR range and stopping power) -> Gy x 1.5 (RBE) = mSv; dose of a room = average of its 400 rays.
   The storm shelter lets in 5% of the storm (team assumption: many layers).
5. **Crew**: where is every astronaut now (demo: they walk smoothly and at random, room to room through
   the doors, kept in `data/crew_live.csv` between the runs; real spacecraft: badges) ->
   the best room around him: among the rooms reachable within 1.5 minutes, the one with the least
   **dose on the way** (Dijkstra on the doors, each door = minutes x dose rate of its rooms) **+ storm dose in
   the room**. He moves only if it saves at least 1 mSv, and stays there until the storm is over.

Output: `data/room_doses.csv / .json`, `data/crew_orders.csv / .json`, `data/shielding_readable.json` (plain words, for the app),
`data/room_doses_floors.gpkg` (floor plans with dose, astronauts, routes), `Figures/room_doses_floors.png`.

Example (`STORM = "October 1989"`, crew at 11 Nov 10:00): every astronaut goes to the shelter in 0.5-1 min
(e.g. galley -> hygiene -> shelter) and gets ~2 mSv instead of 104-110 mSv.

| Folder | What |
|---|---|
| `data/` | voxels, rooms, rays, room doses, crew orders |
| `Figures/` | anatomy, room doses on the floor plans |
| `cad/` | the spacecraft in CAD (STEP, STL, DXF) and the floor plans (DXF, PNG, GPKG) |
| `Destel/` | real dose inside the ISS (DOSTEL, September 2017) as a reference |
