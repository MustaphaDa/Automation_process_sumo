#!/usr/bin/env python3
"""
Analyze critical traffic thresholds and post-threshold growth for delay curves
across cities and methods (Trip info vs Stop info).

Implements plan in critical.plan.md:
1) Load x = value*2, y = mean_delay_s|mean_delta_s per city/method
2) Compute local slope on log-log with rolling smoothing
3) Detect threshold where slope exceeds cutoff and persists
4) Fit exponential (log y ~ a + b * x) and power-law (log y ~ c + d * log x)
5) Select by AIC; export parameters and plots; test universality

Outputs:
- outputs/analysis/critical/threshold_and_growth.csv
- outputs/analysis/critical/<city>_<method>_fit.png
- outputs/analysis/critical/parameters_summary.png
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# --------------------------- IO helpers (from analysis.py) --------------------

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

    # Ensure positive for log scale
    mask = y_vals > 0
    return x_vals[mask].reset_index(drop=True), y_vals[mask].reset_index(drop=True)


# --------------------------- Analysis primitives -----------------------------

def rolling_median(a: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return a.copy()
    pad = window // 2
    padded = np.pad(a, (pad, pad), mode="edge")
    out = np.empty_like(a)
    for i in range(len(a)):
        out[i] = np.median(padded[i:i+window])
    return out


def compute_local_log_slope(x: np.ndarray, y: np.ndarray, smooth_window: int = 3) -> np.ndarray:
    lx = np.log10(x)
    ly = np.log10(y)
    # Central differences on sorted data
    dly = np.gradient(ly)
    dlx = np.gradient(lx)
    slope = np.divide(dly, dlx, out=np.zeros_like(dly), where=dlx != 0)
    return rolling_median(slope, smooth_window)


def detect_threshold(x: np.ndarray, y: np.ndarray, slope_cutoff: float = 1.0, persistence: int = 3,
                     smooth_window: int = 3) -> int:
    """Return index of first persistent growth point; fallback to 0 if not found."""
    s = compute_local_log_slope(x, y, smooth_window=smooth_window)
    above = s >= slope_cutoff
    count = 0
    for i, flag in enumerate(above):
        if flag:
            count += 1
            if count >= persistence:
                # threshold at first index of the persistent run
                return i - persistence + 1
        else:
            count = 0
    # Fallback: choose point with maximum slope
    return int(np.argmax(s)) if len(s) else 0


@dataclass
class FitResult:
    model: str  # 'exp' or 'pow'
    param: float  # b for exp (k), d for pow (alpha)
    intercept: float
    r2: float
    aic: float
    n: int


def fit_exponential(x: np.ndarray, y: np.ndarray) -> FitResult:
    # log(y) = a + b * x
    ly = np.log(y)
    X = np.vstack([np.ones_like(x), x]).T
    beta, *_ = np.linalg.lstsq(X, ly, rcond=None)
    yhat = X @ beta
    resid = ly - yhat
    rss = float(np.sum(resid ** 2))
    n = len(x)
    k = 2  # a, b
    aic = n * np.log(rss / n) + 2 * k if n > 2 else np.inf
    tss = float(np.sum((ly - ly.mean()) ** 2))
    r2 = 1 - rss / tss if tss > 0 else 0.0
    return FitResult("exp", param=float(beta[1]), intercept=float(beta[0]), r2=r2, aic=aic, n=n)


def fit_powerlaw(x: np.ndarray, y: np.ndarray) -> FitResult:
    # log(y) = c + d * log(x)
    lx = np.log(x)
    ly = np.log(y)
    X = np.vstack([np.ones_like(lx), lx]).T
    beta, *_ = np.linalg.lstsq(X, ly, rcond=None)
    yhat = X @ beta
    resid = ly - yhat
    rss = float(np.sum(resid ** 2))
    n = len(x)
    k = 2
    aic = n * np.log(rss / n) + 2 * k if n > 2 else np.inf
    tss = float(np.sum((ly - ly.mean()) ** 2))
    r2 = 1 - rss / tss if tss > 0 else 0.0
    return FitResult("pow", param=float(beta[1]), intercept=float(beta[0]), r2=r2, aic=aic, n=n)


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


# --------------------------- Study orchestration ------------------------------

def analyze_city_method(ax: plt.Axes, city: str, method: str, trip_path: str, stop_path: str,
                        slope_cutoff: float, persistence: int, smooth_window: int) -> Dict[str, object]:
    path = trip_path if method == "trip" else stop_path
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    x_series, y_series = read_summary_series(path)
    x = x_series.to_numpy()
    y = y_series.to_numpy()

    # Detect threshold
    idx_th = detect_threshold(x, y, slope_cutoff=slope_cutoff, persistence=persistence,
                              smooth_window=smooth_window)
    x_th = float(x[idx_th])
    y_th = float(y[idx_th])

    # Fit models on post-threshold region (include idx_th)
    x_fit = x[idx_th:]
    y_fit = y[idx_th:]
    fe = fit_exponential(x_fit, y_fit)
    fp = fit_powerlaw(x_fit, y_fit)
    best = fe if fe.aic < fp.aic else fp

    # Plot
    ax.plot(x, y, marker="o", linewidth=1.5, label=f"{city} - {method}")
    ax.axvline(x_th, color="red", linestyle="--", linewidth=1, label="threshold")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(True, which="both", linestyle=":", alpha=0.5)
    ax.set_title(f"{city} - {method}")
    ax.set_xlabel("Traffic level (value × 2)")
    ax.set_ylabel("Delay (s)")

    # Overlay fit
    xx = np.linspace(x_fit.min(), x_fit.max(), 200)
    if best.model == "exp":
        yy = np.exp(best.intercept + best.param * xx)
        ax.plot(xx, yy, color="black", linewidth=1.5, label=f"exp: k={best.param:.3g}")
    else:
        yy = np.exp(best.intercept) * (xx ** best.param)
        ax.plot(xx, yy, color="black", linewidth=1.5, label=f"pow: α={best.param:.3g}")
    ax.legend(fontsize=8)

    return {
        "city": city,
        "method": method,
        "x_th": x_th,
        "y_th": y_th,
        "model_selected": best.model,
        "param": best.param,
        "r2": best.r2,
        "aic_exp": fe.aic,
        "aic_pow": fp.aic,
    }


def main() -> None:
    # Paths as in analysis.py
    deb_trip = r"C:\Users\RPC\Desktop\sumo_automation\debrecen_case_sumo_automation\outputs\analysis\pt_delay_old_method.xlsx"
    deb_stop = r"C:\Users\RPC\Desktop\sumo_automation\debrecen_case_sumo_automation\outputs\analysis\pt_delay.xlsx"
    pecs_trip = r"C:\Users\RPC\Desktop\sumo_automation\Pécs_sumo_automation\outputs\analysis\pt_delay_tripinfo.xlsx"
    pecs_stop = r"C:\Users\RPC\Desktop\sumo_automation\Pécs_sumo_automation\outputs\analysis\pt_delay.xlsx"
    sz_trip = r"C:\Users\RPC\Desktop\sumo_automation\Szeged_sumo_automation\outputs\analysis\pt_delay_old_method.xlsx"
    sz_stop = r"C:\Users\RPC\Desktop\sumo_automation\Szeged_sumo_automation\outputs\analysis\pt_delay.xlsx"
    br_trip = r"C:\Users\RPC\Desktop\sumo_automation\brest_sumo_case\outputs\analysis\pt_delay_old_method.xlsx"
    br_stop = r"C:\Users\RPC\Desktop\sumo_automation\brest_sumo_case\outputs\analysis\pt_delay_analysis.xlsx"

    configs = [
        ("Debrecen", deb_trip, deb_stop),
        ("Pécs", pecs_trip, pecs_stop),
        ("Szeged", sz_trip, sz_stop),
        ("Brest", br_trip, br_stop),
    ]

    out_dir = os.path.join("outputs", "analysis", "critical")
    ensure_parent(os.path.join(out_dir, "dummy"))

    slope_cutoff = 1.0
    persistence = 3
    smooth_window = 3

    rows: List[Dict[str, object]] = []

    # Per city plots (Trip info only)
    for city, trip_path, stop_path in configs:
        fig, ax = plt.subplots(1, 1, figsize=(6, 4), dpi=150)
        res_trip = analyze_city_method(ax, city, "trip", trip_path, stop_path,
                                       slope_cutoff, persistence, smooth_window)
        rows.append(res_trip)
        fig.tight_layout()
        fpath = os.path.join(out_dir, f"{city.lower()}_fits.png")
        fig.savefig(fpath, bbox_inches="tight")
        plt.close(fig)

    # Table
    df = pd.DataFrame(rows)
    csv_path = os.path.join(out_dir, "threshold_and_growth.csv")
    df.to_csv(csv_path, index=False)

    # Human-readable thresholds summary (Trip info only)
    summary_lines = [
        "Trip info thresholds (x_th = traffic level × 2, y_th = delay at threshold):",
        "city,x_th,y_th,model,param(R),R2",
    ]
    for _, r in df.iterrows():
        if r.get("method") != "trip":
            continue
        summary_lines.append(
            f"{r['city']},{r['x_th']:.0f},{r['y_th']:.3g},{r['model_selected']},{r['param']:.4g},{r['r2']:.3f}"
        )
    txt_path = os.path.join(out_dir, "thresholds_tripinfo.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    # Universality check: compare selected parameter across cities per method
    summary_rows = []
    for method in ["trip"]:
        subset = df[df["method"] == method]
        if subset.empty:
            continue
        params = subset["param"].astype(float).to_numpy()
        mu = float(np.mean(params)) if len(params) else np.nan
        sigma = float(np.std(params, ddof=1)) if len(params) > 1 else np.nan
        cov = float(sigma / mu) if (mu and not np.isnan(mu) and not np.isnan(sigma)) else np.nan
        summary_rows.append({"method": method, "mean_param": mu, "std_param": sigma, "cov": cov})

    df_sum = pd.DataFrame(summary_rows)
    df_sum_path = os.path.join(out_dir, "universality_summary.csv")
    df_sum.to_csv(df_sum_path, index=False)

    # Simple text report
    print("Saved:")
    print(f"- {csv_path}")
    print(f"- {txt_path}")
    print(f"- {df_sum_path}")
    for city, *_ in configs:
        print(f"- {os.path.join(out_dir, f'{city.lower()}_fits.png')}")


if __name__ == "__main__":
    main()


