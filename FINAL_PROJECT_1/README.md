# Project ICHOR

From this directory, install dependencies and start the app:

```bash
pip install -r requirements.txt
python setup_db.py  # builds database/nasaspacechallenge.db from real open data
streamlit run main.py
```

`import_osdr_cbc.py <OSD-569 CBC csv>` is optional; that script is not included in this repository.

In the Orion 3D panel, press **ML FORECAST** to fetch current NOAA proton-flux data, run one forecast, and apply it to the 3D radiation map. Use **APP VALUE** to restore the dashboard dose.

In the astronaut radiation chooser, use **NASA organ-dose reference** to overlay the supplied NASA study values on the 3D body. Hover over cyan diamonds for organ values; select scenarios separately because their units and exposure conditions differ.

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub and choose **Create app**.
3. Select this repository and the `main` branch.
4. In the advanced settings, set **App directory** to `FINAL PROJECT 1` and **Main file path** to `main.py`.
5. Deploy. Streamlit installs the dependencies from this directory's `requirements.txt`.

The app's bundled SQLite database is local to the hosted app; database changes are not durable across app rebuilds or restarts.