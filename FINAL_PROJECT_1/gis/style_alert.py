# =====================================================================
# style_alert.py  -  run INSIDE ArcGIS Pro (Python Window):
#
#   exec(open(r"C:\Creations\python\hackathlon\Radiation-ML-\gis\style_alert.py").read())
#
# Adds warning/data/alert_map.gpkg to a new map "Alert" and styles it:
#   rooms coloured by worst-case dose level, the room to go to with a thick red outline,
#   the route as a red line, labels with the dose, title = the alert level.
# =====================================================================
import os

import arcpy

GPKG = r"C:\Creations\python\hackathlon\Radiation-ML-\warning\data\alert_map.gpkg"
COLORS = {"SAFE": [42, 157, 85, 70], "LOW": [139, 191, 63, 70],
          "MEDIUM": [233, 162, 59, 70], "HIGH": [214, 69, 65, 70], "NO FORECAST": [200, 200, 200, 50]}

aprx = arcpy.mp.ArcGISProject("CURRENT")
old = [m for m in aprx.listMaps() if m.name == "Alert"]
for m in old:
    aprx.deleteItem(m)
m = aprx.createMap("Alert", "MAP")
m.spatialReference = arcpy.SpatialReference(3857)

hull = m.addDataFromPath(os.path.join(GPKG, "main.alert_hull"))
rooms = m.addDataFromPath(os.path.join(GPKG, "main.alert_rooms"))
route_path = os.path.join(GPKG, "main.alert_route")
route = m.addDataFromPath(route_path) if arcpy.Exists(route_path) else None

# hull: grey ring
sym = hull.symbology
sym.renderer.symbol.color = {"RGB": [190, 190, 190, 60]}
sym.renderer.symbol.outlineColor = {"RGB": [80, 80, 80, 100]}
hull.symbology = sym
# (the alert map has only the crew-module floors 2, 3, 4, side by side)

# rooms: colour by level, thick red outline for the room to go to
sym = rooms.symbology
sym.updateRenderer("UniqueValueRenderer")
sym.renderer.fields = ["room_level"]
for group in sym.renderer.groups:
    for item in group.items:
        value = str(item.values[0][0])
        item.symbol.color = {"RGB": COLORS.get(value, [200, 200, 200, 50])}
        item.symbol.outlineColor = {"RGB": [0, 0, 0, 100]}
rooms.symbology = sym

target = m.addDataFromPath(os.path.join(GPKG, "main.alert_rooms"))
target.name = "go here"
target.definitionQuery = "go_here = 1"
sym = target.symbology
sym.renderer.symbol.color = {"RGB": [0, 0, 0, 0]}
sym.renderer.symbol.outlineColor = {"RGB": [214, 0, 0, 100]}
sym.renderer.symbol.outlineWidth = 4
target.symbology = sym

label = rooms.listLabelClasses()[0]
label.expressionEngine = "Arcade"
label.expression = ('$feature.name + " (floor " + $feature.floor + ")" + TextFormatting.NewLine'
                    ' + Round($feature.dose_worst_msv, 1) + " mSv worst case"')
label.visible = True
rooms.showLabels = True

if route:
    sym = route.symbology
    sym.renderer.symbol.color = {"RGB": [214, 0, 0, 100]}
    sym.renderer.symbol.width = 4
    route.symbology = sym

level = [r[0] for r in arcpy.da.SearchCursor(os.path.join(GPKG, "main.alert_rooms"), ["alert_level"])][0]
rooms.name = "rooms - " + level
aprx.save()
print("Alert map ready:", level)
