# ESP32 PROVISIONING - USER GUIDE

**AutomationOne - El Trabajante**  
**Version:** 1.0  
**Datum:** 2025-01-22

---

## 🎯 WAS IST PROVISIONING?

**Provisioning** ist der Prozess, bei dem ein neuer ESP32 seine **WiFi-Zugangsdaten** und **Server-Konfiguration** erhält, damit er sich mit deinem AutomationOne-System verbinden kann.

### Warum wird es benötigt?

Ein brandneuer ESP32 kennt noch nicht:
- ❌ Dein WiFi-Netzwerk (SSID + Passwort)
- ❌ Die IP-Adresse deines God-Kaiser Servers
- ❌ Seine Zone im System

**Nach dem Provisioning weiß der ESP:**
- ✅ WiFi-Zugangsdaten → verbindet sich automatisch
- ✅ Server-IP → sendet Daten an God-Kaiser
- ✅ Optional: Zone-Config (`kaiser_id`, `master_zone_id`) → kann während Provisioning gesetzt werden

**Wichtig:** Zone-Zuordnung kann auch **nach** Provisioning via MQTT erfolgen (siehe [Zone Assignment Flow](../system-flows/08-zone-assignment-flow.md)). Provisioning konfiguriert nur WiFi und Server-Verbindung.

**Siehe auch:**
- → [Zone Assignment Flow](../system-flows/08-zone-assignment-flow.md) - Runtime zone assignment via MQTT
- → [Dynamic Zones Implementation](DYNAMIC_ZONES_IMPLEMENTATION.md) - Implementation summary
- → [Boot Sequence](../system-flows/01-boot-sequence.md) - Provisioning integration

---

## 🚀 SCHNELLSTART: ESP PROVISIONIEREN (3 SCHRITTE)

### Schritt 1: ESP einschalten

1. **Flashe** den ESP32 mit der El Trabajante Firmware
2. **Stecke** den ESP in ein USB-Netzteil oder verbinde ihn mit Strom
3. **Warte** ~5 Sekunden

**Was passiert:**
- ESP bootet
- Erkennt: "Keine Config vorhanden"
- **Startet automatisch AP-Mode** (Access Point)

### Schritt 2: Mit ESP verbinden

1. **Öffne** die WiFi-Einstellungen deines Geräts (Laptop, Smartphone, Tablet)
2. **Suche** nach einem WiFi-Netzwerk mit dem Namen:
   ```
   AutoOne-ESP_XXXXXX
   ```
   (XXXXXX = letzten 6 Zeichen der MAC-Adresse)

3. **Verbinde** mit diesem Netzwerk
   - **Passwort:** `provision`

4. **Öffne** einen Browser und gehe zu:
   ```
   http://192.168.4.1
   ```

**Was du siehst:**
- Landing-Page mit ESP-Informationen
- ESP-ID, MAC-Adresse, Status

### Schritt 3: God-Kaiser konfigurieren

#### Option A: Web-Interface (empfohlen)

1. **Öffne** das God-Kaiser Web-Interface
2. **Navigiere** zu **"ESP Provisioning"**
3. **Du siehst** den neuen ESP in der Liste
4. **Klicke** auf **"Konfigurieren"**
5. **Wähle**:
   - ✅ Production WiFi SSID
   - ✅ WiFi Passwort
   - ✅ Zone (z.B. "Greenhouse Zone 1")
   - ✅ Optional: Subzone
6. **Klicke** auf **"Provision"**

#### Option B: HTTP-API (für Profis)

```bash
curl -X POST http://192.168.4.1/provision \
  -H "Content-Type: application/json" \
  -d '{
    "ssid": "MeinWiFi",
    "password": "GeheimesPasswort",
    "server_address": "192.168.0.100",
    "mqtt_port": 8883,
    "mqtt_username": "",
    "mqtt_password": "",
    "kaiser_id": "god",
    "master_zone_id": "greenhouse_zone_1"
  }'
```

### Schritt 4: Fertig!

**Was passiert:**
- ✅ ESP empfängt Config
- ✅ Speichert sie im NVS (persistenter Speicher)
- ✅ **Rebootet automatisch** (nach 2 Sekunden)
- ✅ Verbindet sich mit Production-WiFi
- ✅ Verbindet sich mit MQTT Broker
- ✅ Sendet initial Heartbeat
- ✅ **Wichtig:** ESP muss zuerst über REST API registriert werden (`POST /api/v1/esp/register`)
- ✅ God-Kaiser kann dann Zone Assignment senden (siehe [Zone Assignment Flow](../system-flows/08-zone-assignment-flow.md))
- ✅ **Ist jetzt OPERATIONAL!**

**Du siehst:**
- ESP verschwindet aus deiner WiFi-Liste (AP-Mode beendet)
- ESP erscheint im God-Kaiser als **"Online"**
- Heartbeat-Messages werden gesendet

---

## 📋 DETAILLIERTE ANLEITUNG

### Variante 1: Einzelner ESP

**Szenario:** Du hast 1 neuen ESP und möchtest ihn hinzufügen.

1. **Vorbereitung:**
   - God-Kaiser Server läuft
   - Production-WiFi ist verfügbar
   - ESP ist geflasht (Firmware El Trabajante)

2. **ESP einschalten:**
   ```
   → ESP bootet
   → Erkennt: Keine Config
   → Startet AP-Mode
   → LED blinkt (falls vorhanden)
   ```

3. **Verbinden:**
   - WiFi: `AutoOne-ESP_AB12CD` (Beispiel)
   - Passwort: `provision`
   - Browser: `http://192.168.4.1`

4. **Konfigurieren:**
   - Option A: God-Kaiser Web-Interface
   - Option B: HTTP POST direkt an ESP
   - Option C: God-Kaiser scannt automatisch und zeigt Notification

5. **Warten:**
   - Config wird gesendet
   - ESP speichert und rebootet
   - ~30 Sekunden bis ESP online

6. **Verifizieren:**
   - God-Kaiser zeigt ESP als "Online"
   - Check: `kaiser/god/esp/ESP_AB12CD/system/heartbeat`
   - Heartbeat alle 60 Sekunden

### Variante 2: Mehrere ESPs gleichzeitig

**Szenario:** Du hast 10 neue ESPs und möchtest alle provisionieren.

**Problem:** God-Kaiser hat nur 1 WiFi-Adapter → kann nur mit 1 ESP-AP gleichzeitig verbunden sein.

**Lösung:** Sequentielles Provisioning

#### Methode 1: Manuell (nacheinander)

```
1. ESP #1 einschalten → AP-Mode
2. God-Kaiser verbindet → provisioniert
3. ESP #1 rebootet → Production-WiFi
4. God-Kaiser verbindet zurück zu Production-WiFi
5. ESP #2 einschalten → AP-Mode
6. Repeat...
```

**Zeit:** ~2 Minuten pro ESP → 10 ESPs = ~20 Minuten

#### Methode 2: Batch-Provisioning (zukünftig)

```
1. Alle 10 ESPs einschalten
2. God-Kaiser scannt WiFi → findet 10 ESP-APs
3. God-Kaiser zeigt Liste: "10 ESPs warten auf Provisioning"
4. User klickt "Provision All" (mit gleicher Config)
5. God-Kaiser verbindet sequentiell zu jedem ESP
6. Fortschritt-Anzeige: "3/10 provisioned"
7. Nach ~20 Minuten: Alle 10 ESPs online
```

**Status:** Geplant für Phase 7

### Variante 3: Runtime-Hinzufügen

**Szenario:** Dein System läuft mit 50 ESPs. Du möchtest ESP #51 hinzufügen.

**Vorteil:** Kein System-Neustart nötig!

```
1. System läuft (50 ESPs operational)
2. ESP #51 einschalten → AP-Mode
3. God-Kaiser erkennt neuen ESP:
   - WiFi-Scan läuft alle 5 Minuten
   - Notification: "Neuer ESP gefunden!"
4. God-Kaiser provisioniert ESP #51
   - Während: 50 andere ESPs laufen weiter
   - God-Kaiser disconnected kurz (30s)
5. ESP #51 rebootet → Production-WiFi
6. ESP #51 ist jetzt Teil des Systems
7. System läuft mit 51 ESPs
```

**Impact:** 30 Sekunden God-Kaiser offline (ESPs puffern Daten)

---

## 🔒 FACTORY RESET: ESP NEU PROVISIONIEREN

Manchmal muss ein ESP neu provisioniert werden:
- ❌ Falsche WiFi-Credentials eingegeben
- ❌ Server-IP geändert
- ❌ ESP an neuen Standort verschoben

**Factory-Reset löscht:**
- WiFi-Konfiguration
- Zone-Zuordnung
- System-Config (optional: auch Sensor/Actuator-Configs)

### Methode 1: Boot-Button (Hardware)

**Für:** ESP ohne Netzwerk-Verbindung

1. **Halte** den Boot-Button gedrückt (GPIO 0)
2. **Drücke** den Reset-Button kurz (oder stecke ESP ab/an)
3. **Halte** Boot-Button weiter gedrückt für **10 Sekunden**
4. **LED blinkt** (Bestätigung)
5. **ESP rebootet** automatisch
6. **ESP startet** im AP-Mode (nicht provisioniert)

**Serial-Output:**

```
╔════════════════════════════════════════╗
║  ⚠️  BOOT BUTTON PRESSED              ║
║  Hold for 10 seconds for Factory Reset║
╚════════════════════════════════════════╝
..........
╔════════════════════════════════════════╗
║  🔥 FACTORY RESET TRIGGERED           ║
╚════════════════════════════════════════╝
✅ WiFi configuration cleared
✅ Zone configuration cleared
Rebooting in 2 seconds...
```

### Methode 2: HTTP-Endpoint (während Provisioning)

**Für:** ESP im AP-Mode, Provisioning schiefgelaufen

1. **Verbinde** mit ESP-AP (`AutoOne-ESP_XXXXXX`)
2. **Sende** HTTP POST:

```bash
curl -X POST http://192.168.4.1/reset \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

**Response:**

```json
{
  "success": true,
  "message": "Factory reset completed. Rebooting in 3 seconds..."
}
```

3. **ESP rebootet** und startet wieder im AP-Mode

### Methode 3: MQTT-Command (nach Provisioning)

**Für:** ESP operational, soll neu provisioniert werden

1. **God-Kaiser** sendet MQTT-Command:

```bash
mosquitto_pub -t "kaiser/god/esp/ESP_AB12CD/system/command" \
  -m '{"command":"factory_reset","confirm":true}'
```

2. **ESP empfängt** Command
3. **ESP löscht** Config
4. **ESP rebootet** → startet im AP-Mode

**Wichtig:** `"confirm":true` ist Pflicht (Schutz vor versehentlichem Reset)

---

## ⚠️ TROUBLESHOOTING

### Problem 1: ESP-AP nicht sichtbar

**Symptome:**
- ESP bootet, aber kein `AutoOne-ESP_XXXXXX` WiFi-Netzwerk

**Ursachen & Lösungen:**

1. **ESP hat bereits Config:**
   - Check: Serial-Output beim Boot
   - Lösung: Factory-Reset (Boot-Button 10s)

2. **AP-Mode Fehler:**
   - Check: Serial-Output zeigt `Failed to start WiFi AP`
   - Lösung: ESP neu flashen, Hardware defekt?

3. **WiFi-Kanal-Problem:**
   - ESP sendet auf Kanal 1, dein Gerät scannt nur 2,4 GHz nicht
   - Lösung: Stelle sicher, dass dein Gerät 2,4 GHz unterstützt

4. **Zu viele WiFi-Netzwerke:**
   - Dein Standort hat >50 WiFi-Netzwerke
   - Lösung: Gehe näher an ESP, WiFi-Liste neu laden

### Problem 2: Verbindung zu ESP-AP scheitert

**Symptome:**
- ESP-AP sichtbar, aber "Kann nicht verbinden"

**Ursachen & Lösungen:**

1. **Falsches Passwort:**
   - Passwort ist `provision` (lowercase, keine Leerzeichen)
   - Check: Groß-/Kleinschreibung

2. **Max Connections erreicht:**
   - ESP erlaubt nur 1 Connection gleichzeitig
   - Lösung: Warte, bis andere Connection abbricht (Timeout: 10 Min)

3. **IP-Vergabe scheitert:**
   - Dein Gerät erhält keine IP (192.168.4.x)
   - Lösung: DHCP aktivieren, WiFi reconnect

### Problem 3: Config-POST scheitert

**Symptome:**
- HTTP POST `/provision` gibt Fehler

**Häufige Fehler:**

#### Error: `JSON_PARSE_ERROR`

```json
{
  "success": false,
  "error": "JSON_PARSE_ERROR",
  "message": "Invalid JSON format"
}
```

**Lösung:** JSON-Syntax prüfen (Kommas, Klammern)

#### Error: `VALIDATION_FAILED`

```json
{
  "success": false,
  "error": "VALIDATION_FAILED",
  "message": "WiFi SSID is empty"
}
```

**Lösung:** Pflichtfelder prüfen:
- `ssid` nicht leer (max 32 Zeichen)
- `password` max 63 Zeichen
- `server_address` gültige IPv4
- `mqtt_port` 1-65535

#### Error: `NVS_WRITE_FAILED`

```json
{
  "success": false,
  "error": "NVS_WRITE_FAILED",
  "message": "Failed to save configuration to NVS"
}
```

**Lösung:** NVS-Speicher voll oder defekt
- Factory-Reset versuchen
- ESP neu flashen
- Hardware defekt?

### Problem 4: ESP rebootet, aber keine Verbindung

**Symptome:**
- Provisioning erfolgreich
- ESP rebootet
- ESP erscheint nicht im God-Kaiser

**Ursachen & Lösungen:**

1. **Falsche WiFi-Credentials:**
   - ESP kann sich nicht mit Production-WiFi verbinden
   - Check: Serial-Output zeigt `WiFi connection timeout`
   - Lösung: Factory-Reset, korrekte Credentials eingeben

2. **Falsche Server-IP:**
   - ESP verbindet WiFi, aber MQTT scheitert
   - Check: Serial-Output zeigt `MQTT connection failed`
   - Lösung: Prüfe God-Kaiser IP, Firewall?

3. **MQTT-Port falsch:**
   - Default: 8883 (TLS) oder 1883 (unencrypted)
   - Check: God-Kaiser MQTT-Broker läuft auf diesem Port?
   - Lösung: Korrekte Port-Nummer eingeben

4. **MQTT-Auth fehlgeschlagen:**
   - ESP sendet falsche oder fehlende Credentials
   - Check: God-Kaiser MQTT-Broker erlaubt Anonymous?
   - Lösung: `mqtt_username` + `mqtt_password` eingeben

### Problem 5: Provisioning Timeout (10 Minuten)

**Symptome:**
- ESP im AP-Mode
- Keine Config empfangen
- Nach 10 Minuten: ESP geht in Safe-Mode

**Serial-Output:**

```
╔════════════════════════════════════════╗
║  ❌ PROVISIONING TIMEOUT              ║
╚════════════════════════════════════════╝
No configuration received within 10 minutes
ESP will enter Safe-Mode
```

**Ursachen & Lösungen:**

1. **God-Kaiser nicht verfügbar:**
   - Lösung: God-Kaiser Server starten

2. **Vergessen zu provisionieren:**
   - Lösung: Factory-Reset (Boot-Button), neu starten

3. **Netzwerk-Problem:**
   - God-Kaiser kann nicht zu ESP-AP verbinden
   - Lösung: Näher an ESP, WiFi-Probleme beheben

**Safe-Mode:**
- ESP bleibt im AP-Mode (unbegrenzter Timeout)
- LED blinkt Fehler-Pattern
- Kann manuell provisioniert werden
- Oder: Boot-Button-Reset → neu starten

---

## 📊 CONFIG-PARAMETER REFERENZ

### Pflichtfelder

| Parameter | Typ | Beschreibung | Validation |
|-----------|-----|--------------|------------|
| `ssid` | String | WiFi SSID (Netzwerk-Name) | 1-32 Zeichen, nicht leer |
| `password` | String | WiFi Passwort | 0-63 Zeichen (leer = offenes Netzwerk) |
| `server_address` | String | God-Kaiser Server IP | IPv4 Format (z.B. `192.168.0.100`) |

### Optionale Felder

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| `mqtt_port` | Number | `8883` | MQTT Broker Port (1-65535) |
| `mqtt_username` | String | `""` | MQTT Username (leer = Anonymous) |
| `mqtt_password` | String | `""` | MQTT Password |
| `kaiser_id` | String | `""` | Overarching Pi identifier (`"god"` = God-Kaiser Server, aktuell immer "god") |
| `master_zone_id` | String | `""` | Master Zone ID (z.B. `greenhouse_master`) - optional |
| `subzone_id` | String | `""` | Subzone ID (z.B. `section_A`) - optional |

### Beispiel: Minimale Config

```json
{
  "ssid": "MeinWiFi",
  "password": "Passwort123",
  "server_address": "192.168.0.100"
}
```

### Beispiel: Vollständige Config

```json
{
  "ssid": "ProductionWiFi",
  "password": "SuperSecretPassword",
  "server_address": "192.168.0.100",
  "mqtt_port": 8883,
  "mqtt_username": "",
  "mqtt_password": "",
  "kaiser_id": "god",
  "master_zone_id": "greenhouse_master",
  "subzone_id": "section_A"
}
```

---

## 🔐 SICHERHEIT

### Aktuelle Sicherheits-Maßnahmen (Phase 6)

✅ **AP-Passwort:** `provision` (verhindert unbefugten Zugriff)  
✅ **Timeout:** 10 Minuten (ESP schaltet AP automatisch ab)  
✅ **Retry-Limit:** 3 Versuche → Safe-Mode  
✅ **Config-Validation:** SSID-Länge, IP-Format, Port-Range  
✅ **NVS-Encryption:** Config wird verschlüsselt gespeichert  
✅ **Factory-Reset Protection:** `"confirm":true` Pflicht (MQTT)

### Geplante Sicherheits-Features (Phase 7+)

🔒 **HTTPS-Server:** Verschlüsselte Config-Übertragung  
🔒 **One-Time-Token:** Token generiert beim Boot, nur 1x verwendbar  
🔒 **IP-Whitelist:** Nur God-Kaiser IP erlaubt  
🔒 **mTLS:** Mutual TLS Authentication  
🔒 **HSM-Integration:** Hardware Security Module

### Best Practices

1. **Ändere AP-Passwort:**
   - Default ist `provision` (dokumentiert, jeder kennt es)
   - Für Production: Custom-Password im Code ändern

2. **Isoliertes Provisioning-Netzwerk:**
   - Provisioning in separatem VLAN
   - Kein Internet-Zugriff nötig

3. **Physischer Zugang:**
   - ESP nur für autorisiertes Personal zugänglich
   - Boot-Button-Reset verhindert durch Gehäuse

4. **MQTT-Auth:**
   - Verwende Username/Password für MQTT
   - Oder: TLS Client-Certificates (mTLS)

5. **Monitoring:**
   - God-Kaiser loggt alle Provisioning-Versuche
   - Audit-Trail: Wann, welcher ESP, von welcher IP

---

## 🎓 FAQ

### F: Kann ich mehrere ESPs mit gleicher Config provisionieren?

**A:** Ja! Alle ESPs in derselben Zone können dieselben WiFi-Credentials und Server-IP bekommen. Die ESP-ID (MAC-basiert) unterscheidet sie.

### F: Was passiert bei WiFi-Passwort-Änderung?

**A:** Alle ESPs müssen neu provisioniert werden. Optionen:
- **Option 1:** MQTT-Command `update_wifi` (zukünftig)
- **Option 2:** Factory-Reset + neu provisionieren (aktuell)

### F: Kann ESP ohne God-Kaiser provisioniert werden?

**A:** Ja, via direktem HTTP POST an ESP-AP. Aber ESP braucht trotzdem Server-IP für MQTT-Verbindung.

### F: Unterstützt ESP 5 GHz WiFi?

**A:** Nein, ESP32 unterstützt nur 2,4 GHz. Stelle sicher, dass dein WiFi 2,4 GHz aktiviert hat.

### F: Wie viele ESPs kann ich haben?

**A:** Theoretisch unbegrenzt. Praktisch limitiert durch:
- God-Kaiser Hardware (RAM, CPU)
- MQTT-Broker (max Connections)
- Netzwerk-Bandbreite

**Getestet:** Bis 100 ESPs pro God-Kaiser (Raspberry Pi 5)

### F: Kann ich ESP über USB provisionieren?

**A:** Aktuell: Nein (nur WiFi AP-Mode)  
**Geplant:** Phase 8 - Serial-Fallback für Debugging

### F: Speichert ESP das WiFi-Passwort im Klartext?

**A:** Nein, NVS ist verschlüsselt. Aber: Jeder mit physischem Zugriff + Serial-Zugriff kann Config auslesen.

---

## 📞 SUPPORT

**Probleme? Fragen?**

1. **Check Logs:**
   - ESP Serial-Output (115200 Baud)
   - God-Kaiser Logs (`/var/log/autoone/`)

2. **Dokumentation:**
   - `docs/ANALYSIS.md` (Code-Analyse)
   - `docs/PROVISIONING_DESIGN.md` (Architektur)
   - `docs/INTEGRATION_GUIDE.md` (Entwickler)

3. **Community:**
   - GitHub Issues
   - Discord Channel

4. **Debug-Modus:**
   - `logger.setLogLevel(LOG_DEBUG);` in `main.cpp`
   - Serial-Output zeigt alle Details

---

**Version 1.0 - Januar 2025**  
**AutomationOne - Making IoT Simple**


