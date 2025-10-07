#!/usr/bin/env python3
"""
Generate a 2x2 figure with delay measurements for four cities.

Each subplot shows two curves:
- Trip info method (from pt_delay_old_method.xlsx or pt_delay_tripinfo.xlsx)
- Stop info method (from pt_delay.xlsx or pt_delay_analysis.xlsx)

Data is read from the 'summary' sheet:
- X-axis: 'value' column multiplied by 2
- Y-axis: mean column auto-detected: 'mean_delay_s' or fallback 'mean_delta_s',
  plotted on a log scale

Paths are preconfigured for Debrecen, Pécs, Szeged, and Brest based on the user's description.
The resulting PNG is saved under outputs/analysis/four_city_delay_comparison.png.
"""

import os
from typing import Tuple

import numpy as np
import pandas as pd


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def _detect_mean_column(df: pd.DataFrame) -> str:
    if "mean_delay_s" in df.columns:
        return "mean_delay_s"
    if "mean_delta_s" in df.columns:
        return "mean_delta_s"
    raise SystemExit("Neither 'mean_delay_s' nor 'mean_delta_s' present in summary sheet")


def read_summary_series(path: str, value_column: str = "value") -> Tuple[pd.Series, pd.Series]:
    df = pd.read_excel(path, sheet_name="summary")
    if value_column not in df.columns:
        raise SystemExit(f"Missing column '{value_column}' in summary of {path}")
    mean_column = _detect_mean_column(df)

    data = df[[value_column, mean_column]].copy()
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    data[mean_column] = pd.to_numeric(data[mean_column], errors="coerce")
    data = data.dropna(subset=[value_column, mean_column])
    data = data.sort_values(value_column)

    x_vals = data[value_column].astype(float) * 2.0
    y_vals = data[mean_column].astype(float)

    # Ensure log-scale safety: drop non-positive values
    y_vals = y_vals.where(y_vals > 0, np.nan)

    return x_vals, y_vals


def plot_city(ax, city_name: str, tripinfo_path: str, stopinfo_path: str) -> None:
    x_trip, y_trip = read_summary_series(tripinfo_path)
    x_stop, y_stop = read_summary_series(stopinfo_path)

    ax.plot(x_trip, y_trip, marker="o", linewidth=2, color="#1f77b4", label="Trip info method")
    ax.plot(x_stop, y_stop, marker="s", linewidth=2, color="#ff7f0e", label="Stop info method")

    ax.set_title(city_name)
    ax.set_yscale("log")
    ax.set_xscale("log")
    ax.grid(True, which="both", linestyle=":", alpha=0.6)
    ax.legend()


def main() -> None:
    # Absolute paths provided by the user
    debrecen_trip = r"C:\Users\RPC\Desktop\sumo_automation\debrecen_case_sumo_automation\outputs\analysis\pt_delay_old_method.xlsx"
    debrecen_stop = r"C:\Users\RPC\Desktop\sumo_automation\debrecen_case_sumo_automation\outputs\analysis\pt_delay.xlsx"

    pecs_trip = r"C:\Users\RPC\Desktop\sumo_automation\Pécs_sumo_automation\outputs\analysis\pt_delay_tripinfo.xlsx"
    pecs_stop = r"C:\Users\RPC\Desktop\sumo_automation\Pécs_sumo_automation\outputs\analysis\pt_delay.xlsx"

    szeged_trip = r"C:\Users\RPC\Desktop\sumo_automation\Szeged_sumo_automation\outputs\analysis\pt_delay_old_method.xlsx"
    szeged_stop = r"C:\Users\RPC\Desktop\sumo_automation\Szeged_sumo_automation\outputs\analysis\pt_delay.xlsx"

    brest_trip = r"C:\Users\RPC\Desktop\sumo_automation\brest_sumo_case\outputs\analysis\pt_delay_old_method.xlsx"
    brest_stop = r"C:\Users\RPC\Desktop\sumo_automation\brest_sumo_case\outputs\analysis\pt_delay_analysis.xlsx"

    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.ravel()

    plot_city(axes[0], "Debrecen", debrecen_trip, debrecen_stop)
    plot_city(axes[1], "Pécs", pecs_trip, pecs_stop)
    plot_city(axes[2], "Szeged", szeged_trip, szeged_stop)
    plot_city(axes[3], "Brest", brest_trip, brest_stop)

    for ax in axes:
        ax.set_xlabel("Traffic level (value × 2)")
        ax.set_ylabel("Delay (s)")

    fig.suptitle("Delay comparison: Trip info vs Stop info", fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])

    out_path = os.path.join("outputs", "analysis", "four_city_delay_comparison.png")
    ensure_parent(out_path)
    fig.savefig(out_path, dpi=150)
    print(f"Saved figure: {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()


