#Requires -Version 5.1
<#
.SYNOPSIS
    System Health Aggregator for AutomationOne Debug Infrastructure.
.DESCRIPTION
    Checks all services and outputs structured JSON for agent consumption.
    Run from project root or let it auto-detect via script location.
.OUTPUTS
    JSON object with overall status, per-service details, and issues list.
.EXAMPLE
    powershell.exe -File scripts/debug/debug-status.ps1
#>

param(
    [string]$ProjectRoot
)

if (-not $ProjectRoot) {
    $parent = Join-Path $PSScriptRoot ".."
    $ProjectRoot = (Resolve-Path (Join-Path $parent "..")).Path
}

$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Test-TcpPort {
    param([string]$Hostname, [int]$Port, [int]$TimeoutMs = 2000)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync($Hostname, $Port)
        $connected = $task.Wait($TimeoutMs)
        $client.Close()
        $client.Dispose()
        return $connected
    }
    catch {
        return $false
    }
}

function Invoke-HttpCheck {
    param([string]$Uri, [int]$TimeoutSec = 3)
    # Try Invoke-WebRequest first, fall back to System.Net.WebClient
    # PowerShell 5.1 Invoke-WebRequest can fail on plain-text responses or proxy issues
    try {
        $resp = Invoke-WebRequest -Uri $Uri -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        return @{ ok = $true; code = [int]$resp.StatusCode; body = [string]$resp.Content }
    }
    catch {
        # Fallback: System.Net.WebClient (no proxy interference, handles plain-text)
        try {
            $wc = New-Object System.Net.WebClient
            $body = $wc.DownloadString($Uri)
            $wc.Dispose()
            return @{ ok = $true; code = 200; body = [string]$body }
        }
        catch {
            return @{ ok = $false; error = $_.Exception.Message }
        }
    }
}

function Invoke-JsonEndpoint {
    param([string]$Uri, [int]$TimeoutSec = 3, [hashtable]$Headers = @{})
    # Try Invoke-RestMethod first, fall back to System.Net.WebClient
    # PowerShell 5.1 can timeout via WinHTTP proxy on localhost endpoints
    try {
        $params = @{
            Uri = $Uri
            TimeoutSec = $TimeoutSec
            ErrorAction = "Stop"
        }
        if ($Headers.Count -gt 0) {
            $params.Headers = $Headers
        }
        $data = Invoke-RestMethod @params
        return @{ ok = $true; data = $data }
    }
    catch {
        # Fallback: System.Net.WebClient (bypasses WinHTTP proxy)
        try {
            $wc = New-Object System.Net.WebClient
            if ($Headers.Count -gt 0) {
                foreach ($entry in $Headers.GetEnumerator()) {
                    $wc.Headers.Add($entry.Key, $entry.Value)
                }
            }
            $body = $wc.DownloadString($Uri)
            $wc.Dispose()
            $data = $body | ConvertFrom-Json
            return @{ ok = $true; data = $data }
        }
        catch {
            return @{ ok = $false; error = $_.Exception.Message }
        }
    }
}

function Get-LokiLastLogAgeSeconds {
    param([string]$LogQuery, [int]$TimeoutSec = 5)
    # Use 127.0.0.1 to avoid WinHTTP proxy/localhost timeout on Windows (see LOG_LOCATIONS.md §12)
    $lokiBase = if ($env:LOKI_URL) { $env:LOKI_URL } else { "http://127.0.0.1:3100" }
    $nowNs = [long]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) * 1000000
    $encodedQuery = [Uri]::EscapeDataString($LogQuery)
    $uri = "$lokiBase/loki/api/v1/query_range?query=$encodedQuery&limit=1&direction=backward&end=$nowNs"
    $resp = Invoke-JsonEndpoint -Uri $uri -TimeoutSec $TimeoutSec
    if (-not $resp.ok) {
        return -1
    }
    $lokiData = $resp.data
    if (-not $lokiData -or -not $lokiData.data -or -not $lokiData.data.result) {
        return -1
    }
    $values = $lokiData.data.result | Select-Object -First 1 | ForEach-Object { $_.values }
    if ($values -and $values.Count -gt 0) {
        # Loki timestamps are nanosecond strings; parse as [double] to avoid PS 5.1 int64 precision loss
        $tsNs = [double]([string]$values[0][0])
        $ageSeconds = [long](($nowNs - $tsNs) / 1000000000)
        # Sanity check: age must be positive and reasonable (< 30 days = 2592000)
        if ($ageSeconds -ge 0 -and $ageSeconds -lt 2592000) {
            return [int]$ageSeconds
        }
        return -1
    }
    return -1
}

# ---------------------------------------------------------------------------
# Result object
# ---------------------------------------------------------------------------

$result = [ordered]@{
    timestamp = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    overall   = "ok"
    services  = [ordered]@{}
    issues    = @()
}

# ---------------------------------------------------------------------------
# 1. Docker Containers
# ---------------------------------------------------------------------------

$dockerLines = docker compose --project-directory $ProjectRoot ps --format json 2>$null
$containers = @()
if ($dockerLines) {
    foreach ($line in $dockerLines) {
        if ($line.Trim()) {
            $containers += ($line | ConvertFrom-Json)
        }
    }
}

$running  = @($containers | Where-Object { $_.State -eq "running" }).Count
$stopped  = @($containers | Where-Object { $_.State -ne "running" }).Count
$restarts = @()

foreach ($c in $containers) {
    $name = $c.Name
    $rc = docker inspect --format '{{.RestartCount}}' $name 2>$null
    if ($rc -and [int]$rc -gt 2) {
        $restarts += "$($c.Service): $rc restarts"
    }
}

$result.services.docker = [ordered]@{
    status     = if ($running -gt 0) { "ok" } else { "error" }
    containers = [ordered]@{ running = $running; stopped = $stopped; total = $containers.Count }
}

if ($stopped -gt 0) {
    $stoppedNames = @($containers | Where-Object { $_.State -ne "running" } | ForEach-Object { $_.Service }) -join ", "
    $result.issues += "docker: $stopped container(s) not running ($stoppedNames)"
}
foreach ($r in $restarts) {
    $result.issues += $r
}

# ---------------------------------------------------------------------------
# 2. Server Health
# ---------------------------------------------------------------------------

$live     = Invoke-HttpCheck "http://localhost:8000/api/v1/health/live"
$detailed = Invoke-JsonEndpoint "http://localhost:8000/api/v1/health/detailed"

$result.services.server = [ordered]@{
    status = if ($live.ok) { "ok" } else { "error" }
    live   = $live.ok
}

if ($detailed.ok) {
    $result.services.server.uptime = $detailed.data.uptime
}

if (-not $live.ok) {
    $result.issues += "server: /health/live unreachable"
}

# ---------------------------------------------------------------------------
# 3. PostgreSQL
# ---------------------------------------------------------------------------

$pgResult = docker compose --project-directory $ProjectRoot exec -T postgres pg_isready -U god_kaiser -d god_kaiser_db 2>$null
$pgOk = ($LASTEXITCODE -eq 0)

$pgConnections = $null
if ($pgOk) {
    $pgConnections = docker compose --project-directory $ProjectRoot exec -T postgres psql -U god_kaiser -d god_kaiser_db -t -c "SELECT count(*) FROM pg_stat_activity;" 2>$null
    if ($pgConnections) { $pgConnections = $pgConnections.Trim() }
}

$pgSize = $null
if ($pgOk) {
    $pgSize = docker compose --project-directory $ProjectRoot exec -T postgres psql -U god_kaiser -d god_kaiser_db -t -c "SELECT pg_size_pretty(pg_database_size('god_kaiser_db'));" 2>$null
    if ($pgSize) { $pgSize = $pgSize.Trim() }
}

$result.services.postgres = [ordered]@{
    status      = if ($pgOk) { "ok" } else { "error" }
    connections = $pgConnections
    db_size     = $pgSize
}

if (-not $pgOk) {
    $result.issues += "postgres: not ready"
}

# ---------------------------------------------------------------------------
# 4. MQTT Broker
# ---------------------------------------------------------------------------

$mqttPort = Test-TcpPort "localhost" 1883

$result.services.mqtt = [ordered]@{
    status    = if ($mqttPort) { "ok" } else { "error" }
    port_open = $mqttPort
}

if (-not $mqttPort) {
    $result.issues += "mqtt: port 1883 not reachable"
}

# ---------------------------------------------------------------------------
# 5. Frontend
# ---------------------------------------------------------------------------

$frontendPort = Test-TcpPort "localhost" 5173

$result.services.frontend = [ordered]@{
    status    = if ($frontendPort) { "ok" } else { "error" }
    port_open = $frontendPort
}

if (-not $frontendPort) {
    $result.issues += "frontend: port 5173 not reachable"
}

# ---------------------------------------------------------------------------
# 6. Loki
# ---------------------------------------------------------------------------

# Use 127.0.0.1 to avoid WinHTTP proxy/localhost timeout on Windows; 5s for Loki startup response
$lokiReady = Invoke-HttpCheck "http://127.0.0.1:3100/ready" -TimeoutSec 5
$lokiOk = ($lokiReady.ok -and ([string]$lokiReady.body) -match "ready")
$lokiLastAge = -1
if ($lokiOk) {
    # Promtail labels: container, compose_service (ROADMAP §1.1) – not container_name
    $lokiLastAge = Get-LokiLastLogAgeSeconds -LogQuery '{container=~"automationone-.+"}'
}

$result.services.loki = [ordered]@{
    status               = if ($lokiOk) { "ok" } else { "error" }
    ready                = $lokiOk
    last_log_age_seconds = $lokiLastAge
}

if (-not $lokiOk) {
    $result.issues += "loki: not ready"
}

# ---------------------------------------------------------------------------
# 7. MQTT Broker Logs (via Loki; no separate mqtt-logger container)
# ---------------------------------------------------------------------------

$mqttBrokerLogAge = -1
if ($lokiOk) {
    $mqttBrokerLogAge = Get-LokiLastLogAgeSeconds -LogQuery '{compose_service="mqtt-broker"}'
}

$result.services.mqtt_broker_logs = [ordered]@{
    status                 = if ($lokiOk) { "ok" } else { "n/a" }
    last_log_age_seconds   = $mqttBrokerLogAge
}

# ---------------------------------------------------------------------------
# 8. Prometheus
# ---------------------------------------------------------------------------

$promReady = Invoke-HttpCheck "http://localhost:9090/-/ready"

$result.services.prometheus = [ordered]@{
    status = if ($promReady.ok) { "ok" } else { "error" }
}

if (-not $promReady.ok) {
    $result.issues += "prometheus: not ready"
}

# ---------------------------------------------------------------------------
# 9. Grafana
# ---------------------------------------------------------------------------

# Grafana requires auth for API endpoints (anonymous access disabled)
$grafanaAuthHeader = @{ Authorization = "Basic " + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("admin:admin")) }
$grafana = Invoke-JsonEndpoint "http://localhost:3000/api/health" -Headers $grafanaAuthHeader

$result.services.grafana = [ordered]@{
    status  = if ($grafana.ok) { "ok" } else { "error" }
    version = if ($grafana.ok) { $grafana.data.version } else { $null }
}

if (-not $grafana.ok) {
    $result.issues += "grafana: not ready"
}

# ---------------------------------------------------------------------------
# 10. Log Availability
# ---------------------------------------------------------------------------

$logChecks = [ordered]@{}
$logsBase = Join-Path $ProjectRoot "logs"
$logDirs = @{
    server   = Join-Path $logsBase "server"
    mqtt     = Join-Path $logsBase "mqtt"
    postgres = Join-Path $logsBase "postgres"
}

foreach ($entry in $logDirs.GetEnumerator()) {
    $dirPath = $entry.Value
    if (Test-Path $dirPath) {
        $files = @(Get-ChildItem $dirPath -Filter "*.log" -ErrorAction SilentlyContinue)
        $newestAge = -1
        if ($files.Count -gt 0) {
            $newest = $files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
            $newestAge = [int]((Get-Date) - $newest.LastWriteTime).TotalSeconds
        }
        $logChecks[$entry.Key] = [ordered]@{
            exists             = $true
            file_count         = $files.Count
            newest_age_seconds = $newestAge
        }
    }
    else {
        $logChecks[$entry.Key] = [ordered]@{
            exists             = $false
            file_count         = 0
            newest_age_seconds = -1
        }
    }
}

$result.services.logs = $logChecks

# ---------------------------------------------------------------------------
# 11. Alembic Migration
# ---------------------------------------------------------------------------

$alembicCurrent = docker compose --project-directory $ProjectRoot exec -T el-servador alembic current 2>$null
if ($alembicCurrent) {
    $result.services.alembic = [ordered]@{
        status  = "ok"
        current = ($alembicCurrent | Select-Object -Last 1).Trim()
    }
}
else {
    $result.services.alembic = [ordered]@{
        status = "unknown"
    }
}

# ---------------------------------------------------------------------------
# 12. Disk Usage
# ---------------------------------------------------------------------------

$dockerDf = docker system df --format '{{.Type}}\t{{.Size}}\t{{.Reclaimable}}' 2>$null
$diskInfo = [ordered]@{}
if ($dockerDf) {
    foreach ($line in $dockerDf) {
        $parts = $line -split "\t"
        if ($parts.Count -ge 3) {
            $diskInfo[$parts[0]] = [ordered]@{
                size        = $parts[1]
                reclaimable = $parts[2]
            }
        }
    }
}
$result.services.disk = $diskInfo

# ---------------------------------------------------------------------------
# Determine overall status
# ---------------------------------------------------------------------------

$coreServices = @("server", "postgres", "mqtt")
$monitoringServices = @("loki", "prometheus", "grafana")

$coreDown = @($coreServices | Where-Object { $result.services[$_].status -eq "error" })
$monitoringDown = @($monitoringServices | Where-Object { $result.services[$_].status -ne "ok" })

if ($coreDown.Count -gt 0) {
    $result.overall = "critical"
}
elseif ($monitoringDown.Count -gt 0) {
    $result.overall = "degraded"
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

$result | ConvertTo-Json -Depth 5
