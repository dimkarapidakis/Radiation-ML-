# =====================================================================
# arcgis_export.py
# Files for ArcGIS Pro (Local Scene):
#
#   gis/3d/orion.glb, orion.obj        the whole spacecraft (Import 3D Files -> 1 multipatch)
#   gis/3d/parts/*.glb, parts_obj/*.obj one file per part  (Import 3D Files on the folder
#                                                -> 1 multipatch feature per part, named by the file)
#   gis/3d/orion_voxels.nc             the anatomy as a voxel layer
#                                                (Add Data -> Multidimensional Voxel Layer)
#   gis/3d/orion_points.csv            plan B: the voxels as 3D points every 10 cm
#                                                (XY Table To Point, with Z field = z)
#
# Axes for ArcGIS: x = x, y = -z (plan view, like the floor plans), z = up (spacecraft axis).
# Units: metres. Coordinates are local (origin = bottom centre of the service module).
#
# Needs:  pip install cadquery trimesh xarray netCDF4
# Run:    python gis/arcgis_export.py      (after shielding/01_anatomy.py)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os
import re
import runpy

import numpy as np
import trimesh
import xarray as xr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIELDING = os.path.join(ROOT, "shielding")
CAD_SCRIPT = os.path.join(SHIELDING, "cad", "orion_cad.py")
VOXELS_IN = os.path.join(SHIELDING, "data", "orion_voxels.npz")
ROOMS_IN = os.path.join(SHIELDING, "data", "rooms.json")
OUT = os.path.join(ROOT, "gis", "3d")
PARTS = os.path.join(OUT, "parts")
PARTS_OBJ = os.path.join(OUT, "parts_obj")
os.makedirs(PARTS, exist_ok=True)
os.makedirs(PARTS_OBJ, exist_ok=True)

# a projected coordinate system in metres, needed by the Local Scene (the place does not matter)
CRS_WKT = ('PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
           'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
           'PROJECTION["Mercator_Auxiliary_Sphere"],PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
           'PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],'
           'PARAMETER["Auxiliary_Sphere_Type",0.0],UNIT["Meter",1.0]]')


# =====================================================================
# 2. THE 3D SHAPE: every CAD part -> a mesh in metres, z up
# =====================================================================
orion = runpy.run_path(CAD_SCRIPT)["orion"]
scene = trimesh.Scene()
for child in orion.children:
    solid = child.obj.val() if hasattr(child.obj, "val") else child.obj
    vertices, triangles = solid.moved(child.loc).tessellate(2, 0.3)
    points = np.array([[p.x, -p.z, p.y] for p in vertices]) / 1000        # mm -> m, z up
    r, g, b, a = child.color.toTuple() if child.color else (0.8, 0.8, 0.8, 1)
    mesh = trimesh.Trimesh(vertices=points, faces=np.array(triangles), process=False)
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=[int(255 * r), int(255 * g), int(255 * b), int(255 * a)])
    name = re.sub(r"[^A-Za-z0-9_-]", "_", child.name)
    mesh.export(os.path.join(PARTS, name + ".glb"))                       # one file per part
    mesh.export(os.path.join(PARTS_OBJ, name + ".obj"))
    scene.add_geometry(mesh, node_name=name, geom_name=name)
scene.export(os.path.join(OUT, "orion.glb"))                              # the whole spacecraft
scene.export(os.path.join(OUT, "orion.obj"))
print("Parts:", len(orion.children), "->", PARTS)


# =====================================================================
# 3. THE VOXELS -> netCDF (dimensions z, y, x as ArcGIS wants them)
# =====================================================================
grid = np.load(VOXELS_IN, allow_pickle=True)
x, y_up, z_depth = grid["x"], grid["y"], grid["z"]          # 01_anatomy axes: y = spacecraft axis
names = list(grid["material_names"])

# which room every cube belongs to (0 = none), for filtering in ArcGIS
with open(ROOMS_IN) as f:
    rooms = json.load(f)
X, Y, Z = np.meshgrid(x, y_up, z_depth, indexing="ij")
room_id = np.zeros(X.shape, dtype=np.int16)
for k, (name, (cx, cy, cz, w, h, d)) in enumerate(rooms.items(), start=1):
    inside = (np.abs(X - cx) <= w / 2) & (np.abs(Y - cy) <= h / 2) & (np.abs(Z - cz) <= d / 2)
    room_id[inside & (room_id == 0)] = k

# reorder (x, up, depth) -> (up, -depth, x): ArcGIS z = up, y = -depth (increasing), x = x
variables = {}
for key, data in [("density", grid["density"]), ("material", grid["material"]),
                  ("al_equiv", grid["al_equiv"]), ("room", room_id)]:
    variables[key] = np.transpose(data, (1, 2, 0))[:, ::-1, :]

# ArcGIS reads the coordinate system from the "esri_pe_string" attribute of every variable
ds = xr.Dataset(
    {
        "density": (("z", "y", "x"), variables["density"].astype(np.float32),
                    {"long_name": "density", "units": "g/cm3", "esri_pe_string": CRS_WKT}),
        "material": (("z", "y", "x"), variables["material"].astype(np.float32),
                     {"long_name": "material id: " + "; ".join(f"{i} = {n}" for i, n in enumerate(names)),
                      "esri_pe_string": CRS_WKT}),
        "al_equiv": (("z", "y", "x"), variables["al_equiv"].astype(np.float32),
                     {"long_name": "aluminium equivalence (proton stopping per g/cm2 vs aluminium)",
                      "esri_pe_string": CRS_WKT}),
        "room": (("z", "y", "x"), variables["room"].astype(np.float32),
                 {"long_name": "room id: 0 = none; " + "; ".join(f"{k} = {n}" for k, n in enumerate(rooms, start=1)),
                  "esri_pe_string": CRS_WKT}),
    },
    coords={
        "x": ("x", x.astype(np.float64), {"units": "m", "axis": "X", "standard_name": "projection_x_coordinate"}),
        "y": ("y", (-z_depth[::-1]).astype(np.float64), {"units": "m", "axis": "Y", "standard_name": "projection_y_coordinate"}),
        "z": ("z", y_up.astype(np.float64), {"units": "m", "axis": "Z", "positive": "up", "standard_name": "height"}),
    },
    attrs={"title": "Orion anatomy (voxels 5 cm)", "Conventions": "CF-1.6", "esri_pe_string": CRS_WKT,
           "source": "shielding/01_anatomy.py (team assumptions, checked against Orion masses)"},
)
# no NaN "no data" values: ArcGIS warns about them
encoding = {v: {"zlib": True, "complevel": 4, "_FillValue": -9999.0} for v in ["density", "material", "al_equiv", "room"]}
encoding.update({c: {"_FillValue": None} for c in ["x", "y", "z"]})
ds.to_netcdf(os.path.join(OUT, "orion_voxels.nc"), encoding=encoding, format="NETCDF4")
print("Voxels:", dict(ds.sizes), "->", os.path.join(OUT, "orion_voxels.nc"))


# =====================================================================
# 4. PLAN B: the voxels as 3D points (every 10 cm, only cubes with something in them)
# =====================================================================
points = ds.isel(x=slice(0, None, 2), y=slice(0, None, 2), z=slice(0, None, 2)).to_dataframe().reset_index()
points = points[points["material"] > 0][["x", "y", "z", "material", "density", "al_equiv", "room"]]
points["material_name"] = points["material"].astype(int).map(dict(enumerate(names)))
points.round(4).to_csv(os.path.join(OUT, "orion_points.csv"), index=False)
print("Points:", len(points), "->", os.path.join(OUT, "orion_points.csv"))
