# Shielding

Converts forecast fluence per energy band (from `forecast/`) into a dose estimate for each Orion spacecraft room and selects the safest room.

Work in progress; per-room shielding factors are assumptions and are not validated flight-planning data.

## Destel/

Dose measured inside the International Space Station by the DOSTEL dosimeter (NASA OSDR RadLab), used as a reference for dose behind spacecraft walls, including the September 2017 storm.

- `dostel.py` downloads the NASA RadLab DOSTEL time series to `iss_dostel_2017-09.csv`.
- `data_processing.py` inspects the full download, or the included sample if the full download is not present.
- `dostel_2017-09-01_20.csv` is the included September 1–19, 2017 sample.
- `plot_dostel.py` creates `plot1_event.png` through `plot4_regions.png` from the full download or sample. The included PNGs are supplied example plots; rerunning the script replaces them using whichever CSV is selected.

Run from the project root:

```bash
python -m shielding.Destel.data_processing
python -m shielding.Destel.plot_dostel
python -m shielding.Destel.dostel
```

The full download makes one request per month over the configured period and can take several minutes. The included sample can be used to run the plots without downloading the full series, but it covers only September 1–19, 2017; the multi-year plots require the full download.
