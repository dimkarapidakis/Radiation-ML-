# =====================================================================
# floors_3d.py
# 3D "exploded" view of Orion: the CAD model of orion_cad.py is cut into the
# same 4 floors as floor_plans.py and every floor is lifted a bit, so you can
# see inside each one.
#
# Output:  shielding/cad/orion_floors_3d.step   solids (AutoCAD: IMPORT, then SAVEAS .dwg)
#          shielding/cad/orion_floors_3d.dxf    meshes, one layer per floor and part (AutoCAD: OPEN)
#          shielding/cad/orion_floors_3d.html   interactive 3D in the browser (rotate, zoom, hide parts)
#
# Needs:  pip install cadquery ezdxf plotly
# Run:    python shielding/cad/floors_3d.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import os
import re
import runpy

import cadquery as cq
import ezdxf
import plotly.graph_objects as go

FOLDER = os.path.dirname(os.path.abspath(__file__))
STEP_FILE = os.path.join(FOLDER, "orion_floors_3d.step")
DXF_FILE = os.path.join(FOLDER, "orion_floors_3d.dxf")
HTML_FILE = os.path.join(FOLDER, "orion_floors_3d.html")

# the same floors as floor_plans.py (mm), and how much each floor is lifted
FLOORS = [
    ("Floor 1 - Service Module", -1200, 4000),        # from the engine bell to the top of the module
    ("Floor 2 - Lower Equipment Bay", 4000, 5850),     # adapter, heat shield, equipment bay
    ("Floor 3 - Crew Deck", 5850, 6800),
    ("Floor 4 - Upper Cabin", 6800, 8200),             # sleeping area, forward bay, docking ring
]
LIFT = 1500                                            # mm between the floors in the exploded view
SKIP = ("Solar Wing",)                                 # wings left out: they hide the inside

# the full CAD model from orion_cad.py
orion = runpy.run_path(os.path.join(FOLDER, "orion_cad.py"))["orion"]


# =====================================================================
# 2. CUT EVERY PART INTO THE FLOORS AND LIFT THEM
# =====================================================================
exploded = cq.Assembly(name="Orion floors")
pieces = []                                            # (floor, part name, solid, colour) for DXF / HTML
for f, (floor, bottom, top) in enumerate(FLOORS):
    slab = cq.Workplane("XZ", origin=(0, top, 0)).rect(30000, 30000).extrude(top - bottom).val()
    for child in orion.children:
        if child.name.startswith(SKIP):
            continue
        solid = child.obj.val() if hasattr(child.obj, "val") else child.obj
        part = solid.moved(child.loc).intersect(slab)
        if part.Volume() < 1:                          # this part is not on this floor
            continue
        part = part.translate(cq.Vector(0, f * LIFT, 0))
        color = child.color if child.color else cq.Color(0.8, 0.8, 0.8, 1)
        exploded.add(part, name=f"{floor} | {child.name}", color=color)
        pieces.append((floor, child.name, part, color))
print("Pieces:", len(pieces))


# =====================================================================
# 3. SAVE: STEP (solids) and DXF (meshes, AutoCAD Z up)
# =====================================================================
exploded.export(STEP_FILE)

doc = ezdxf.new("R2018")
doc.header["$INSUNITS"] = 4                            # millimetres
msp = doc.modelspace()
for floor, name, part, color in pieces:
    layer = re.sub(r"[^A-Za-z0-9 _-]", "", f"{floor[:7]} {name}")[:60]
    if layer not in doc.layers:
        r, g, b, a = color.toTuple()
        new_layer = doc.layers.add(layer)
        new_layer.rgb = (int(255 * r), int(255 * g), int(255 * b))
        if a < 1:
            new_layer.transparency = 1 - a
    vertices, triangles = part.tessellate(2, 0.3)
    mesh = msp.add_mesh(dxfattribs={"layer": layer})
    with mesh.edit_data() as data:
        data.vertices = [(p.x, -p.z, p.y) for p in vertices]
        data.faces = [tuple(t) for t in triangles]
doc.saveas(DXF_FILE)


# =====================================================================
# 4. INTERACTIVE 3D (HTML): one trace per piece, click the legend to hide
# =====================================================================
fig = go.Figure()
for floor, name, part, color in pieces:
    vertices, triangles = part.tessellate(5, 0.5)
    r, g, b, a = color.toTuple()
    fig.add_trace(go.Mesh3d(
        x=[p.x / 1000 for p in vertices], y=[-p.z / 1000 for p in vertices], z=[p.y / 1000 for p in vertices],
        i=[t[0] for t in triangles], j=[t[1] for t in triangles], k=[t[2] for t in triangles],
        color=f"rgb({int(255 * r)},{int(255 * g)},{int(255 * b)})", opacity=a if a < 1 else 1.0,
        flatshading=True, name=name, legendgroup=floor, legendgrouptitle_text=floor, showlegend=True,
        hovertext=f"{floor}<br>{name}", hoverinfo="text"))
fig.update_layout(
    title="ORION - 4 floors (exploded view, schematic interior)",
    scene=dict(aspectmode="data", xaxis_title="x (m)", yaxis_title="z (m)", zaxis_title="y (m)",
               camera=dict(eye=dict(x=1.5, y=1.5, z=1.5), center=dict(x=0, y=0, z=-0.1))),
    legend=dict(groupclick="toggleitem", font=dict(size=10)),
    margin=dict(l=0, r=0, t=40, b=0))
fig.write_html(HTML_FILE, include_plotlyjs=True)          # works offline

print("Saved:", STEP_FILE)
print("Saved:", DXF_FILE)
print("Saved:", HTML_FILE)
