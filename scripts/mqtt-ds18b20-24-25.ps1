# DS18B20 MQTT: 24-25°C fuer eine Zeitlang senden (Wokwi-Manipulation)
# Topic: kaiser/god/esp/ESP_00000001/sensor/4/data
# Stopp: Ctrl+C oder nach 2 Minuten

$topic = "kaiser/god/esp/ESP_00000001/sensor/4/data"
$esp_id = "ESP_00000001"
$gpio = 4
$onewire = "280102030405069E"
$durationSec = 120   # 2 Minuten
$intervalSec = 5
$endAt = (Get-Date).AddSeconds($durationSec)

Write-Host "DS18B20 24-25°C: Sende alle ${intervalSec}s bis $($endAt.ToString('HH:mm:ss')) (Ctrl+C zum Abbrechen)" -ForegroundColor Cyan

$toggle = 0
while ((Get-Date) -lt $endAt) {
    $ts = [int][double]::Parse((Get-Date -UFormat %s))
    $raw = 24 + ($toggle % 2)   # 24, 25, 24, 25 ...
    $toggle++
    $payload = "{`"ts`":$ts,`"esp_id`":`"$esp_id`",`"gpio`":$gpio,`"sensor_type`":`"ds18b20`",`"raw`":$raw,`"raw_mode`":true,`"onewire_address`":`"$onewire`"}"
    docker exec automationone-mqtt mosquitto_pub -h localhost -p 1883 -t $topic -m $payload 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "  $((Get-Date).ToString('HH:mm:ss')) -> ${raw}°C" } else { Write-Host "  Fehler (Broker erreichbar?)" -ForegroundColor Yellow }
    Start-Sleep -Seconds $intervalSec
}
Write-Host "Fertig." -ForegroundColor Green
