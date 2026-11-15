# =====================================================================
# orion_cad.py
# A CAD model (solid bodies) of Orion, with the same geometry as
# Orion/main.py and shielding/01_anatomy.py.
#
# Output:  shielding/cad/orion.step   solids with names and colours
#                                     (SolidWorks, Fusion 360, FreeCAD, CATIA...)
#          shielding/cad/orion.stl    one mesh (quick view, 3D printing)
#
# Units: millimetres.  Axes: Y along the spacecraft (up), like Orion/main.py.
#        y = 0 bottom of the service module, crew module from y = 4700.
# Outer shapes: public NASA / ESA figures. Interior: schematic (no public CAD).
#
# Needs:  pip install cadquery
# Run:    python shielding/cad/orion_cad.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import math
import os

import cadquery as cq

FOLDER = os.path.dirname(os.path.abspath(__file__))
STEP_FILE = os.path.join(FOLDER, "orion.step")
STL_FILE = os.path.join(FOLDER, "orion.stl")

CM_Y = 4700                      # crew module starts here (mm)
SKIN = 30                        # thickness of the outer skins (mm), for the solid bodies
Y_AXIS = ((0, 0, 0), (0, 1, 0))  # revolve around the Y axis

orion = cq.Assembly(name="Orion")
grey = cq.Color(0.75, 0.77, 0.78, 1)
white = cq.Color(0.93, 0.93, 0.93, 1)
gold = cq.Color(0.78, 0.60, 0.24, 1)
dark = cq.Color(0.30, 0.33, 0.35, 1)
blue = cq.Color(0.15, 0.25, 0.55, 1)
room_color = cq.Color(0.0, 1.0, 0.4, 0.25)     # see-through rooms


# =====================================================================
# 2. SERVICE MODULE (ESM): cylinder 4100 mm wide, 4000 mm tall
# =====================================================================
# outer skin: a ring profile revolved around the axis
esm = (cq.Workplane("XY").polyline([(2050 - SKIN, 0), (2050, 0), (2050, 4000), (2050 - SKIN, 4000)])
       .close().revolve(360, *Y_AXIS))
bottom = cq.Workplane("XZ").circle(2050).extrude(-SKIN)            # bottom plate (y 0 .. 30)
top = cq.Workplane("XZ", origin=(0, 4000 - SKIN, 0)).circle(2050).extrude(-SKIN)
orion.add(esm.union(bottom).union(top), name="Service Module", color=white)

# main engine bell (profile from Orion/main.py)
bell_profile = [(100, 250), (160, -50), (270, -450), (380, -850), (440, -1100),
                (420, -1100), (350, -850), (240, -450), (120, -50), (80, 250)]
bell = cq.Workplane("XY").polyline(bell_profile).close().revolve(360, *Y_AXIS)
orion.add(bell, name="Main Engine", color=dark)

# 8 auxiliary engines around the main one
for k in range(8):
    angle = k * 2 * math.pi / 8
    aux = (cq.Workplane("XZ", origin=(1200 * math.cos(angle), 50, 1200 * math.sin(angle)))
           .circle(90).workplane(offset=250).circle(40).loft())
    orion.add(aux, name=f"Aux Engine {k + 1}", color=dark)

# 4 propellant tanks (2 MON + 2 MMH): cylinder 1100 mm wide, 1800 mm tall, flat domes
# profile of half a tank: bottom dome (ellipse 550 x 220), straight wall, top dome
tank_profile = ([(550 * math.sin(math.radians(a)), 1300 - 220 * math.cos(math.radians(a))) for a in range(0, 91, 10)]
                + [(550 * math.cos(math.radians(a)), 3100 + 220 * math.sin(math.radians(a))) for a in range(0, 91, 10)])
for k, (tx, tz) in enumerate([(950, 950), (-950, 950), (950, -950), (-950, -950)]):
    tank = cq.Workplane("XY").polyline(tank_profile).close().revolve(360, *Y_AXIS).translate((tx, 0, tz))
    orion.add(tank, name=f"Propellant Tank {k + 1}",
              color=cq.Color(0.43, 0.62, 0.71, 1) if tz > 0 else cq.Color(0.71, 0.54, 0.43, 1))

# water / oxygen / nitrogen tanks (spheres)
for k in range(3):
    angle = k * 2 * math.pi / 3
    sphere = cq.Workplane("XY").sphere(220).translate((1300 * math.cos(angle), 3350, 1300 * math.sin(angle)))
    orion.add(sphere, name=f"Life-support Tank {k + 1}", color=grey)
orion.add(cq.Workplane("XY").sphere(200).translate((0, 3350, 0)), name="Life-support Tank 4", color=grey)

# 4 solar wings x 3 panels (each panel 2410 x 1900 x 35 mm), at y = 1250
for w in range(4):
    angle = math.pi / 4 + w * math.pi / 2
    for s in range(3):
        px = 2200 + (s + 0.5) * 2460 + s * 50
        panel = (cq.Workplane("XY").box(2410, 1900, 35).translate((px, 1250, 0))
                 .rotate((0, 0, 0), (0, 1, 0), math.degrees(angle)))
        orion.add(panel, name=f"Solar Wing {w + 1} Panel {s + 1}", color=blue)

# 6 RCS pods on the service module
for k in range(6):
    angle = k * 2 * math.pi / 6
    pod = (cq.Workplane("XY").box(200, 250, 200).translate((2150, 3400, 0))
           .rotate((0, 0, 0), (0, 1, 0), math.degrees(angle)))
    orion.add(pod, name=f"RCS Pod {k + 1}", color=grey)


# =====================================================================
# 3. CREW MODULE ADAPTER (y 4000 .. 4720)
# =====================================================================
cma_outer = [(2050, 4000), (2050, 4120), (2280, 4520), (2120, 4720)]
cma_inner = [(r - SKIN, y) for r, y in reversed(cma_outer)]
cma = cq.Workplane("XY").polyline(cma_outer + cma_inner).close().revolve(360, *Y_AXIS)
orion.add(cma, name="Crew Module Adapter", color=gold)


# =====================================================================
# 4. CREW MODULE (local height h, from Orion/main.py, + CM_Y)
# =====================================================================
# heat shield: spherical cap (radius 6 m), 80 mm thick, 5020 mm wide
cap = [(2510 * i / 28, CM_Y + 1000 * (6 - math.sqrt(36 - (2.51 * i / 28) ** 2))) for i in range(29)]
heat_profile = cap + [(r, y + 80) for r, y in reversed(cap)]
heat_shield = cq.Workplane("XY").polyline(heat_profile).close().revolve(360, *Y_AXIS)
orion.add(heat_shield, name="Heat Shield (Avcoat)", color=cq.Color(0.45, 0.33, 0.22, 1))

# backshell + pressure vessel: the 57.5 deg cone, 100 mm thick (tiles + panels + Al-Li)
back_outer = [(2510, 550), (2540, 660), (2480, 760), (1374, 2400)]
back_profile = ([(r, CM_Y + h) for r, h in back_outer]
                + [(r - 100, CM_Y + h) for r, h in reversed(back_outer)])
backshell = cq.Workplane("XY").polyline(back_profile).close().revolve(360, *Y_AXIS)
orion.add(backshell, name="Backshell + Pressure Vessel", color=cq.Color(0.85, 0.85, 0.85, 1))

# forward bay cover (top of the cone, parachutes inside) and docking ring
fwd_outer = [(1374, 2400), (780, 3280), (700, 3300)]
fwd_profile = ([(r, CM_Y + h) for r, h in fwd_outer]
               + [(r - SKIN, CM_Y + h - SKIN) for r, h in reversed(fwd_outer)])
forward_bay = cq.Workplane("XY").polyline(fwd_profile).close().revolve(360, *Y_AXIS)
orion.add(forward_bay, name="Forward Bay Cover", color=grey)
docking = cq.Workplane("XZ", origin=(0, CM_Y + 3300, 0)).circle(690).circle(550).extrude(-120)
orion.add(docking, name="Docking Ring", color=grey)

# parachute canisters (3 main) and docking tunnel inside the forward bay
for k in range(3):
    angle = k * 2 * math.pi / 3
    can = cq.Workplane("XZ", origin=(480 * math.cos(angle), 7225, 480 * math.sin(angle))).circle(200).extrude(-650)
    orion.add(can, name=f"Main Parachute {k + 1}", color=cq.Color(0.85, 0.33, 0.24, 1))
tunnel = cq.Workplane("XZ", origin=(0, 7100, 0)).circle(360).circle(330).extrude(-900)
orion.add(tunnel, name="Docking Tunnel", color=grey)


# =====================================================================
# 5. INTERIOR: rooms (see-through boxes) and the storm shelter
#    centre (x, y, z) and size (width, height, depth) in metres, from Orion/main.py
# =====================================================================
ROOMS = {
    "Cockpit": [-0.6, 6.75, -1.3, 1.9, 0.8, 0.5],
    "Crew Seats": [-0.6, 6.05, -0.3, 1.6, 0.8, 2.1],
    "Galley": [1.35, 6.4, 0.95, 0.55, 0.65, 0.75],
    "Exercise": [1.4, 6.1, -0.1, 0.65, 0.55, 0.95],
    "Hygiene Bay": [0.08, 6.25, 1.3, 0.68, 0.8, 0.68],
    "Storm Shelter": [0.55, 6.3, 0.0, 0.8, 1.1, 2.1],
    "Sleeping Area": [0.0, 7.0, 0.0, 2.0, 0.5, 1.7],
    "Lower Equipment Bay": [0.0, 5.55, 0.0, 3.2, 0.65, 3.2],
}
cabin_inside = (cq.Workplane("XY").polyline([(0, CM_Y + 550)] + [(r - 100, CM_Y + h) for r, h in back_outer]
                                            + [(0, CM_Y + 2400)]).close().revolve(360, *Y_AXIS))
for name, (cx, cy, cz, w, hgt, d) in ROOMS.items():
    room = cq.Workplane("XY").box(w * 1000, hgt * 1000, d * 1000).translate((cx * 1000, cy * 1000, cz * 1000))
    room = room.intersect(cabin_inside)                 # cut the corners that stick out of the cone
    orion.add(room, name="Room - " + name, color=room_color)

# storm shelter: the two lockers (600 x 900 x 900 mm)
for k, lz in enumerate([-500, 500]):
    locker = cq.Workplane("XY").box(600, 900, 900).translate((550, 6300, lz)).faces(">X").shell(-20)
    orion.add(locker, name=f"Shelter Locker {k + 1}", color=cq.Color(0.44, 0.55, 0.61, 1))

# lower equipment bay: 8 avionics boxes in a ring
for k in range(8):
    angle = k * math.pi / 4 + 0.2
    avionics = (cq.Workplane("XY").box(500, 400, 320).translate((1450, 5550, 0))
                .rotate((0, 0, 0), (0, 1, 0), -math.degrees(angle)))
    orion.add(avionics, name=f"Avionics Box {k + 1}", color=dark)


# =====================================================================
# 6. SAVE
# =====================================================================
orion.export(STEP_FILE)
cq.exporters.export(orion.toCompound(), STL_FILE, tolerance=5, angularTolerance=0.2)
print("Parts:", len(orion.children))
print("Saved:", STEP_FILE)
print("Saved:", STL_FILE)
