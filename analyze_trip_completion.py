#!/usr/bin/env python3
"""
Analyze trip completion rates from SUMO simulation outputs.

This script analyzes tripinfo.xml files to determine:
- Number of complete vs incomplete trips per traffic level
- Completion percentage for each traffic level (averaged across 10 simulations)
- Separate analysis for public transport, private vehicles, and combined
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Tuple, List
import pandas as pd
import numpy as np

def analyze_trip_completion_by_type(tripinfo_path: str) -> Tuple[int, int, int, int, float, float]:
    """
    Analyze trip completion from a tripinfo.xml file, separating public transport and private vehicles.
    
    Args:
        tripinfo_path: Path to tripinfo.xml file
        
    Returns:
        Tuple of (pt_complete, pt_incomplete, pv_complete, pv_incomplete, pt_percentage, pv_percentage)
    """
    try:
        tree = ET.parse(tripinfo_path)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing {tripinfo_path}: {e}")
        return 0, 0, 0, 0, 0.0, 0.0
    
    pt_complete = 0
    pt_incomplete = 0
    pv_complete = 0
    pv_incomplete = 0
    
    for tripinfo in root.findall('.//tripinfo'):
        # Check if trip is complete
        is_complete = True
        
        # Method 1: Check if vaporized
        vaporized = tripinfo.get('vaporized', '')
        if vaporized == 'true':
            is_complete = False
        
        # Method 2: Check if arrival time exists
        arrival = tripinfo.get('arrival', '')
        if not arrival or arrival == '':
            is_complete = False
        
        # Method 3: Check if duration is valid
        duration = tripinfo.get('duration', '0')
        try:
            if float(duration) <= 0:
                is_complete = False
        except (ValueError, TypeError):
            is_complete = False
        
        # Determine if it's public transport or private vehicle
        vtype = tripinfo.get('vType', '').lower()
        is_public_transport = 'bus' in vtype or 'pt' in vtype or 'public' in vtype
        
        if is_public_transport:
            if is_complete:
                pt_complete += 1
            else:
                pt_incomplete += 1
        else:
            if is_complete:
                pv_complete += 1
            else:
                pv_incomplete += 1
    
    # Calculate percentages
    pt_total = pt_complete + pt_incomplete
    pv_total = pv_complete + pv_incomplete
    
    pt_percentage = (pt_complete / pt_total * 100) if pt_total > 0 else 0.0
    pv_percentage = (pv_complete / pv_total * 100) if pv_total > 0 else 0.0
    
    return pt_complete, pt_incomplete, pv_complete, pv_incomplete, pt_percentage, pv_percentage

def find_simulation_files(base_dir: str) -> Dict[str, Dict[int, List[str]]]:
    """
    Find all simulation files organized by city and traffic level.
    
    Args:
        base_dir: Base directory to search
        
    Returns:
        Dictionary: {city: {traffic_level: [list_of_simulation_files]}}
    """
    simulation_files = {}
    base_path = Path(base_dir)
    
    # Define city directories and their patterns
    city_configs = {
        'debrecen': {
            'dir': 'debrecen_case_sumo_automation',
            'pattern': '4_{traffic_level}_{sim_number}_Debrecen_sim_output.xml'
        },
        'pecs': {
            'dir': 'Pécs_sumo_automation',
            'pattern': '4_{traffic_level}_{sim_number}_Pécs_sim_output.xml'
        },
        'szeged': {
            'dir': 'Szeged_sumo_automation',
            'pattern': '4_{traffic_level}_{sim_number}_Szeged_sim_output.xml'
        },
        'brest': {
            'dir': 'brest_sumo_case',
            'pattern': '4_{traffic_level}_{sim_number}_Brest_sim_output.xml'
        }
    }
    
    for city_name, config in city_configs.items():
        city_dir = base_path / config['dir']
        if not city_dir.exists():
            print(f"Warning: {city_dir} not found")
            continue
            
        simulation_files[city_name] = {}
        
        # Look for outputs/sim directory
        sim_dir = city_dir / "outputs" / "sim"
        if not sim_dir.exists():
            print(f"Warning: {sim_dir} not found")
            continue
        
        # Find all simulation files directly in sim directory
        sim_files = []
        for sim_file in sim_dir.glob("*.xml"):
            if "sim_output" in sim_file.name:
                sim_files.append(str(sim_file))
        
        if not sim_files:
            print(f"No simulation files found for {city_name}")
            continue
        
        # Group files by traffic level
        traffic_groups = {}
        for sim_file in sim_files:
            # Parse filename to extract traffic level (e.g., "4_10000_1_Debrecen_sim_output.xml")
            filename = Path(sim_file).name
            parts = filename.split('_')
            if len(parts) >= 2:
                try:
                    traffic_level = int(parts[1])  # Second part is traffic level
                    if traffic_level not in traffic_groups:
                        traffic_groups[traffic_level] = []
                    traffic_groups[traffic_level].append(sim_file)
                except (ValueError, IndexError):
                    continue
        
        # Store results
        for traffic_level, files in traffic_groups.items():
            simulation_files[city_name][traffic_level] = files
            print(f"Found {len(files)} simulations for {city_name} at traffic level {traffic_level}")
    
    return simulation_files

def analyze_traffic_levels(base_dir: str = ".") -> None:
    """
    Analyze trip completion for all cities and traffic levels.
    
    Args:
        base_dir: Base directory to search for simulation files
    """
    print("=" * 80)
    print("TRIP COMPLETION ANALYSIS BY TRAFFIC LEVEL")
    print("=" * 80)
    
    # Find all simulation files
    simulation_files = find_simulation_files(base_dir)
    
    if not simulation_files:
        print("No simulation files found!")
        return
    
    # Results storage
    pt_results = []  # Public transport results
    pv_results = []  # Private vehicle results
    combined_results = []  # Combined results
    
    for city_name, traffic_levels in simulation_files.items():
        print(f"\nAnalyzing {city_name}...")
        
        for traffic_level, sim_files in traffic_levels.items():
            print(f"  Traffic Level {traffic_level} ({len(sim_files)} simulations)")
            
            # Analyze each simulation for this traffic level
            pt_complete_list = []
            pt_incomplete_list = []
            pt_percentage_list = []
            pv_complete_list = []
            pv_incomplete_list = []
            pv_percentage_list = []
            
            for sim_file in sim_files:
                if not os.path.exists(sim_file):
                    continue
                    
                pt_comp, pt_incomp, pv_comp, pv_incomp, pt_perc, pv_perc = analyze_trip_completion_by_type(sim_file)
                
                pt_complete_list.append(pt_comp)
                pt_incomplete_list.append(pt_incomp)
                pt_percentage_list.append(pt_perc)
                pv_complete_list.append(pv_comp)
                pv_incomplete_list.append(pv_incomp)
                pv_percentage_list.append(pv_perc)
            
            if not pt_complete_list:
                continue
            
            # Calculate averages across all simulations
            avg_pt_complete = np.mean(pt_complete_list)
            avg_pt_incomplete = np.mean(pt_incomplete_list)
            avg_pt_percentage = np.mean(pt_percentage_list)
            
            avg_pv_complete = np.mean(pv_complete_list)
            avg_pv_incomplete = np.mean(pv_incomplete_list)
            avg_pv_percentage = np.mean(pv_percentage_list)
            
            # Combined results
            avg_total_complete = avg_pt_complete + avg_pv_complete
            avg_total_incomplete = avg_pt_incomplete + avg_pv_incomplete
            avg_total_percentage = (avg_total_complete / (avg_total_complete + avg_total_incomplete) * 100) if (avg_total_complete + avg_total_incomplete) > 0 else 0
            
            # Store results
            pt_results.append({
                'City': city_name,
                'Traffic_Level': traffic_level,
                'Avg_Complete_Trips': avg_pt_complete,
                'Avg_Incomplete_Trips': avg_pt_incomplete,
                'Avg_Completion_Percentage': avg_pt_percentage
            })
            
            pv_results.append({
                'City': city_name,
                'Traffic_Level': traffic_level,
                'Avg_Complete_Trips': avg_pv_complete,
                'Avg_Incomplete_Trips': avg_pv_incomplete,
                'Avg_Completion_Percentage': avg_pv_percentage
            })
            
            combined_results.append({
                'City': city_name,
                'Traffic_Level': traffic_level,
                'Avg_Complete_Trips': avg_total_complete,
                'Avg_Incomplete_Trips': avg_total_incomplete,
                'Avg_Completion_Percentage': avg_total_percentage
            })
    
    # Create and save results
    if pt_results:
        print("\n" + "=" * 80)
        print("PUBLIC TRANSPORT RESULTS")
        print("=" * 80)
        
        pt_df = pd.DataFrame(pt_results)
        print(pt_df.to_string(index=False, float_format='%.1f'))
        pt_df.to_csv("public_transport_completion.csv", index=False)
        
        print("\n" + "=" * 80)
        print("PRIVATE VEHICLE RESULTS")
        print("=" * 80)
        
        pv_df = pd.DataFrame(pv_results)
        print(pv_df.to_string(index=False, float_format='%.1f'))
        pv_df.to_csv("private_vehicle_completion.csv", index=False)
        
        print("\n" + "=" * 80)
        print("COMBINED RESULTS")
        print("=" * 80)
        
        combined_df = pd.DataFrame(combined_results)
        print(combined_df.to_string(index=False, float_format='%.1f'))
        combined_df.to_csv("combined_completion.csv", index=False)
        
        print(f"\nResults saved to:")
        print(f"  - public_transport_completion.csv")
        print(f"  - private_vehicle_completion.csv") 
        print(f"  - combined_completion.csv")

if __name__ == "__main__":
    analyze_traffic_levels()
