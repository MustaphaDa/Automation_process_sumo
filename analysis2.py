#!/usr/bin/env python3
"""
Compute summary statistics of PT vehicle trip durations from SUMO tripinfo outputs
for four cities (Debrecen, Pécs, Szeged, Brest).

Outputs:
- Prints per-city count, average travel time (s), and standard deviation (s)
- Saves CSV to outputs/analysis/pt_tripinfo_stats.csv

Assumptions:
- Provided tripinfo.xml files contain PT vehicles (no extra filtering applied)
"""

import csv
import os
import sys
from typing import Dict, List, Tuple

import numpy as np
import xml.etree.ElementTree as ET


def ensure_parent(path: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def parse_tripinfo_durations(xml_path: str) -> List[float]:
    """Stream-parse a SUMO tripinfo.xml file and collect duration values (seconds)."""
    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"Missing tripinfo file: {xml_path}")

    durations: List[float] = []
    try:
        for _event, elem in ET.iterparse(xml_path, events=("end",)):
            if elem.tag == "tripinfo":
                duration_str = elem.get("duration")
                if duration_str is not None:
                    try:
                        durations.append(float(duration_str))
                    except ValueError:
                        pass
                elem.clear()
    except ET.ParseError as exc:
        raise SystemExit(f"XML parse error in {xml_path}: {exc}")

    return durations


def compute_stats(values: List[float]) -> Tuple[int, float, float]:
    """Return count, mean, std (population) for a list of floats. Empty -> zeros."""
    if not values:
        return 0, 0.0, 0.0
    arr = np.asarray(values, dtype=float)
    count = int(arr.size)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=0))  # population std
    return count, mean, std


def count_unique_routes(routes_path: str) -> int:
    """Count unique non-empty route_id values from a GTFS routes file.

    The file is expected to be CSV-like with a header containing 'route_id'.
    """
    if not os.path.exists(routes_path):
        return 0

    unique_ids = set()
    try:
        with open(routes_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            # If header has route_id, use it; else fallback to first column as route_id
            if reader.fieldnames and any(name.strip().lower() == "route_id" for name in reader.fieldnames):
                for row in reader:
                    route_id = (row.get("route_id") or "").strip()
                    if route_id:
                        unique_ids.add(route_id)
            else:
                f.seek(0)
                simple_reader = csv.reader(f)
                for idx, parts in enumerate(simple_reader):
                    if idx == 0 and parts and any(token.lower() == "route_id" for token in parts):
                        continue
                    if not parts:
                        continue
                    route_id = (parts[0] or "").strip()
                    if route_id and route_id.lower() != "route_id":
                        unique_ids.add(route_id)
    except Exception:
        return 0

    return len(unique_ids)


def main() -> None:
    # Absolute paths provided by the user
    city_to_path: Dict[str, str] = {
        "Debrecen": r"C:\Users\RPC\Desktop\sumo_automation\debrecen_case_sumo_automation\old_methods\tripinfo.xml",
        "Pécs": r"C:\Users\RPC\Desktop\sumo_automation\Pécs_sumo_automation\old_method\tripinfo.xml",
        "Szeged": r"C:\Users\RPC\Desktop\sumo_automation\Szeged_sumo_automation\old_method\tripinfo.xml",
        "Brest": r"C:\Users\RPC\Desktop\sumo_automation\brest_sumo_case\old_method\tripinfo.xml",
    }

    city_to_routes: Dict[str, str] = {
        "Debrecen": r"C:\Users\RPC\Desktop\sumo_automation\routes_cities\routes_debrecen.txt",
        "Brest": r"C:\Users\RPC\Desktop\sumo_automation\routes_cities\routes_brest.txt",
        "Pécs": r"C:\Users\RPC\Desktop\sumo_automation\routes_cities\routes_pecs.txt",
        "Szeged": r"C:\Users\RPC\Desktop\sumo_automation\routes_cities\routes_Szeged.txt",
    }

    results: List[Tuple[str, int, float, float, int]] = []

    print("City | Count | Average(s) | StdDev(s) | Routes")
    print("-----|-------|------------|-----------|--------")
    for city, path in city_to_path.items():
        durations = parse_tripinfo_durations(path)
        count, mean, std = compute_stats(durations)
        routes_count = count_unique_routes(city_to_routes.get(city, ""))
        results.append((city, count, mean, std, routes_count))
        print(f"{city} | {count} | {mean:.2f} | {std:.2f} | {routes_count}")

    out_csv = os.path.join("outputs", "analysis", "pt_tripinfo_stats.csv")
    ensure_parent(out_csv)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "count", "mean_s", "std_s", "num_routes"])
        for city, count, mean, std, routes_count in results:
            writer.writerow([city, count, f"{mean:.6f}", f"{std:.6f}", routes_count])

    print(f"Saved: {os.path.abspath(out_csv)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


