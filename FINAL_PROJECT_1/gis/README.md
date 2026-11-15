# GIS

Everything that is opened in ArcGIS Pro (or QGIS). The layers are made by the scripts of each folder;
this folder has the scripts that **style** them inside ArcGIS and the 3D export.

## Layers (GeoPackage, local metres, EPSG:3857)

| File | Made by | What it shows |
|---|---|---|
| `shielding/cad/orion_floor_plans.gpkg` | `shielding/cad/floor_plans_gis.py` | the 4 floor plans: hull, rooms, equipment |
| `shielding/data/room_doses_floors.gpkg` | `shielding/03_dose.py` | the floor plans with the dose of every room (current storm) |
| `shielding/data/room_doses_floors_S4.gpkg` | `shielding/03_dose.py` | the same for the S4 example storm |
| `warning/data/alert_map.gpkg` | `warning/alert.py` | worst-case dose per room, the storm shelter = the place to go |

## Styling scripts (run INSIDE ArcGIS Pro, Python Window)

```
exec(open(r"C:\Creations\python\hackathlon\Radiation-ML-\gis\style_floor_plans.py").read())
```

| Script | Map |
|---|---|
| `style_floor_plans.py` | rooms coloured by dose level, labels with mSv and % of the limit |
| `style_floor1.py` | floor 1 (service module): tanks and hull |
| `style_alert.py` | new map "Alert": rooms by level, the shelter outlined in red |

## Layout of the 4 floor plans (no radiation values)

`python gis/layout_floor_plans.py` -> `gis/layout/floor_plans_layout.png` (300 dpi, slides),
`.pdf` and `.svg` (vector). All floors at the same scale.

## 3D

`python gis/arcgis_export.py` (after `shielding/01_anatomy.py`) writes `gis/3d/`:
`orion.obj` (Import 3D Files; GLB is rejected by ArcGIS), `parts/` (one file per part),
`orion_voxels.nc` (voxel layer), `orion_points.csv` (plan B: XY Table To Point with Z).
