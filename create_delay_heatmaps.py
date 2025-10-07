#!/usr/bin/env python3
"""
Create geographic heat maps showing where each city experiences high public transport delays.

For each city, this script:
1. Reads stop locations from SUMO network files (osm_ptstops.xml)
2. Reads per-stop delay data from the analysis Excel file
3. Generates a scatter plot heat map showing delay severity by location
4. Saves individual city heat maps and a combined 2x2 comparison figure

The heat maps use color intensity to show delay severity at each stop location.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Tuple, Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib import cm
import numpy as np


def parse_stop_locations_from_xml(gtfs_add_path: str, network_path: str) -> Dict[str, Tuple[float, float]]:
    """
    Parse stop IDs and their (x, y) coordinates from SUMO network files.
    
    Args:
        gtfs_add_path: Path to gtfs_publictransport.add.xml file (contains GTFS-generated stop IDs)
        network_path: Path to network .net.xml file containing edge/lane coordinates
    
    Returns:
        Dictionary mapping stop_id to (x, y) coordinates
    """
    stop_locations = {}
    
    # First, read the network to get lane geometries
    lane_coords = {}
    try:
        net_tree = ET.parse(network_path)
        net_root = net_tree.getroot()
        
        # Parse lane shapes (they contain the actual coordinates)
        for edge in net_root.findall('.//edge'):
            for lane in edge.findall('lane'):
                lane_id = lane.attrib.get('id')
                shape = lane.attrib.get('shape')
                if lane_id and shape:
                    # Shape is a space-separated list of "x,y" coordinates
                    coords = []
                    for point in shape.split():
                        if ',' in point:
                            x, y = point.split(',')
                            coords.append((float(x), float(y)))
                    if coords:
                        # Use midpoint of lane as representative location
                        mid_idx = len(coords) // 2
                        lane_coords[lane_id] = coords[mid_idx]
    except Exception as e:
        print(f"  Warning: Could not parse network file {network_path}: {e}")
        return stop_locations
    
    # Now read the GTFS stops and match them to lane coordinates
    try:
        stops_tree = ET.parse(gtfs_add_path)
        stops_root = stops_tree.getroot()
        
        for bus_stop in stops_root.findall('.//busStop'):
            stop_id = bus_stop.attrib.get('id')
            lane = bus_stop.attrib.get('lane')
            
            if stop_id and lane and lane in lane_coords:
                stop_locations[stop_id] = lane_coords[lane]
                
    except Exception as e:
        print(f"  Warning: Could not parse GTFS stops file {gtfs_add_path}: {e}")
    
    return stop_locations


def read_stop_delays_from_excel(excel_path: str, traffic_value: Optional[int] = None) -> Dict[str, float]:
    """
    Read per-stop average delays from the Excel analysis file.
    
    Args:
        excel_path: Path to pt_delay.xlsx file
        traffic_value: Specific traffic value sheet to read (if None, uses max value)
    
    Returns:
        Dictionary mapping stop_id to average delay in seconds
    """
    stop_delays = {}
    
    if not os.path.exists(excel_path):
        print(f"  Warning: Excel file not found: {excel_path}")
        return stop_delays
    
    try:
        # Read summary to find the maximum traffic value if not specified
        if traffic_value is None:
            summary_df = pd.read_excel(excel_path, sheet_name='summary')
            if 'value' in summary_df.columns and len(summary_df) > 0:
                traffic_value = int(summary_df['value'].max())
            else:
                print(f"  Warning: Could not determine max traffic value from summary")
                return stop_delays
        
        # Read the specific traffic value sheet
        sheet_name = str(traffic_value)
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        if 'stop' not in df.columns:
            print(f"  Warning: 'stop' column not found in sheet {sheet_name}")
            return stop_delays
        
        # Check if we have the pre-calculated average, otherwise calculate it
        if 'stop_avg_delta_s' in df.columns:
            # Use pre-calculated average
            stop_delays_raw = df.groupby('stop')['stop_avg_delta_s'].first().to_dict()
        elif 'delay_delta_s' in df.columns:
            # Calculate average from delay_delta_s
            stop_delays_raw = df.groupby('stop')['delay_delta_s'].mean().to_dict()
        else:
            print(f"  Warning: Neither 'stop_avg_delta_s' nor 'delay_delta_s' found in sheet {sheet_name}")
            return stop_delays
        
        # Normalize stop IDs (handle numeric and string formats)
        for stop_id, delay in stop_delays_raw.items():
            # Convert to string and handle numeric IDs
            if isinstance(stop_id, float):
                # Check if it's like 15239046.0 (integer float)
                if stop_id == int(stop_id):
                    normalized_id = str(int(stop_id))
                else:
                    # It's like 15239046.1, keep one decimal
                    normalized_id = str(stop_id)
            else:
                normalized_id = str(stop_id)
            
            stop_delays[normalized_id] = delay
        
    except Exception as e:
        print(f"  Warning: Error reading Excel {excel_path}: {e}")
        import traceback
        traceback.print_exc()
    
    return stop_delays


def create_heatmap(
    stop_locations: Dict[str, Tuple[float, float]], 
    stop_delays: Dict[str, float],
    city_name: str,
    ax: plt.Axes,
    show_colorbar: bool = True
) -> None:
    """
    Create a geographic heat map of delays on the provided axes.
    
    Args:
        stop_locations: Dictionary mapping stop_id to (x, y) coordinates
        stop_delays: Dictionary mapping stop_id to delay in seconds
        city_name: Name of the city for the title
        ax: Matplotlib axes to plot on
        show_colorbar: Whether to show the colorbar
    """
    # Match stops that have both location and delay data
    x_coords = []
    y_coords = []
    delays = []
    
    for stop_id, (x, y) in stop_locations.items():
        if stop_id in stop_delays:
            delay = stop_delays[stop_id]
            x_coords.append(x)
            y_coords.append(y)
            delays.append(delay)
    
    if not x_coords:
        ax.text(0.5, 0.5, f"No data available\nfor {city_name}", 
               ha='center', va='center', transform=ax.transAxes, fontsize=12)
        ax.set_title(city_name, fontsize=14, fontweight='bold')
        return
    
    # Convert to numpy arrays
    x_coords = np.array(x_coords)
    y_coords = np.array(y_coords)
    delays = np.array(delays)
    
    # Create color map: green (low delay) -> yellow -> red (high delay)
    norm = mcolors.TwoSlopeNorm(vmin=min(delays), vcenter=np.median(delays), vmax=max(delays))
    cmap = cm.get_cmap('RdYlGn_r')  # Reverse so red is high
    
    # Create scatter plot with colors based on delay
    scatter = ax.scatter(
        x_coords, 
        y_coords, 
        c=delays,
        cmap=cmap,
        norm=norm,
        s=80,
        alpha=0.7,
        edgecolors='black',
        linewidths=0.5
    )
    
    ax.set_title(f"{city_name}\n({len(delays)} stops)", fontsize=14, fontweight='bold')
    ax.set_xlabel("X Coordinate (m)", fontsize=11)
    ax.set_ylabel("Y Coordinate (m)", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal', adjustable='box')
    
    # Add colorbar if requested
    if show_colorbar:
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Average Delay (seconds)', fontsize=11)
    
    # Add statistics text box
    stats_text = f"Mean: {np.mean(delays):.1f}s\nMedian: {np.median(delays):.1f}s\nMax: {np.max(delays):.1f}s"
    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
           fontsize=9, verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))


def main():
    # Define city configurations
    cities = {
        "Debrecen": {
            "ptstops": r"debrecen_case_sumo_automation\outputs\gtfs\gtfs_publictransport.add.xml",
            "network": r"debrecen_case_sumo_automation\outputs\net\Debrecen_full.net.xml",
            "excel": r"debrecen_case_sumo_automation\outputs\analysis\pt_delay.xlsx",
        },
        "Pécs": {
            "ptstops": r"Pécs_sumo_automation\outputs\gtfs\gtfs_publictransport.add.xml",
            "network": r"Pécs_sumo_automation\outputs\net\Pecs_full.net.xml",
            "excel": r"Pécs_sumo_automation\outputs\analysis\pt_delay.xlsx",
        },
        "Szeged": {
            "ptstops": r"Szeged_sumo_automation\outputs\gtfs\gtfs_publictransport.add.xml",
            "network": r"Szeged_sumo_automation\outputs\net\Szeged_full.net.xml",
            "excel": r"Szeged_sumo_automation\outputs\analysis\pt_delay.xlsx",
        },
        "Brest": {
            "ptstops": r"brest_sumo_case\outputs\gtfs\gtfs_publictransport.add.xml",
            "network": r"brest_sumo_case\outputs\net\Brest_full.net.xml",
            "excel": r"brest_sumo_case\outputs\analysis\pt_delay_analysis.xlsx",
        },
    }
    
    print("\n" + "=" * 80)
    print("CREATING DELAY HEAT MAPS FOR ALL CITIES")
    print("=" * 80 + "\n")
    
    # Create output directory
    output_dir = Path("outputs/analysis")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create individual heat maps for each city
    for city_name, paths in cities.items():
        print(f"\nProcessing {city_name}...")
        print("-" * 40)
        
        # Parse stop locations
        print("  Reading stop locations...")
        stop_locations = parse_stop_locations_from_xml(paths["ptstops"], paths["network"])
        print(f"  Found {len(stop_locations)} stop locations")
        
        # Read delay data
        print("  Reading delay data...")
        stop_delays = read_stop_delays_from_excel(paths["excel"])
        print(f"  Found delay data for {len(stop_delays)} stops")
        
        # Create individual heat map
        fig, ax = plt.subplots(figsize=(12, 10), dpi=150)
        fig.patch.set_facecolor("white")
        
        create_heatmap(stop_locations, stop_delays, city_name, ax, show_colorbar=True)
        
        # Save individual figure
        output_path = output_dir / f"{city_name.lower()}_delay_heatmap.png"
        fig.savefig(output_path, bbox_inches='tight', dpi=150, facecolor='white')
        print(f"  Saved: {output_path}")
        plt.close(fig)
    
    # Create combined 2x2 figure
    print("\n" + "=" * 80)
    print("Creating combined 2x2 comparison figure...")
    print("=" * 80)
    
    fig, axes = plt.subplots(2, 2, figsize=(18, 16), dpi=150)
    fig.patch.set_facecolor("white")
    axes = axes.ravel()
    
    for idx, (city_name, paths) in enumerate(cities.items()):
        print(f"  Adding {city_name} to combined figure...")
        
        stop_locations = parse_stop_locations_from_xml(paths["ptstops"], paths["network"])
        stop_delays = read_stop_delays_from_excel(paths["excel"])
        
        create_heatmap(stop_locations, stop_delays, city_name, axes[idx], show_colorbar=True)
    
    fig.suptitle("Public Transport Delay Heat Maps by City\n(at Maximum Traffic Level)", 
                 fontsize=16, fontweight='bold', y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.99])
    
    # Save combined figure
    combined_path = output_dir / "all_cities_delay_heatmap.png"
    fig.savefig(combined_path, bbox_inches='tight', dpi=150, facecolor='white')
    print(f"\nSaved combined figure: {combined_path}")
    plt.close(fig)
    
    print("\n" + "=" * 80)
    print("HEAT MAP GENERATION COMPLETE!")
    print("=" * 80)
    print(f"\nOutput files saved in: {output_dir.absolute()}")
    print("\nGenerated files:")
    print("  - debrecen_delay_heatmap.png")
    print("  - pécs_delay_heatmap.png")
    print("  - szeged_delay_heatmap.png")
    print("  - brest_delay_heatmap.png")
    print("  - all_cities_delay_heatmap.png")


if __name__ == "__main__":
    main()

