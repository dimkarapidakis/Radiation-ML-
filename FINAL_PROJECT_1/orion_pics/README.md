   # Project ICHOR
   pip install -r requirements.txt
python setup_db.py                      # builds database/nasaspacechallenge.db from REAL open data
python import_osdr_cbc.py <OSD-569 CBC csv>   # optional but recommended: real Inspiration4 blood counts
streamlit run main.py

In the Orion 3D panel, press **ML FORECAST** to fetch current NOAA proton-flux data, run one forecast, and apply it to the 3D radiation map. Use **APP VALUE** to restore the dashboard dose.

In the astronaut radiation chooser, use **NASA organ-dose reference** to overlay the supplied NASA study values on the 3D body. Hover over cyan diamonds for organ values; select scenarios separately because their units and exposure conditions differ.