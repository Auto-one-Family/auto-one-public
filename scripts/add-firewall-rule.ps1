# Add Windows Firewall Rule for Mosquitto MQTT (Port 1883)
# MUSS ALS ADMINISTRATOR AUSGEFUEHRT WERDEN!
#
# Ausfuehren mit:
#   1. PowerShell als Administrator oeffnen
#   2. cd "c:\Users\PCUser\Documents\PlatformIO\Projects\Auto-one\scripts"
#   3. .\add-firewall-rule.ps1

# Check if running as Administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "FEHLER: Dieses Script muss als Administrator ausgefuehrt werden!" -ForegroundColor Red
    Write-Host ""
    Write-Host "So geht's:" -ForegroundColor Yellow
    Write-Host "1. PowerShell als Administrator oeffnen (Rechtsklick -> Als Administrator ausfuehren)"
    Write-Host "2. cd `"c:\Users\PCUser\Documents\PlatformIO\Projects\Auto-one\scripts`""
    Write-Host "3. .\add-firewall-rule.ps1"
    Write-Host ""
    exit 1
}

Write-Host "=== Mosquitto MQTT Firewall-Regel hinzufuegen ===" -ForegroundColor Cyan
Write-Host ""

# Check if rule already exists
$existingRule = Get-NetFirewallRule -DisplayName "Mosquitto MQTT" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "Regel 'Mosquitto MQTT' existiert bereits!" -ForegroundColor Green
    Get-NetFirewallRule -DisplayName "Mosquitto MQTT" | Format-List DisplayName,Enabled,Direction,Action
    exit 0
}

# Add the firewall rule
Write-Host "Fuege Firewall-Regel hinzu..." -ForegroundColor Yellow
try {
    New-NetFirewallRule -DisplayName "Mosquitto MQTT" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort 1883 `
        -Action Allow `
        -Profile Any `
        -Description "Erlaubt eingehende MQTT-Verbindungen fuer Mosquitto Broker (Wokwi ESP32 Simulation)"

    Write-Host ""
    Write-Host "ERFOLG! Firewall-Regel wurde hinzugefuegt." -ForegroundColor Green
    Write-Host ""

    # Verify
    Write-Host "Verifizierung:" -ForegroundColor Cyan
    Get-NetFirewallRule -DisplayName "Mosquitto MQTT" | Format-List DisplayName,Enabled,Direction,Action

    Write-Host ""
    Write-Host "Naechste Schritte:" -ForegroundColor Yellow
    Write-Host "1. Mosquitto neu starten: net stop mosquitto && net start mosquitto"
    Write-Host "2. Wokwi CLI testen: scripts\run-wokwi.bat"
    Write-Host ""
}
catch {
    Write-Host "FEHLER beim Hinzufuegen der Regel: $_" -ForegroundColor Red
    exit 1
}
