<#
.SYNOPSIS
    Starts the complete Wokwi development environment.

.DESCRIPTION
    This script starts all components needed for Wokwi ESP32 simulation:
    1. Mosquitto MQTT Broker (Docker)
    2. God-Kaiser Server (FastAPI)
    3. Wokwi ESP32 Simulation (optional)

.PARAMETER SkipWokwi
    Start only Mosquitto and Server, skip Wokwi simulation.

.PARAMETER BuildFirmware
    Build the Wokwi firmware before starting simulation.

.EXAMPLE
    .\start-wokwi-dev.ps1
    # Starts everything including Wokwi

.EXAMPLE
    .\start-wokwi-dev.ps1 -SkipWokwi
    # Starts only Mosquitto and Server

.EXAMPLE
    .\start-wokwi-dev.ps1 -BuildFirmware
    # Builds firmware first, then starts everything
#>

param(
    [switch]$SkipWokwi,
    [switch]$BuildFirmware
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Wokwi Development Environment Startup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "[1/5] Checking prerequisites..." -ForegroundColor Yellow

# Check Docker
try {
    docker --version | Out-Null
    Write-Host "  [OK] Docker available" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Docker not found. Install Docker Desktop." -ForegroundColor Red
    exit 1
}

# Check Poetry
try {
    poetry --version | Out-Null
    Write-Host "  [OK] Poetry available" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] Poetry not found. Install: pip install poetry" -ForegroundColor Red
    exit 1
}

# Check PlatformIO (for firmware build)
if ($BuildFirmware -or -not $SkipWokwi) {
    $pioPath = "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe"
    if (Test-Path $pioPath) {
        Write-Host "  [OK] PlatformIO available" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] PlatformIO not found at expected path" -ForegroundColor Yellow
    }
}

# Check Wokwi CLI Token
if (-not $SkipWokwi) {
    if (-not $env:WOKWI_CLI_TOKEN) {
        Write-Host ""
        Write-Host "  [WARN] WOKWI_CLI_TOKEN not set!" -ForegroundColor Yellow
        Write-Host "  Get your token from: https://wokwi.com/dashboard/ci" -ForegroundColor Yellow
        Write-Host "  Set it with: `$env:WOKWI_CLI_TOKEN = 'your_token'" -ForegroundColor Yellow
        Write-Host ""
        $SkipWokwi = $true
    } else {
        Write-Host "  [OK] WOKWI_CLI_TOKEN set" -ForegroundColor Green
    }
}

Write-Host ""

# Step 2: Start Mosquitto
Write-Host "[2/5] Starting Mosquitto MQTT Broker..." -ForegroundColor Yellow

# Check if Mosquitto container exists
$mosquittoRunning = docker ps --filter "name=mosquitto-wokwi" --format "{{.Names}}" 2>$null

if ($mosquittoRunning -eq "mosquitto-wokwi") {
    Write-Host "  [OK] Mosquitto already running" -ForegroundColor Green
} else {
    # Remove old container if exists
    docker rm -f mosquitto-wokwi 2>$null | Out-Null

    # Start Mosquitto with anonymous access (for development)
    docker run -d `
        --name mosquitto-wokwi `
        -p 1883:1883 `
        -e "MOSQUITTO_USERNAME=" `
        eclipse-mosquitto:2 `
        mosquitto -c /mosquitto-no-auth.conf 2>$null

    if ($LASTEXITCODE -ne 0) {
        # Try with custom config allowing anonymous
        $mosquittoConf = @"
listener 1883
allow_anonymous true
"@
        $tempConf = [System.IO.Path]::GetTempFileName()
        $mosquittoConf | Out-File -FilePath $tempConf -Encoding ASCII

        docker run -d `
            --name mosquitto-wokwi `
            -p 1883:1883 `
            -v "${tempConf}:/mosquitto/config/mosquitto.conf" `
            eclipse-mosquitto:2

        Remove-Item $tempConf -ErrorAction SilentlyContinue
    }

    Start-Sleep -Seconds 2
    Write-Host "  [OK] Mosquitto started on port 1883" -ForegroundColor Green
}

Write-Host ""

# Step 3: Seed Wokwi ESP
Write-Host "[3/5] Ensuring Wokwi ESP exists in database..." -ForegroundColor Yellow

Push-Location "$ProjectRoot\El Servador\god_kaiser_server"
try {
    poetry run python scripts/seed_wokwi_esp.py 2>&1 | ForEach-Object {
        if ($_ -match "already exists|created") {
            Write-Host "  [OK] $_" -ForegroundColor Green
        }
    }
} catch {
    Write-Host "  [WARN] Could not seed Wokwi ESP: $_" -ForegroundColor Yellow
}
Pop-Location

Write-Host ""

# Step 4: Build Firmware (optional)
if ($BuildFirmware) {
    Write-Host "[4/5] Building Wokwi firmware..." -ForegroundColor Yellow
    Push-Location "$ProjectRoot\El Trabajante"
    try {
        & $pioPath run -e wokwi_simulation
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] Firmware built successfully" -ForegroundColor Green
        } else {
            Write-Host "  [ERROR] Firmware build failed" -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "  [ERROR] Firmware build failed: $_" -ForegroundColor Red
        exit 1
    }
    Pop-Location
} else {
    Write-Host "[4/5] Skipping firmware build (use -BuildFirmware to build)" -ForegroundColor Gray
}

Write-Host ""

# Step 5: Start Server and optionally Wokwi
Write-Host "[5/5] Starting services..." -ForegroundColor Yellow
Write-Host ""

if ($SkipWokwi) {
    Write-Host "Starting God-Kaiser Server only..." -ForegroundColor Cyan
    Write-Host "  Server will be available at: http://localhost:8000" -ForegroundColor White
    Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor White
    Write-Host ""
    Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
    Write-Host ""

    Push-Location "$ProjectRoot\El Servador\god_kaiser_server"
    poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    Pop-Location
} else {
    Write-Host "Starting God-Kaiser Server and Wokwi in parallel..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Server: http://localhost:8000" -ForegroundColor White
    Write-Host "  Wokwi ESP: ESP_WOKWI001 (will appear in Frontend when connected)" -ForegroundColor White
    Write-Host ""

    # Start server in background
    $serverJob = Start-Job -ScriptBlock {
        param($projectRoot)
        Set-Location "$projectRoot\El Servador\god_kaiser_server"
        poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    } -ArgumentList $ProjectRoot

    Write-Host "  [OK] Server starting in background (Job ID: $($serverJob.Id))" -ForegroundColor Green

    # Wait for server to be ready
    Write-Host "  Waiting for server to be ready..." -ForegroundColor Gray
    $maxWait = 30
    $waited = 0
    while ($waited -lt $maxWait) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 1 -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Host "  [OK] Server is ready" -ForegroundColor Green
                break
            }
        } catch {
            Start-Sleep -Seconds 1
            $waited++
        }
    }

    if ($waited -ge $maxWait) {
        Write-Host "  [WARN] Server may not be fully ready yet" -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Starting Wokwi simulation..." -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop both Server and Wokwi." -ForegroundColor Yellow
    Write-Host ""

    Push-Location "$ProjectRoot\El Trabajante"
    try {
        wokwi-cli . --timeout 0
    } finally {
        # Cleanup
        Write-Host ""
        Write-Host "Stopping server..." -ForegroundColor Yellow
        Stop-Job $serverJob -ErrorAction SilentlyContinue
        Remove-Job $serverJob -ErrorAction SilentlyContinue
    }
    Pop-Location
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Environment stopped." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
