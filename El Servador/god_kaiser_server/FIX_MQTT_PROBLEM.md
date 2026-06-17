# MQTT Connection Problem - Lösung

## Problem
Der God-Kaiser Server kann sich nicht mit dem Mosquitto Broker verbinden.
**Error Code 7** wird gemeldet und es gibt hunderte TIME_WAIT Verbindungen.

## Diagnose-Ergebnisse
```
[OK] Mosquitto Broker läuft auf Port 1883
[OK] Mosquitto Config gefunden: C:\Program Files\mosquitto\mosquitto.conf
[PROBLEM] Hunderte TIME_WAIT Verbindungen (Server reconnect Loop)
[PROBLEM] Error Code 7 - Connection rejected
```

## Lösung

### Schritt 1: Server stoppen
Stoppe den laufenden God-Kaiser Server (CTRL+C im Terminal 19)

### Schritt 2: Mosquitto Config anpassen

**Option A: Schnelle Lösung (Empfohlen)**

1. Öffne PowerShell **als Administrator**
2. Führe aus:
```powershell
# Config bearbeiten
notepad "C:\Program Files\mosquitto\mosquitto.conf"
```

3. Füge am Ende der Datei hinzu:
```
# Erlaube anonyme Verbindungen
allow_anonymous true
listener 1883
```

4. Speichern und schließen

**Option B: Vollständige Lösung**

Kopiere die Einstellungen aus `mosquitto_fix.conf` (in diesem Ordner) in die 
Mosquitto Config.

### Schritt 3: Mosquitto Broker neu starten

```powershell
# PowerShell als Administrator
Restart-Service mosquitto
```

Oder manuell:
1. Windows Services öffnen (services.msc)
2. "Mosquitto Broker" suchen
3. Rechtsklick → Neu starten

### Schritt 4: TIME_WAIT Verbindungen clearen (Optional)

Die TIME_WAIT Verbindungen verschwinden automatisch nach einigen Minuten.
Alternativ: Computer neu starten (clearert alle Verbindungen)

### Schritt 5: Server neu starten

```powershell
cd "El Servador\god_kaiser_server"
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

## Test der Verbindung

Nach den Änderungen teste die Verbindung:

```powershell
cd "El Servador\god_kaiser_server"
poetry run python scripts/test_mqtt.py
```

Erwartetes Ergebnis:
```
[OK] Connection successful
[OK] Publish successful
[OK] Broker allows anonymous connections
```

## Alternative: MQTT Authentifizierung einrichten

Falls du MQTT mit Authentifizierung verwenden möchtest:

### 1. Password File erstellen

```powershell
# PowerShell als Administrator
cd "C:\Program Files\mosquitto"
.\mosquitto_passwd.exe -c passwd god_kaiser
# Passwort eingeben wenn gefragt
```

### 2. Mosquitto Config anpassen

```
allow_anonymous false
password_file C:/Program Files/mosquitto/passwd
listener 1883
```

### 3. .env Datei anpassen

Erstelle/bearbeite `El Servador/god_kaiser_server/.env`:

```env
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=god_kaiser
MQTT_PASSWORD=dein_passwort_hier
```

### 4. Mosquitto neu starten

```powershell
Restart-Service mosquitto
```

## Troubleshooting

### Problem: "Access Denied" beim Config-Bearbeiten
**Lösung:** PowerShell/Notepad als Administrator ausführen

### Problem: Mosquitto Service nicht gefunden
**Lösung:** 
```powershell
# Service Status prüfen
Get-Service mosquitto

# Falls nicht installiert, Mosquitto neu installieren
```

### Problem: Server zeigt weiter Error Code 7
**Lösung:**
1. Prüfe, ob Mosquitto wirklich neu gestartet wurde
2. Prüfe die Config mit: `C:\Program Files\mosquitto\mosquitto.exe -c "C:\Program Files\mosquitto\mosquitto.conf" -v`
3. Prüfe Firewall-Einstellungen für Port 1883

## Weitere Hilfe

- Test-Script ausführen: `poetry run python scripts/test_mqtt.py`
- Mosquitto Logs prüfen (nach Aktivierung): `C:\Program Files\mosquitto\mosquitto.log`
- Verbindungen prüfen: `netstat -ano | findstr ":1883"`















