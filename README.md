# SUMO Automation Analysis Scripts

This repository contains Python scripts for analyzing SUMO (Simulation of Urban Mobility) simulation results, focusing on public transport delay analysis and trip completion statistics across multiple cities.

## Scripts Overview

### 1. `analysis.py`
**Purpose**: Basic delay analysis and visualization
- Reads summary data from Excel files for each city
- Detects mean delay columns automatically
- Plots city-specific delay comparisons using Trip info and Stop info methods
- Creates log-scale visualizations of delay patterns
- **Cities**: Debrecen, Pécs, Szeged, Brest

### 2. `analysis2.py`
**Purpose**: Trip duration statistics and analysis
- Parses tripinfo.xml files to extract trip durations
- Computes statistical measures (count, mean, standard deviation)
- Generates summary statistics for public transport trips
- Exports results to CSV format
- **Output**: `pt_tripinfo_stats.csv`

### 3. `analysis_find_limit.py`
**Purpose**: Extract delay values at specific traffic points
- Finds delay at maximum traffic point (last row of summary sheet)
- Extracts delay from third column of summary data
- Provides delay values for each city at peak traffic conditions
- **Output**: `max_delay_values.csv`

### 4. `analysis_Baseline_Public.py`
**Purpose**: Public transport baseline analysis with route correlation
- Creates scatter plots showing relationship between number of routes and average travel time
- Includes linear regression analysis with correlation statistics (r, R², p-value)
- Shows error bars for standard deviation
- **Route counts**: Debrecen: 89, Pécs: 93, Szeged: 63, Brest: 60

### 5. `create_delay_heatmaps.py`
**Purpose**: Geographic delay heatmaps (original version)
- Creates scatter plot heatmaps of public transport delays
- Shows delay intensity at individual stop locations
- Includes city center markers and zone circles (2km, 5km radii)
- **Output**: Individual city heatmap PNG files

### 6. `create_heatmaps_with_zones.py`
**Purpose**: Advanced delay heatmaps with zoning overlay
- Creates smooth, continuous delay-weighted density heatmaps
- Aggregates delays across all traffic levels (equal weighting)
- Shows persistent delay hotspots across the city
- Includes city center calculation and zone visualization
- **Features**:
  - Smooth interpolation for football-style heatmap appearance
  - Zone circles: 2km (blue) and 5km (cyan) from city center
  - Statistics boxes with mean, median, max delays
  - Combined 2x2 grid layout for document inclusion
- **Output**: Individual and combined heatmap PNG files

### 7. `analyze_trip_completion.py`
**Purpose**: Trip completion analysis across traffic levels
- Analyzes complete vs incomplete trips from tripinfo.xml files
- Separates public transport and private vehicle trips
- Averages results across 10 simulations per traffic level
- **Output**: Three CSV files:
  - `public_transport_completion.csv`
  - `private_vehicle_completion.csv`
  - `combined_completion.csv`

### 8. `get_center.py`
**Purpose**: Calculate city network center
- Parses SUMO network XML files
- Calculates average center coordinates from edge shapes
- Used by heatmap scripts for zone circle placement

## Data Sources

### Input Files
- **Excel files**: `pt_delay.xlsx` (delay analysis results)
- **XML files**: 
  - `tripinfo.xml` (trip completion data)
  - `network.net.xml` (road network geometry)
  - `gtfs_publictransport.add.xml` (public transport stops)

### Directory Structure
```
city_sumo_case/
├── outputs/
│   ├── analysis/          # Excel delay analysis files
│   ├── sim/              # Simulation results (tripinfo.xml)
│   ├── gtfs/             # GTFS public transport data
│   └── net/              # Network files
```

## Key Features

### Delay Analysis
- **Traffic levels**: 1000 to 58000 vehicles
- **Simulations**: 10 runs per traffic level
- **Methods**: Trip info vs Stop info comparison
- **Aggregation**: Equal weighting across all traffic points

### Visualization
- **Heatmaps**: Smooth, continuous delay density surfaces
- **Zoning**: 2km and 5km radius zones from city center
- **Statistics**: Mean, median, maximum delay values
- **Layout**: Professional 2x2 grid for document inclusion

### Trip Completion
- **Completion criteria**: Valid arrival time, duration > 0, not vaporized
- **Vehicle types**: Public transport (bus) vs private vehicles
- **Analysis**: Per traffic level with 10-simulation averaging

## Usage

### Running Individual Scripts
```bash
# Basic delay analysis
python analysis.py

# Trip completion analysis
python analyze_trip_completion.py

# Create heatmaps
python create_heatmaps_with_zones.py
```

### Output Files
- **PNG**: Heatmap visualizations
- **CSV**: Statistical analysis results
- **Location**: `outputs/analysis/` directory

## Requirements
- Python 3.7+
- pandas
- numpy
- matplotlib
- scipy (for smoothing)
- xml.etree.ElementTree

## Cities Analyzed
1. **Debrecen** (614 stops)
2. **Pécs** (545 stops) 
3. **Szeged** (424 stops)
4. **Brest** (651 stops)

Each city has complete simulation data across all traffic levels with 10 simulation runs per level.