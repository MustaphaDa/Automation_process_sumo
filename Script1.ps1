Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Success($msg) { Write-Host "[SUCCESS] $msg" -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "[WARNING] $msg" -ForegroundColor Yellow }
function Write-Err($msg)     { Write-Host "[ERROR] $msg" -ForegroundColor Red }

function Test-Command([string]$name) {
    try { return [bool](Get-Command $name -ErrorAction Stop) } catch { return $false }
}

function Get-PythonCommand {
    if ($env:PYTHON) { return $env:PYTHON }
    if (Test-Command py) { return 'py' }
    if (Test-Command python3) { return 'python3' }
    # Try common user installation paths first to avoid Windows Store alias
    $local = Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python" -Filter "Python3*" -Directory -ErrorAction SilentlyContinue | Get-ChildItem -Filter python.exe -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($local) { return $local.FullName }
    if (Test-Command python) { return 'python' }
    throw "Python not found. Please install Python 3 and ensure it is in PATH, or set $env:PYTHON."
}

function Ensure-RequestsInstalled([string]$pythonCmd) {
    Write-Info "Checking Python 'requests' library..."
    try {
        & $pythonCmd -c "import requests" | Out-Null
        $exit = $LASTEXITCODE
    } catch {
        $exit = 1
    }
    if ($exit -ne 0) {
        Write-Info "Installing 'requests' via pip..."
        & $pythonCmd -m pip install --user requests | Write-Host
    }
}

function Ensure-GtfsDeps([string]$pythonCmd) {
    Write-Info "Checking Python packages for GTFS import (numpy, pandas, lxml, shapely, rtree, pyproj)..."
    $modules = @('numpy','pandas','lxml','shapely','rtree','pyproj','openpyxl')
    $missing = @()
    foreach ($m in $modules) {
        try { & $pythonCmd -c "import $m" | Out-Null; $ok = ($LASTEXITCODE -eq 0) } catch { $ok = $false }
        if (-not $ok) { $missing += $m }
    }
    if ($missing.Count -gt 0) {
        Write-Info ("Installing missing packages: {0}" -f ($missing -join ', '))
        & $pythonCmd -m pip install --user @missing | Write-Host
    }
}

# Remove diacritics and unsafe characters for filenames
function Remove-Diacritics([string]$text) {
    if ([string]::IsNullOrEmpty($text)) { return $text }
    $normalized = $text.Normalize([Text.NormalizationForm]::FormD)
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $normalized.ToCharArray()) {
        $cat = [Globalization.CharUnicodeInfo]::GetUnicodeCategory($ch)
        if ($cat -ne [Globalization.UnicodeCategory]::NonSpacingMark) { [void]$sb.Append($ch) }
    }
    $clean = $sb.ToString().Normalize([Text.NormalizationForm]::FormC)
    # Replace anything not safe for filenames with '_'
    return ($clean -replace "[^A-Za-z0-9._-]", "_")
}

function Resolve-SUMO {
    Write-Info "Checking SUMO tools..."
    $tools = @('sumo','netconvert','od2trips','duarouter')
    $missing = @()
    foreach ($t in $tools) { if (-not (Test-Command $t)) { $missing += $t } }
    if ($missing.Count -gt 0 -and -not $env:SUMO_HOME) {
        Write-Err "Missing tools: $($missing -join ', '). Either add them to PATH or set SUMO_HOME."
        throw "SUMO tools not found"
    }
    if ($env:SUMO_HOME) {
        $Global:GTFS2PT = Join-Path $env:SUMO_HOME 'tools\import\gtfs\gtfs2pt.py'
        if (-not (Test-Path $Global:GTFS2PT)) {
            Write-Err "gtfs2pt.py not found at '$Global:GTFS2PT'. Ensure SUMO tools are installed."
            throw "gtfs2pt.py missing"
        }
        Write-Info "Using SUMO_HOME: $($env:SUMO_HOME)"
    } else {
        # Fallback: try gtfs2pt.py via SUMO_HOME-like resolution is not available; require SUMO_HOME
        Write-Err "SUMO_HOME is not set. Please set SUMO_HOME to your SUMO installation root."
        throw "SUMO_HOME not set"
    }
}

function Load-Config {
    Write-Info "Looking for configuration file 'config.json'..."
    if (-not (Test-Path 'config.json')) { return $false }
    try {
        $raw = Get-Content -Path 'config.json' -Raw -Encoding UTF8
        $cfg = $raw | ConvertFrom-Json
    } catch {
        Write-Warn "Failed to read/parse config.json: $($_.Exception.Message)"
        return $false
    }

    if ($null -ne $cfg.cityName) { $Global:CITY_NAME = [string]$cfg.cityName }
    if ($null -ne $cfg.gtfsPath) { $Global:GTFS_PATH = [string]$cfg.gtfsPath }
    if ($null -ne $cfg.simDate) { $Global:SIM_DATE = [string]$cfg.simDate }
    if ($null -ne $cfg.transportModes) { $Global:TRANSPORT_MODES = [string]$cfg.transportModes }
    if ($null -ne $cfg.maxJobs) { $Global:MAX_JOBS = [int]$cfg.maxJobs }
    if ($null -ne $cfg.PSObject.Properties['centerX']) { $Global:CENTER_X = [double]$cfg.centerX }
    if ($null -ne $cfg.PSObject.Properties['centerY']) { $Global:CENTER_Y = [double]$cfg.centerY }
    if ($null -ne $cfg.simsPerValue) { $Global:SIMS_PER_VALUE = [int]$cfg.simsPerValue }

    Write-Success "Loaded configuration from config.json"
    return $true
}

function Get-UserInput {
    Write-Info "Getting user configuration..."

    # Initialize global variables
    $Global:CENTER_X = $null
    $Global:CENTER_Y = $null

    $cfgLoaded = Load-Config

    if ([string]::IsNullOrWhiteSpace($Global:CITY_NAME)) {
        do { $Global:CITY_NAME = Read-Host "Enter the city name (e.g., Budapest, Pecs)" } while ([string]::IsNullOrWhiteSpace($Global:CITY_NAME))
    } else { Write-Info ("City: {0}" -f $Global:CITY_NAME) }

    if ([string]::IsNullOrWhiteSpace($Global:GTFS_PATH)) {
        do {
            $Global:GTFS_PATH = Read-Host "Enter the path to GTFS zip file"
            if (-not (Test-Path $Global:GTFS_PATH)) { Write-Warn "GTFS file not found: $Global:GTFS_PATH" }
        } while (-not (Test-Path $Global:GTFS_PATH))
    } else {
        Write-Info ("GTFS: {0}" -f $Global:GTFS_PATH)
        if (-not (Test-Path $Global:GTFS_PATH)) {
            Write-Err "GTFS file not found at path from config.json: $Global:GTFS_PATH"
            throw "GTFS path invalid"
        }
    }
    try { $Global:GTFS_PATH_ABS = (Resolve-Path $Global:GTFS_PATH).Path } catch { Write-Err "Could not resolve GTFS path: $Global:GTFS_PATH"; throw }
    Write-Info ("Resolved GTFS path: {0}" -f $Global:GTFS_PATH_ABS)

    if (-not ($Global:SIM_DATE -match '^[0-9]{8}$')) {
        do { $Global:SIM_DATE = Read-Host "Enter simulation date (YYYYMMDD, e.g., 20231229)" } while (-not ($Global:SIM_DATE -match '^[0-9]{8}$'))
    } else { Write-Info ("Date: {0}" -f $Global:SIM_DATE) }

    if ([string]::IsNullOrWhiteSpace($Global:TRANSPORT_MODES)) {
        $Global:TRANSPORT_MODES = Read-Host "Enter transport modes (default: bus)"
        if ([string]::IsNullOrWhiteSpace($Global:TRANSPORT_MODES)) { $Global:TRANSPORT_MODES = 'bus' }
    } else { Write-Info ("Modes: {0}" -f $Global:TRANSPORT_MODES) }

    if ($null -eq $Global:MAX_JOBS -or $Global:MAX_JOBS -le 0) {
        $tmp = Read-Host "Enter number of parallel jobs (default: processor count)"
        if ([string]::IsNullOrWhiteSpace($tmp)) { $Global:MAX_JOBS = [Environment]::ProcessorCount } else { $Global:MAX_JOBS = [int]$tmp }
    } else { Write-Info ("Max jobs: {0}" -f $Global:MAX_JOBS) }

    # Center coordinates will be automatically detected from network file
    Write-Info "Center coordinates will be automatically detected from network file"

    if ($null -eq $Global:SIMS_PER_VALUE -or $Global:SIMS_PER_VALUE -le 0) {
        $tmp2 = Read-Host "Enter number of simulations per value (default: 10)"
        if ([string]::IsNullOrWhiteSpace($tmp2)) { $Global:SIMS_PER_VALUE = 10 } else { $Global:SIMS_PER_VALUE = [int]$tmp2 }
    } else { Write-Info ("Simulations per value: {0}" -f $Global:SIMS_PER_VALUE) }

    Write-Success "Configuration completed"
}

function Create-PythonScripts {
    Write-Info "Creating Python helper scripts..."
    $getMap = @'
#!/usr/bin/env python3
import argparse
import requests

HEADERS = {"User-Agent": "sumo-automation/1.0 (contact: exemple@exemple.com)", "Accept-Language": "en"}

def get_bbox(city_name: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise SystemExit(f"No results from Nominatim for '{city_name}'")
    bb = data[0]["boundingbox"]  # [south, north, west, east]
    south, north, west, east = map(float, bb)
    # Lightly expand bbox by 10%
    lat_pad = (north - south) * 0.1
    lon_pad = (east - west) * 0.1
    return south - lat_pad, north + lat_pad, west - lon_pad, east + lon_pad

def download_osm_map(city_name: str, outfile: str):
    overpass_url = "http://overpass-api.de/api/interpreter"
    south, north, west, east = get_bbox(city_name)
    overpass_query = f"""
    [out:xml][timeout:180];
    (
      node({south},{west},{north},{east});
      way({south},{west},{north},{east});
      relation({south},{west},{north},{east});
    );
    out body;
    >;
    out skel qt;
    """
    print(f"Downloading OSM map for {city_name} with bbox S={south}, W={west}, N={north}, E={east} ...")
    try:
        response = requests.post(overpass_url, data={'data': overpass_query}, headers=HEADERS, timeout=180)
    except Exception as e:
        print(f"Failed to contact Overpass API: {e}")
        raise
    if response.status_code == 200 and len(response.content) > 10000:
        with open(outfile, "wb") as file:
            file.write(response.content)
        print(f"Map saved as '{outfile}'")
    else:
        print(f"Failed to download data or empty result. HTTP {response.status_code}, size={len(response.content)}")
        raise SystemExit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True)
    parser.add_argument("--outfile", required=True)
    args = parser.parse_args()
    download_osm_map(args.city, args.outfile)
'@
    Set-Content -Path "get_map.py" -Value $getMap -Encoding UTF8
    Write-Success "get_map.py created"
}

function Create-ConfigFiles {
    Write-Info "Creating configuration files..."

    $od = @'
$O;D2
*From-Time To-Time
06.00 10.00
*Factor
1.00
*some
*additional
*comments
    zone2	zone1	10000	
    zone3	zone1   10000
'@
    Set-Content -Path "private_traffic.od" -Value $od -Encoding UTF8

    $od2trips = @'
<configuration>

	<input>
		<taz-files value="zones.taz.xml"/>
		<od-matrix-files value="private_traffic.od"/>
	</input>

</configuration>

'@
    Set-Content -Path "od2trips.config.xml" -Value $od2trips -Encoding UTF8

    Write-Success "Configuration files created"
}

function Run-Workflow {
    param([string]$pythonCmd)
    Write-Info "Starting automated SUMO workflow..."

    $CITY_SAFE = Remove-Diacritics $CITY_NAME

    # Output folders
    $OUT_ROOT = Join-Path (Get-Location) "outputs"
    $OUT_OSM = Join-Path $OUT_ROOT "osm"
    $OUT_NET = Join-Path $OUT_ROOT "net"
    $OUT_ZONES = Join-Path $OUT_ROOT "zones"
    $OUT_GTFS = Join-Path $OUT_ROOT "gtfs"
    $OUT_SIM = Join-Path $OUT_ROOT "sim"

    foreach ($d in @($OUT_ROOT,$OUT_OSM,$OUT_NET,$OUT_ZONES,$OUT_GTFS,$OUT_SIM)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }

    $osmFile = Join-Path $OUT_OSM ("{0}.osm" -f $CITY_SAFE)
    $netFile = Join-Path $OUT_NET ("{0}_full.net.xml" -f $CITY_SAFE)

    # Step 1: Download map
    Write-Info "Step 1: Checking for existing OSM map..."
    $needDownload = $true
    if (Test-Path $osmFile) {
        try { $size = (Get-Item $osmFile).Length } catch { $size = 0 }
        if ($size -lt 50000) {
            Write-Warn "Existing OSM file is too small ($size bytes). Re-downloading..."
        } else {
            Write-Warn "OSM file already exists and looks valid: $osmFile ($size bytes)"
            $needDownload = $false
        }
    }
    if ($needDownload) {
        Write-Info "Downloading OSM map for $CITY_NAME..."
        & $pythonCmd get_map.py --city "$CITY_NAME" --outfile "$osmFile" | Write-Host
        if (-not (Test-Path $osmFile)) { Write-Err "OSM file not found: $osmFile"; throw "Download failed" }
        $size = (Get-Item $osmFile).Length
        if ($size -lt 50000) { Write-Err "Downloaded OSM file is too small ($size bytes)"; throw "Download failed" }
        Write-Success "OSM map downloaded successfully ($size bytes)"
    }

    # Step 2: Convert OSM to SUMO network
    Write-Info "Step 2: Checking for existing SUMO network..."
    if (Test-Path $netFile) {
        Write-Warn "Network file already exists: $netFile"
    } else {
        Write-Info "Converting OSM to SUMO network..."
        $ptStops = Join-Path $OUT_NET "osm_ptstops.xml"
        $ptLines = Join-Path $OUT_NET "osm_ptlines.xml"
        netconvert --osm-files $osmFile -o $netFile `
                   --ptstop-output $ptStops `
                   --ptline-output $ptLines `
                   --ignore-errors `
                   --remove-edges.isolated `
                   --ramps.guess `
                   --junctions.join | Write-Host
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $netFile)) { Write-Err "Failed to create network file: $netFile"; throw "netconvert failed" }
        Write-Success "Network file created successfully"
    }

    # Step 2.5: Get center coordinates automatically
    if ($null -eq $Global:CENTER_X -or $null -eq $Global:CENTER_Y) {
        Write-Info "Getting center coordinates automatically from network file..."
        $getCenterScript = Join-Path (Get-Location) "get_center.py"
        if (Test-Path $getCenterScript) {
            Push-Location $OUT_NET
            try {
                $netFileName = Split-Path $netFile -Leaf
                $centerOutput = & $pythonCmd $getCenterScript $netFileName 2>&1
                if ($LASTEXITCODE -eq 0) {
                    # Parse output like "Suggested center: (6357.804047432355, 6651.46203987553)"
                    if ($centerOutput -match "Suggested center: \(([0-9.-]+), ([0-9.-]+)\)") {
                        $Global:CENTER_X = [double]$matches[1]
                        $Global:CENTER_Y = [double]$matches[2]
                        Write-Success ("Center coordinates obtained: X={0}, Y={1}" -f $Global:CENTER_X, $Global:CENTER_Y)
                    } else {
                        Write-Warn "Could not parse center coordinates from output: $centerOutput"
                        throw "Failed to parse center coordinates"
                    }
                } else {
                    Write-Warn "get_center.py failed with exit code: $LASTEXITCODE"
                    throw "get_center.py failed"
                }
            } catch {
                Write-Err "Failed to get center coordinates automatically: $($_.Exception.Message)"
                throw "Center coordinates required"
            } finally {
                Pop-Location
            }
        } else {
            Write-Err "get_center.py script not found at: $getCenterScript"
            throw "get_center.py missing"
        }
    } else {
        Write-Info ("Using center coordinates from config: X={0}, Y={1}" -f $Global:CENTER_X, $Global:CENTER_Y)
    }

    # Step 3: Create zones
    Write-Info "Step 3: Checking for existing zones..."
    $zone1 = Join-Path $OUT_ZONES "zone1.xml"
    $zone2 = Join-Path $OUT_ZONES "zone2.xml"
    $zone3 = Join-Path $OUT_ZONES "zone3.xml"
    if ((Test-Path $zone1) -and (Test-Path $zone2) -and (Test-Path $zone3)) {
        Write-Warn "Zone files already exist: $zone1, $zone2, $zone3"
    } else {
        Write-Info "Creating traffic zones..."
        Push-Location $OUT_ZONES
        & $pythonCmd (Join-Path (Get-Location).Path "..\..\get_zones.py") $netFile $CENTER_X $CENTER_Y | Write-Host
        Pop-Location
        if (-not ((Test-Path $zone1) -and (Test-Path $zone2) -and (Test-Path $zone3))) { Write-Err "Failed to create all zone files"; throw "zones failed" }
        Write-Success "Zone files created successfully"
    }

    # Step 4: Create TAZ
    Write-Info "Step 4: Checking for existing TAZ file..."
    $tazFile = Join-Path $OUT_ZONES "zones.taz.xml"
    if (Test-Path $tazFile) {
        Write-Warn "TAZ file already exists: $tazFile"
    } else {
        Write-Info "Creating TAZ file..."
        Push-Location $OUT_ZONES
        & $pythonCmd (Join-Path (Get-Location).Path "..\..\get_taz.py") | Write-Host
        Pop-Location
        if (-not (Test-Path $tazFile)) { Write-Err "Failed to create TAZ file"; throw "taz failed" }
        Write-Success "TAZ file created successfully"
    }

    # Step 5: GTFS processing
    Write-Info "Step 5: Checking for existing GTFS output files..."
    $vtypes = Join-Path $OUT_GTFS "pt_vtypes.xml"
    $gtfsRou = Join-Path $OUT_GTFS "gtfs_publictransport.rou.xml"
    $gtfsAdd = Join-Path $OUT_GTFS "gtfs_publictransport.add.xml"
    if ((Test-Path $vtypes) -and (Test-Path $gtfsRou) -and (Test-Path $gtfsAdd)) {
        Write-Warn "GTFS output files already exist"
    } else {
        Write-Info "Processing GTFS data..."
        Push-Location $OUT_GTFS
        & $pythonCmd $Global:GTFS2PT -n "$netFile" --gtfs "$Global:GTFS_PATH_ABS" --date $SIM_DATE --modes "$TRANSPORT_MODES" `
            --vtype-output "$vtypes" `
            --route-output "$gtfsRou" `
            --additional-output "$gtfsAdd"
        Pop-Location
        if (-not ((Test-Path $vtypes) -and (Test-Path $gtfsRou) -and (Test-Path $gtfsAdd))) { Write-Err "Failed to create GTFS outputs"; throw "gtfs failed" }
        Write-Success "GTFS processing completed successfully"
    }

    Write-Success "Preprocessing completed successfully!"
    Run-Simulations -PythonCmd $pythonCmd -NetFile $netFile -ZonesTaz $tazFile -GtfsVtypes $vtypes -GtfsAdd $gtfsAdd -GtfsRou $gtfsRou -SimDir $OUT_SIM
}

function Run-Simulations {
    param([string]$PythonCmd, [string]$NetFile, [string]$ZonesTaz, [string]$GtfsVtypes, [string]$GtfsAdd, [string]$GtfsRou, [string]$SimDir)
    Write-Info "Starting simulation batch..."

    $BASE_SEED = 12345
    $VALUES = @()
    for ($v=1000; $v -le 33000; $v+=1000) { $VALUES += $v }
    for ($v=36000; $v -le 58000; $v+=2000) { $VALUES += $v }

    $odVarDir = Join-Path $SimDir "od_variants"
    New-Item -Path $odVarDir -ItemType Directory -Force | Out-Null
    $logDir = Join-Path $SimDir "logs"
    New-Item -Path $logDir -ItemType Directory -Force | Out-Null

    Write-Info "Creating OD matrix variants..."
    $template = Get-Content -Path "private_traffic.od" -Raw
    foreach ($value in $VALUES) {
        $content = $template -replace '\b10000\b', [string]$value
        Set-Content -Path (Join-Path $odVarDir ("private_{0}.od" -f $value)) -Value $content -Encoding UTF8
    }
    Write-Success "OD variants created"

    if (-not (Test-Path $NetFile)) { Write-Err "Network file not found: $NetFile"; throw "net file missing" }

    $jobs = @()
    $hadFailures = $false

    # Baseline jobs (public transport only, no private traffic)
    for ($sim=1; $sim -le $SIMS_PER_VALUE; $sim++) {
        $SEED = $BASE_SEED + $sim
        $baselineStop = Join-Path $SimDir ("stop_events_baseline_${sim}.xml")
        if (Test-Path $baselineStop) {
            $validBase = $true
            try { [xml](Get-Content -LiteralPath $baselineStop -Raw) | Out-Null } catch { $validBase = $false }
            if ($validBase -and (Get-Item $baselineStop).Length -gt 500) {
                Write-Warn ("Baseline already exists and is valid, skipping: {0}" -f $baselineStop)
                continue
            } else {
                Write-Warn ("Existing baseline is missing/invalid, regenerating: {0}" -f $baselineStop)
                try { Remove-Item -LiteralPath $baselineStop -Force -ErrorAction Stop } catch {}
            }
        }
        $job = Start-Job -ScriptBlock {
            param($sim,$SEED,$CITY_NAME,$NetFile,$GtfsVtypes,$GtfsAdd,$GtfsRou,$SimDir,$baselineStop,$logDir)
            $ErrorActionPreference = 'Continue'
            Set-Location $SimDir
            if (-not (Test-Path $NetFile)) { throw "net file missing in job" }
            if (-not (Test-Path $GtfsVtypes)) { throw "pt_vtypes missing" }
            if (-not (Test-Path $GtfsAdd)) { throw "gtfs additional missing" }
            if (-not (Test-Path $GtfsRou)) { throw "gtfs routes missing" }
            $sumoLog = Join-Path $logDir ("baseline_${sim}.log")
            $baselineStopTmp = "$baselineStop.tmp"
            if (Test-Path $baselineStopTmp) { try { Remove-Item -LiteralPath $baselineStopTmp -Force -ErrorAction Stop } catch {} }
            Write-Host "[INFO] Starting baseline simulation for sim=$sim, seed=$SEED" -ForegroundColor Cyan
            sumo -n "$NetFile" --additional "$GtfsVtypes,$GtfsAdd" --routes "$GtfsRou" `
                 --begin 21600 --end 39600 --seed $SEED --stop-output "$baselineStopTmp" --ignore-route-errors `
                 --log "$sumoLog" 2>&1 | Write-Host
            if ($LASTEXITCODE -ne 0) { throw "sumo baseline failed for sim=$sim" }
            # Validate stop XML
            if (-not (Test-Path $baselineStopTmp)) { throw "baseline stop file missing" }
            try { [xml](Get-Content -LiteralPath $baselineStopTmp -Raw) | Out-Null } catch { throw "baseline stop xml invalid" }
            try { Move-Item -LiteralPath $baselineStopTmp -Destination $baselineStop -Force } catch { throw "failed to finalize baseline stop file" }
            Write-Host "[SUCCESS] Baseline completed: sim=$sim" -ForegroundColor Green
        } -ArgumentList $sim,$SEED,$CITY_NAME,$NetFile,$GtfsVtypes,$GtfsAdd,$GtfsRou,$SimDir,$baselineStop,$logDir

        $jobs += $job
        if ($jobs.Count -ge $MAX_JOBS) {
            $done = Wait-Job -Any $jobs
            $done = @($done)
            foreach ($j in $done) {
                Receive-Job $j -ErrorAction Continue | Out-Host
                if ($j.State -ne 'Completed') { $hadFailures = $true }
                Remove-Job $j
                $jobs = @($jobs | Where-Object { $_.Id -ne $j.Id })
            }
        }
    }
    foreach ($value in $VALUES) {
        for ($sim=1; $sim -le $SIMS_PER_VALUE; $sim++) {
            $SEED = $BASE_SEED + $sim + $value
            $stopOutput = Join-Path $SimDir ("stop_events_${value}_${sim}.xml")
            $simOutput  = Join-Path $SimDir ("4_${value}_${sim}_${CITY_NAME}_sim_output.xml")
            $simOk = $false; $stopOk = $false
            if (Test-Path $simOutput) {
                try { [xml](Get-Content -LiteralPath $simOutput -Raw) | Out-Null; if ((Get-Item $simOutput).Length -gt 1000) { $simOk = $true } } catch {}
                if (-not $simOk) { try { Remove-Item -LiteralPath $simOutput -Force -ErrorAction Stop } catch {} }
            }
            if (Test-Path $stopOutput) {
                try { [xml](Get-Content -LiteralPath $stopOutput -Raw) | Out-Null; if ((Get-Item $stopOutput).Length -gt 200) { $stopOk = $true } } catch {}
                if (-not $stopOk) { try { Remove-Item -LiteralPath $stopOutput -Force -ErrorAction Stop } catch {} }
            }
            if ($simOk -and $stopOk) {
                Write-Warn ("Outputs already exist and are valid, skipping: {0}; {1}" -f $simOutput,$stopOutput)
                continue
            }
            $job = Start-Job -ScriptBlock {
                param($value,$sim,$SEED,$CITY_NAME,$NetFile,$ZonesTaz,$GtfsVtypes,$GtfsAdd,$GtfsRou,$SimDir,$odVarDir,$stopOutput,$simOutput,$logDir)
                $ErrorActionPreference = 'Continue'
                Set-Location $SimDir
                $odFile = Join-Path $odVarDir ("private_${value}.od")
                $tripFile = Join-Path $SimDir ("4_${value}_${sim}_private_for.trips.xml")
                $routeFile = Join-Path $SimDir ("4_${value}_${sim}_private.rou.xml")
                $tripFileTmp = "$tripFile.tmp"
                $routeFileTmp = "$routeFile.tmp"
                $stopOutputTmp = "$stopOutput.tmp"
                $simOutputTmp  = "$simOutput.tmp"

                foreach ($tmp in @($tripFileTmp,$routeFileTmp,$stopOutputTmp,$simOutputTmp)) {
                    if (Test-Path $tmp) { try { Remove-Item -LiteralPath $tmp -Force -ErrorAction Stop } catch {} }
                }

                Write-Host "[INFO] Starting simulation #$sim for value=$value, seed=$SEED" -ForegroundColor Cyan

                if (-not (Test-Path $ZonesTaz)) { throw "Zones TAZ missing" }
                if (-not (Test-Path $odFile)) { throw "OD file missing: $odFile" }
                if ((Test-Path $tripFile) -and ((Get-Item $tripFile).Length -gt 500)) {
                    Write-Host "[INFO] Reusing existing trips: $tripFile" -ForegroundColor Yellow
                } else {
                    $odLog = Join-Path $logDir ("od2trips_${value}_${sim}.log")
                    od2trips --taz-files "$ZonesTaz" --od-matrix-files "$odFile" --seed $SEED -o "$tripFileTmp" 2>&1 | Tee-Object -FilePath $odLog -Append | Write-Host
                    if ($LASTEXITCODE -ne 0) { throw "od2trips failed for value=$value sim=$sim" }
                    if (-not (Test-Path $tripFileTmp)) { throw "trip file missing" }
                    if ((Get-Item $tripFileTmp).Length -lt 500) { throw "trip file too small" }
                    try { Move-Item -LiteralPath $tripFileTmp -Destination $tripFile -Force } catch { throw "failed to finalize trip file" }
                }

                if ((Test-Path $routeFile) -and ((Get-Item $routeFile).Length -gt 500)) {
                    Write-Host "[INFO] Reusing existing routes: $routeFile" -ForegroundColor Yellow
                } else {
                    $duaLog = Join-Path $logDir ("duarouter_${value}_${sim}.log")
                    duarouter -n "$NetFile" --route-files "$tripFile" --seed $SEED -o "$routeFileTmp" --ignore-errors --repair 2>&1 | Tee-Object -FilePath $duaLog -Append | Write-Host
                    if ($LASTEXITCODE -ne 0) { throw "duarouter failed for value=$value sim=$sim" }
                    if (-not (Test-Path $routeFileTmp)) { throw "route file missing" }
                    if ((Get-Item $routeFileTmp).Length -lt 500) { throw "route file too small" }
                    try { Move-Item -LiteralPath $routeFileTmp -Destination $routeFile -Force } catch { throw "failed to finalize route file" }
                }

                # Run mixed simulation: PT routes + private routes
                $sumoLog = Join-Path $logDir ("sumo_${value}_${sim}.log")
                sumo -n "$NetFile" --additional "$GtfsVtypes,$GtfsAdd" --routes "$GtfsRou,$routeFile" `
                     --begin 21600 --end 39600 --seed $SEED --tripinfo-output "$simOutputTmp" --tripinfo-output.write-unfinished true `
                     --stop-output "$stopOutputTmp" --ignore-route-errors --log "$sumoLog" 2>&1 | Write-Host
                if ($LASTEXITCODE -ne 0) { throw "sumo failed for value=$value sim=$sim" }
                # Validate outputs
                if (-not (Test-Path $simOutputTmp)) { throw "sim output missing" }
                if ((Get-Item $simOutputTmp).Length -lt 1000) { throw "sim output too small" }
                try { [xml](Get-Content -LiteralPath $simOutputTmp -Raw) | Out-Null } catch { throw "sim output xml invalid" }
                if (-not (Test-Path $stopOutputTmp)) { throw "stop output missing" }
                try { [xml](Get-Content -LiteralPath $stopOutputTmp -Raw) | Out-Null } catch { throw "stop output xml invalid" }
                try { Move-Item -LiteralPath $simOutputTmp -Destination $simOutput -Force } catch { throw "failed to finalize sim output" }
                try { Move-Item -LiteralPath $stopOutputTmp -Destination $stopOutput -Force } catch { throw "failed to finalize stop output" }

                Write-Host "[SUCCESS] Completed: value=$value sim=$sim" -ForegroundColor Green
            } -ArgumentList $value,$sim,$SEED,$CITY_NAME,$NetFile,$ZonesTaz,$GtfsVtypes,$GtfsAdd,$GtfsRou,$SimDir,$odVarDir,$stopOutput,$simOutput,$logDir

            $jobs += $job
            if ($jobs.Count -ge $MAX_JOBS) {
                $done = Wait-Job -Any $jobs
                $done = @($done)
            foreach ($j in $done) {
                Receive-Job $j -ErrorAction Continue | Out-Host
                if ($j.State -ne 'Completed') { $hadFailures = $true }
                Remove-Job $j
                $jobs = @($jobs | Where-Object { $_.Id -ne $j.Id })
            }
            }
        }
    }
    while (@($jobs).Count -gt 0) {
        $done = Wait-Job -Any $jobs
        $done = @($done)
        foreach ($j in $done) {
            Receive-Job $j -ErrorAction Continue | Out-Host
            if ($j.State -ne 'Completed') { $hadFailures = $true }
            Remove-Job $j
            $jobs = @($jobs | Where-Object { $_.Id -ne $j.Id })
        }
    }
    if ($hadFailures) { throw "A simulation job failed." }
    
    Write-Success "All simulations for all values completed!"

    # Build Excel analysis automatically
    try {
        $OUT_ROOT = Split-Path -Parent $SimDir
        $OUT_ANALYSIS = Join-Path $OUT_ROOT "analysis"
        New-Item -ItemType Directory -Path $OUT_ANALYSIS -Force | Out-Null
        $excelPath = Join-Path $OUT_ANALYSIS "pt_delay.xlsx"
        if (Test-Path $excelPath) {
            try {
                Remove-Item -Path $excelPath -Force -ErrorAction Stop
            } catch {
                Write-Warn ("Existing Excel locked, writing to a new file. Details: {0}" -f $_.Exception.Message)
                $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
                $excelPath = Join-Path $OUT_ANALYSIS ("pt_delay_{0}.xlsx" -f $ts)
            }
        }
        $exportScript = Join-Path (Get-Location) "export_pt_delay_excel.py"
        Write-Info ("Exporting delay analysis to: {0}" -f $excelPath)
        & $PythonCmd $exportScript --simdir "$SimDir" --sims $SIMS_PER_VALUE --out "$excelPath" | Write-Host
        if ($LASTEXITCODE -eq 0 -and (Test-Path $excelPath)) {
            Write-Success "Delay analysis Excel generated"
            # Auto-run plotting script to produce figures
            $plotScript = Join-Path (Get-Location) "plot_pt_delay.py"
            if (Test-Path $plotScript) {
                $outPng   = Join-Path $OUT_ANALYSIS "pt_delay.png"
                $outHeat  = Join-Path $OUT_ANALYSIS "pt_delay_heat.png"
                $outFan   = Join-Path $OUT_ANALYSIS "pt_delay_fan.png"
                $outBox   = Join-Path $OUT_ANALYSIS "pt_delay_box.png"
                $outRange = Join-Path $OUT_ANALYSIS "pt_delay_range.png"
                Write-Info ("Generating plots to: {0}" -f $outPng)
                & $PythonCmd $plotScript --excel "$excelPath" --out "$outPng" --out-heat "$outHeat" --out-fan "$outFan" --out-box "$outBox" --out-range "$outRange" | Write-Host
                if ($LASTEXITCODE -eq 0 -and (Test-Path $outPng)) {
                    Write-Success "Plots generated"
                } else {
                    Write-Warn ("Plotting failed (exit={0})." -f $LASTEXITCODE)
                }
            } else {
                Write-Warn "plot_pt_delay.py not found; skipping plotting step"
            }
        } else {
            Write-Err ("Export failed (exit={0})." -f $LASTEXITCODE)
        }
    } catch {
        Write-Warn ("Failed to export Excel: {0}" -f $_.Exception.Message)
    }
    }


function Main {
    Write-Host "========================================="
    Write-Host "    Automated SUMO Workflow (Windows)    "
    Write-Host "========================================="
    Write-Host ""

    Resolve-SUMO
    $pythonCmd = Get-PythonCommand
    Ensure-RequestsInstalled -pythonCmd $pythonCmd
    Ensure-GtfsDeps -pythonCmd $pythonCmd

    Get-UserInput
    Create-PythonScripts
    Create-ConfigFiles
    Run-Workflow -pythonCmd $pythonCmd

    Write-Success "Workflow completed successfully!"
    Write-Info "Output files are available in the current directory"
}

Main


