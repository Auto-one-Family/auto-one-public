#Requires -Version 5.1
<#
.SYNOPSIS
    AutomationOne — Loki Query Helper (PowerShell)
.DESCRIPTION
    Convenience wrapper for Loki API queries. Windows-native alternative to loki-query.sh.
    Requires: make monitor-up (Loki on localhost:3100)
.PARAMETER Command
    errors | trace | esp | health
.PARAMETER Arg1
    For errors: minutes (default 5). For trace/esp: correlation-id or esp-id.
.EXAMPLE
    .\loki-query.ps1 errors 5
    .\loki-query.ps1 trace abc-123-def
    .\loki-query.ps1 esp ESP_12AB34CD
    .\loki-query.ps1 health
#>

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("errors", "trace", "esp", "health")]
    [string]$Command,

    [Parameter(Position = 1)]
    [string]$Arg1 = "5"
)

$ErrorActionPreference = "SilentlyContinue"
# Prefer 127.0.0.1 on Windows to avoid WinHTTP proxy/localhost timeout (see debug-status.ps1)
$LOKI_URL = if ($env:LOKI_URL) { $env:LOKI_URL } else { "http://127.0.0.1:3100" }

function Get-UnixTimestampNanoseconds {
    $epoch = [datetime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)
    $now = [DateTime]::UtcNow
    $seconds = [long]($now - $epoch).TotalSeconds
    return $seconds * 1000000000
}

function Invoke-LokiQueryRange {
    param(
        [string]$Query,
        [long]$StartNs,
        [long]$EndNs,
        [int]$Limit = 50
    )
    $url = "$LOKI_URL/loki/api/v1/query_range"
    $params = @{
        query = $Query
        start = $StartNs
        end   = $EndNs
        limit = $Limit
    }
    $queryString = ($params.GetEnumerator() | ForEach-Object { "$($_.Key)=$([Uri]::EscapeDataString($_.Value))" }) -join "&"
    $fullUrl = "$url`?$queryString"
    try {
        $resp = Invoke-RestMethod -Uri $fullUrl -Method Get -TimeoutSec 10
        return $resp
    }
    catch {
        # Fallback: WebClient (avoids WinHTTP proxy timeout on localhost)
        try {
            $wc = New-Object System.Net.WebClient
            $json = $wc.DownloadString($fullUrl)
            $wc.Dispose()
            return $json | ConvertFrom-Json
        }
        catch {
            return $null
        }
    }
}

function Format-LokiResult {
    param([object]$Result)
    if (-not $Result -or -not $Result.data -or -not $Result.data.result) {
        return @()
    }
    $lines = @()
    foreach ($stream in $Result.data.result) {
        $svc = $stream.stream.compose_service
        if (-not $svc) { $svc = "unknown" }
        foreach ($entry in $stream.values) {
            $tsNs = [long]$entry[0]
            $tsSec = $tsNs / 1000000000.0
            $dt = [DateTime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc).AddSeconds($tsSec)
            $timeStr = $dt.ToString("HH:mm:ss")
            $msg = $entry[1]
            $lines += "[$timeStr] [$svc] $msg"
        }
    }
    return $lines
}

switch ($Command) {
    "errors" {
        $minutes = [int]$Arg1
        $endNs = Get-UnixTimestampNanoseconds
        $startSec = ([long]($endNs / 1000000000)) - ($minutes * 60)
        $startNs = $startSec * 1000000000

        Write-Host "=== Errors (last ${minutes}min) ===" -ForegroundColor Cyan
        $resp = Invoke-LokiQueryRange -Query '{compose_service=~".+"} | level="ERROR"' -StartNs $startNs -EndNs $endNs -Limit 50
        $lines = Format-LokiResult -Result $resp
        if ($lines.Count -gt 0) {
            $lines | ForEach-Object { Write-Host $_ }
        }
        else {
            Write-Host "(no errors or Loki not reachable)"
        }
    }

    "trace" {
        $cid = $Arg1
        if (-not $cid) {
            Write-Host "Usage: loki-query.ps1 trace <correlation-id>" -ForegroundColor Red
            exit 1
        }
        $endNs = Get-UnixTimestampNanoseconds
        $startNs = $endNs - (86400 * 1000000000)  # last 24h

        Write-Host "=== Correlation Trace: $cid ===" -ForegroundColor Cyan
        $resp = Invoke-LokiQueryRange -Query "{compose_service=~`".+`"} |= `"$cid`"" -StartNs $startNs -EndNs $endNs -Limit 100
        $lines = Format-LokiResult -Result $resp
        if ($lines.Count -gt 0) {
            $lines | ForEach-Object { Write-Host $_ }
        }
        else {
            Write-Host "(no results or Loki not reachable)"
        }
    }

    "esp" {
        $espId = $Arg1
        if (-not $espId) {
            Write-Host "Usage: loki-query.ps1 esp <esp-id>" -ForegroundColor Red
            exit 1
        }
        $endNs = Get-UnixTimestampNanoseconds
        $startNs = $endNs - (86400 * 1000000000)  # last 24h

        Write-Host "=== ESP Logs: $espId ===" -ForegroundColor Cyan
        $resp = Invoke-LokiQueryRange -Query "{compose_service=~`".+`"} |= `"$espId`"" -StartNs $startNs -EndNs $endNs -Limit 100
        $lines = Format-LokiResult -Result $resp
        if ($lines.Count -gt 0) {
            $lines | ForEach-Object { Write-Host $_ }
        }
        else {
            Write-Host "(no results or Loki not reachable)"
        }
    }

    "health" {
        Write-Host "=== Loki Ready ===" -ForegroundColor Cyan
        $ready = $null
        try {
            $ready = Invoke-RestMethod -Uri "$LOKI_URL/ready" -Method Get -TimeoutSec 5
        }
        catch {
            try {
                $wc = New-Object System.Net.WebClient
                $ready = $wc.DownloadString("$LOKI_URL/ready")
                $wc.Dispose()
            }
            catch {
                $ready = $null
            }
        }
        if ($ready -and ([string]$ready).Trim() -eq "ready") {
            Write-Host "OK: Loki is ready" -ForegroundColor Green
        }
        elseif ($ready) {
            Write-Host "FAIL: Loki not ready (response: $ready)"
        }
        else {
            Write-Host "FAIL: Loki not reachable (timeout or connection refused)"
        }

        Write-Host ""
        Write-Host "=== Active Streams ===" -ForegroundColor Cyan
        try {
            $labels = Invoke-RestMethod -Uri "$LOKI_URL/loki/api/v1/label/compose_service/values" -Method Get -TimeoutSec 5
            if ($labels.data) {
                $labels.data | ForEach-Object { Write-Host $_ }
            }
        }
        catch {
            Write-Host "(Loki not reachable)"
        }

        Write-Host ""
        Write-Host "=== Error Count (5min) ===" -ForegroundColor Cyan
        $url = "$LOKI_URL/loki/api/v1/query"
        $query = 'count_over_time({compose_service=~".+"} | level="ERROR" [5m])'
        $fullUrl = "$url`?query=$([Uri]::EscapeDataString($query))"
        try {
            $countResp = Invoke-RestMethod -Uri $fullUrl -Method Get -TimeoutSec 5
            if ($countResp.data -and $countResp.data.result) {
                foreach ($r in $countResp.data.result) {
                    $svc = $r.stream.compose_service
                    $val = $r.value[1]
                    Write-Host "$svc`: $val errors"
                }
            }
            else {
                Write-Host "(no data)"
            }
        }
        catch {
            Write-Host "(Loki not reachable)"
        }
    }
}
