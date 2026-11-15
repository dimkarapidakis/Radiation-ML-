# =====================================================================
# style_floor1.py  -  run INSIDE ArcGIS Pro (Python Window):
#
#   exec(open(r"C:\Creations\python\hackathlon\Radiation-ML-\gis\style_floor1.py").read())
#
# Floor 1 (Service Module): shows only this floor, colours the parts by name
# (MON / MMH propellant tanks, water / oxygen tanks, hull) and labels them.
# =====================================================================
import arcpy

COLORS = {"MON Tank": [111, 159, 181, 80], "MMH Tank": [181, 138, 111, 80],
          "Water/O2 Tank": [42, 120, 214, 60], "Hull wall": [150, 150, 150, 100]}

aprx = arcpy.mp.ArcGISProject("CURRENT")
m = aprx.listMaps("Map1")[0]
floor1 = None
for lyr in m.listLayers():
    if lyr.isFeatureLayer and "floor" in lyr.name:
        lyr.visible = "floor1" in lyr.name
        if "floor1" in lyr.name:
            floor1 = lyr

sym = floor1.symbology
sym.updateRenderer("UniqueValueRenderer")
sym.renderer.fields = ["name"]
for group in sym.renderer.groups:
    for item in group.items:
        value = str(item.values[0][0])
        item.symbol.color = {"RGB": COLORS.get(value, [220, 220, 220, 40])}
        item.symbol.outlineColor = {"RGB": [0, 0, 0, 100]}
        item.label = value
floor1.symbology = sym

label = floor1.listLabelClasses()[0]
label.expressionEngine = "Arcade"
label.expression = '$feature.name + TextFormatting.NewLine + Round($feature.area_m2, 2) + " m2"'
label.SQLQuery = "type = 'equipment'"
label.visible = True
floor1.showLabels = True
print("Floor 1 styled:", floor1.name)
