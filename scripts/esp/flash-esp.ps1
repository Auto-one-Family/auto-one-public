#Requires -Version 5.1
<#
.SYNOPSIS
    Flash ESP32 firmware from PowerShell with correct paths.
.DESCRIPTION
    Uses PlatformIO from user profile. Run from project root (Auto-one) or pass -ProjectRoot.
    Environments: esp32_dev (generic), seeed_xiao_esp32c3 (Xiao C3)
.EXAMPLE
    .\scripts\esp\flash-esp.ps1
    .\scripts\esp\flash-esp.ps1 -Environment seeed_xiao_esp32c3
    .\scripts\esp\flash-esp.ps1 -BuildOnly
#>

param(
    [string]$ProjectRoot,
    [ValidateSet("esp32_dev", "seeed_xiao_esp32c3")]
    [string]$Environment = "esp32_dev",
    [switch]$BuildOnly,
    [switch]$ListPorts
)

if (-not $ProjectRoot) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$ElTrabajante = Join-Path $ProjectRoot "El Trabajante"
$PioExe = Join-Path $env:USERPROFILE ".platformio\penv\Scripts\pio.exe"

if (-not (Test-Path $PioExe)) {
    Write-Error "PlatformIO not found at: $PioExe"
    Write-Host "Install: pip install platformio  OR  use VS Code PlatformIO IDE (creates this path)."
    exit 1
}

if (-not (Test-Path (Join-Path $ElTrabajante "platformio.ini"))) {
    Write-Error "ESP32 project not found at: $ElTrabajante"
    exit 1
}

if ($ListPorts) {
    & $PioExe device list -d $ElTrabajante
    exit $LASTEXITCODE
}

if ($BuildOnly) {
    & $PioExe run -d $ElTrabajante -e $Environment
    exit $LASTEXITCODE
}

# Upload (flash)
& $PioExe run -d $ElTrabajante -e $Environment -t upload
exit $LASTEXITCODE
