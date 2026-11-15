# =====================================================================
# style_floor_plans.py  -  run INSIDE ArcGIS Pro (Analysis -> Python -> Python Window):
#
#   exec(open(r"C:\Creations\python\hackathlon\Radiation-ML-\gis\style_floor_plans.py").read())
#
# For every floor-plan layer of the active map (the room_doses_floors.gpkg layers):
#   - colours the rooms by dose level (SAFE green ... HIGH red)
#   - hull and equipment: no fill, grey outline
#   - labels on the rooms: name, dose (mSv) and % of the limit
#   - shows only the crew deck (floor 3); tick the others in Contents to see them
# =====================================================================
import arcpy

COLORS = {"SAFE": [42, 157, 85, 70], "LOW": [139, 191, 63, 70],
          "MEDIUM": [233, 162, 59, 70], "HIGH": [214, 69, 65, 70]}      # RGB + transparency (0-100)

aprx = arcpy.mp.ArcGISProject("CURRENT")
m = aprx.activeMap
for lyr in m.listLayers():
    if "floor" not in lyr.name or not lyr.isFeatureLayer:
        continue

    # colours by level
    sym = lyr.symbology
    sym.updateRenderer("UniqueValueRenderer")
    sym.renderer.fields = ["level"]
    for group in sym.renderer.groups:
        for item in group.items:
            value = str(item.values[0][0])
            if value in COLORS:
                item.symbol.color = {"RGB": COLORS[value]}
                item.symbol.outlineColor = {"RGB": [0, 0, 0, 100]}
                item.label = value
            else:                                                   # hull, equipment (no dose)
                item.symbol.color = {"RGB": [0, 0, 0, 0]}
                item.symbol.outlineColor = {"RGB": [90, 90, 90, 100]}
                item.label = "hull / equipment"
    lyr.symbology = sym

    # labels on the rooms only
    label = lyr.listLabelClasses()[0]
    label.expressionEngine = "Arcade"
    label.expression = ('$feature.name + TextFormatting.NewLine + Round($feature.dose_msv, 1) + " mSv ("'
                        ' + Round($feature.pct_limit, 0) + "%)"')
    label.SQLQuery = "type = 'room'"
    label.visible = True
    lyr.showLabels = True

    # only the crew deck visible at first
    lyr.visible = "floor3" in lyr.name
    print("styled:", lyr.name)

print("Done. Tick the other floors in Contents to see them.")
