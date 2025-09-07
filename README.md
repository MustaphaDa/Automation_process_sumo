# Automated SUMO + GTFS Workflow (Windows)

End-to-end pipeline to measure how private traffic affects public transport delay.

## Setup
- Windows + PowerShell
- SUMO installed (`SUMO_HOME` set)
- Python 3 or Python launcher `py`

## Configure
Edit `config.json`:
```
{
  "cityName": "Pécs",
  "gtfsPath": "gtfs_pea.zip",
  "simDate": "20210916",
  "transportModes": "bus",
  "maxJobs": 7,
  "centerX": 9619.87,
  "centerY": 10540.2,
  "simsPerValue": 10
}
```

## Run
PowerShell:
```
powershell -ExecutionPolicy Bypass -File .\Script1.ps1
```
- Skips steps if outputs already exist
- Parallelized by `maxJobs`

## Outputs
- `outputs/osm/` – `<City>.osm`
- `outputs/net/` – `<City>_full.net.xml`, `osm_ptstops.xml`, `osm_ptlines.xml`
- `outputs/zones/` – `zone1.xml`, `zone2.xml`, `zone3.xml`, `zones.taz.xml`
- `outputs/gtfs/` – `pt_vtypes.xml`, `gtfs_publictransport.rou.xml`, `gtfs_publictransport.add.xml`
- `outputs/sim/` per run:
  - `stop_events_baseline_<sim>.xml` (public-only)
  - `stop_events_<value>_<sim>.xml` (mixed)
  - `4_<value>_<sim>_<City>_sim_output.xml` (tripinfo)
  - `log_<value>_<sim>.txt`, `od_variants/`
- `outputs/analysis/` – `pt_delay.xlsx`, plots

## Analysis tools
- Build Excel from sim files:
```
py -3 export_pt_delay_excel.py --simdir outputs\sim --sims 10 --out outputs\analysis\pt_delay.xlsx
```
- Rebuild only the summary sheet:
```
py -3 rebuild_summary_from_excel.py --excel outputs\analysis\pt_delay.xlsx
```
- Plot mean delay vs traffic (and heat curve):
```
py -3 plot_pt_delay.py --excel outputs\analysis\pt_delay.xlsx \
  --out outputs\analysis\pt_delay.png --out-heat outputs\analysis\pt_delay_heat.png
```

## Delay method (new)
- SUMO `--stop-output` gives per-stop `delay` (s): actual_departure − scheduled_departure (GTFS).
- For each traffic point and seed:
  - Run Baseline (public-only) and Mixed (public+private)
  - Align stop events; compute Δdelay = mixed − baseline
- Aggregate across all stops and 10 seeds: mean/median/p90/min/max → Excel summary

## Tips
- Use `py` launcher if needed:
```
$env:PYTHON = "py"
```
- To re-run only sims, delete specific files under `outputs/sim/`.
- Consider zipping `outputs/sim/` or Git LFS to keep large results.
