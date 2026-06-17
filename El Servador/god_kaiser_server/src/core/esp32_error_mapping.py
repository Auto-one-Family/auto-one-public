"""
ESP32 Error Code Mapping - Vollständiges Mapping aller Error-Codes

Maps ESP32 error codes to human-readable messages with troubleshooting hints.
Used by Error-Event-Handler to enrich error events before storage.

Architecture Philosophy:
- Server TRUSTS ESP32 hardware status COMPLETELY
- No re-validation of ESP error codes
- Error info is for ENRICHMENT only (user messages, troubleshooting)
- System MUST NOT break on unknown error codes

Error Code Ranges (from error_codes.h):
- HARDWARE:       1000-1999 (GPIO, I2C, OneWire, PWM, Sensor, Actuator)
- SERVICE:        2000-2999 (NVS, Config, Logger, Storage, Subzone)
- COMMUNICATION:  3000-3999 (WiFi, MQTT, HTTP, Network)
- APPLICATION:    4000-4999 (State, Operation, Command, Payload, Memory, System, Task, Watchdog, Discovery)
"""

from typing import Any, Dict, Optional

# ============================================
# HARDWARE ERROR CODES (1000-1999)
# ============================================

# GPIO Errors (1001-1006)
ESP32_GPIO_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1001: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "GPIO-Pin vom System reserviert",
        "message_user_de": "Hardware-Fehler: Dieser Pin ist vom System reserviert und kann nicht verwendet werden",
        "troubleshooting_de": [
            "1. Anderen GPIO-Pin in der Konfiguration wählen",
            "2. Reservierte Pins prüfen: GPIO 6-11 (SPI Flash), GPIO 34-39 (nur Input)",
            "3. Board-spezifische Pin-Belegung in Dokumentation prüfen",
        ],
        "docs_link": "/docs/hardware/esp32#reserved-pins",
        "recoverable": True,
        "user_action_required": True,
    },
    1002: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "GPIO-Pin bereits durch andere Komponente belegt",
        "message_user_de": "Konfigurations-Fehler: Dieser Pin wird bereits von einem anderen Sensor oder Aktor verwendet",
        "troubleshooting_de": [
            "1. Aktuelle Pin-Belegung des ESP prüfen (GET /api/v1/esp/{id}/gpio-status)",
            "2. Konflikt auflösen: Anderen Pin wählen oder bestehende Komponente entfernen",
            "3. Bei OneWire: Mehrere Sensoren können denselben Bus-Pin teilen",
        ],
        "docs_link": "/docs/hardware/esp32#gpio-conflicts",
        "recoverable": True,
        "user_action_required": True,
    },
    1003: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "GPIO-Pin Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Pin konnte nicht initialisiert werden",
        "troubleshooting_de": [
            "1. Pin-Nummer auf Gültigkeit prüfen (0-39 für ESP32)",
            "2. ESP32 neu starten",
            "3. Bei wiederholtem Fehler: Hardware-Defekt möglich",
        ],
        "docs_link": "/docs/hardware/esp32#pins",
        "recoverable": False,
        "user_action_required": True,
    },
    1004: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Ungültiger GPIO-Modus angegeben",
        "message_user_de": "Konfigurations-Fehler: Der angegebene Pin-Modus ist ungültig",
        "troubleshooting_de": [
            "1. Gültige Modi: INPUT, OUTPUT, INPUT_PULLUP, INPUT_PULLDOWN",
            "2. Pins 34-39 unterstützen nur INPUT (keine Pull-ups)",
            "3. Konfiguration in Server-DB prüfen",
        ],
        "docs_link": "/docs/hardware/esp32#pin-modes",
        "recoverable": True,
        "user_action_required": True,
    },
    1005: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "GPIO-Pin Lesevorgang fehlgeschlagen",
        "message_user_de": "Hardware-Warnung: Pin-Wert konnte nicht gelesen werden",
        "troubleshooting_de": [
            "1. Pin-Modus prüfen (muss INPUT sein)",
            "2. Physische Verbindung prüfen",
            "3. Bei ADC-Pins: Spannung im gültigen Bereich (0-3.3V)?",
        ],
        "docs_link": "/docs/hardware/esp32#gpio-read",
        "recoverable": True,
        "user_action_required": False,
    },
    1006: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "GPIO-Pin Schreibvorgang fehlgeschlagen",
        "message_user_de": "Hardware-Warnung: Pin-Wert konnte nicht geschrieben werden",
        "troubleshooting_de": [
            "1. Pin-Modus prüfen (muss OUTPUT sein)",
            "2. Pins 34-39 sind nur Input-fähig",
            "3. Bei wiederholtem Fehler: ESP32 neu starten",
        ],
        "docs_link": "/docs/hardware/esp32#gpio-write",
        "recoverable": True,
        "user_action_required": False,
    },
}

# I2C Errors (1007, 1009-1019)
ESP32_I2C_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1007: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Timeout: Sensor antwortet nicht",
        "message_user_de": "Hardware-Fehler: I2C-Gerät antwortet nicht innerhalb der Zeitgrenze",
        "troubleshooting_de": [
            "1. Kabelprüfung SDA/SCL auf Wackelkontakt oder Bruch",
            "2. Pull-Up-Widerstände prüfen (4.7kOhm empfohlen)",
            "3. Nur ein I2C-Master auf dem Bus erlaubt",
            "4. ESP32 neu starten für Bus-Reset",
        ],
        "docs_link": "/docs/hardware/i2c#timeout",
        "recoverable": True,
        "user_action_required": True,
    },
    1009: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "I2C CRC-Prüfung fehlgeschlagen",
        "message_user_de": "Hardware-Warnung: Daten vom I2C-Sensor sind beschädigt (CRC-Fehler)",
        "troubleshooting_de": [
            "1. Kabellänge prüfen (max. ~50cm ohne Level-Shifter)",
            "2. Abgeschirmte Kabel verwenden bei Störquellen in der Nähe",
            "3. Elektromagnetische Störquellen entfernen (Motoren, Relais)",
            "4. Versorgungsspannung des Sensors prüfen (stabil 3.3V oder 5V)",
        ],
        "docs_link": "/docs/hardware/i2c#crc-errors",
        "recoverable": True,
        "user_action_required": False,
    },
    1010: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Bus Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: I2C-Bus konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. I2C-Pins prüfen: Standard SDA=21, SCL=22 (ESP32)",
            "2. Pull-up Widerstände (4.7k Ohm) an SDA und SCL anschließen",
            "3. Prüfen ob Pins nicht anderweitig belegt sind",
        ],
        "docs_link": "/docs/hardware/i2c#setup",
        "recoverable": False,
        "user_action_required": True,
    },
    1011: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Gerät nicht am Bus gefunden",
        "message_user_de": "Hardware-Fehler: Sensor antwortet nicht am I2C-Bus",
        "troubleshooting_de": [
            "1. I2C-Adresse in Konfiguration prüfen (z.B. 0x44 für SHT31)",
            "2. Kabelverbindung SDA/SCL/VCC/GND prüfen",
            "3. I2C-Scan ausführen: POST /api/v1/sensors/esp/{esp_id}/i2c/scan",
            "4. Bei mehreren Geräten: Adresskonflikte ausschließen",
        ],
        "docs_link": "/docs/sensors/i2c#troubleshooting",
        "recoverable": True,
        "user_action_required": True,
    },
    1012: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Lesevorgang fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Daten konnten nicht vom I2C-Gerät gelesen werden",
        "troubleshooting_de": [
            "1. Sensor-Stromversorgung prüfen (3.3V oder 5V je nach Sensor)",
            "2. Kabellänge prüfen (max. ~50cm ohne Level-Shifter)",
            "3. Bus-Geschwindigkeit reduzieren (100kHz statt 400kHz)",
            "4. Sensor könnte defekt sein",
        ],
        "docs_link": "/docs/sensors/i2c#read-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    1013: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Schreibvorgang fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Daten konnten nicht zum I2C-Gerät geschrieben werden",
        "troubleshooting_de": [
            "1. Gerät unterstützt möglicherweise keine Schreiboperationen",
            "2. I2C-Adresse und Register-Adresse prüfen",
            "3. Timing-Probleme: Bus-Geschwindigkeit reduzieren",
        ],
        "docs_link": "/docs/sensors/i2c#write-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    1014: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Bus Fehler (SDA/SCL blockiert)",
        "message_user_de": "Hardware-Fehler: I2C-Bus ist blockiert (Timeout oder Kurzschluss)",
        "troubleshooting_de": [
            "1. ESP32 neu starten (Bus-Reset)",
            "2. Kabel auf Kurzschluss prüfen",
            "3. Defektes Gerät vom Bus entfernen (einzeln testen)",
            "4. Pull-up Widerstände prüfen (4.7k Ohm empfohlen)",
        ],
        "docs_link": "/docs/hardware/i2c#bus-errors",
        "recoverable": False,
        "user_action_required": True,
    },
    1015: {
        "category": "HARDWARE",
        "severity": "CRITICAL",
        "message_de": "I2C-Bus blockiert (SDA oder SCL dauerhaft LOW)",
        "message_user_de": "Kritischer Hardware-Fehler: I2C-Bus hängt, kein Gerät antwortet",
        "troubleshooting_de": [
            "1. SDA- und SCL-Leitungen mit Multimeter prüfen (sollten HIGH sein im Ruhezustand)",
            "2. ESP32 neu starten (erzwingt Bus-Reset)",
            "3. Sensor vom Bus trennen und einzeln testen (Power-Cycle)",
            "4. Clock-Stretching-Problem: Sensor hält SCL zu lange LOW",
        ],
        "docs_link": "/docs/hardware/i2c#bus-stuck",
        "recoverable": False,
        "user_action_required": True,
    },
    1016: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "I2C-Bus Recovery gestartet",
        "message_user_de": "System-Info: Automatische I2C-Bus-Wiederherstellung wurde gestartet",
        "troubleshooting_de": [
            "1. Keine Aktion nötig — System versucht Selbstheilung",
            "2. Bei häufigem Auftreten: Verkabelung und Pull-Up-Widerstände prüfen",
            "3. Sensor-Stromversorgung auf Stabilität prüfen",
        ],
        "docs_link": "/docs/hardware/i2c#recovery",
        "recoverable": True,
        "user_action_required": False,
    },
    1017: {
        "category": "HARDWARE",
        "severity": "CRITICAL",
        "message_de": "I2C-Bus Recovery fehlgeschlagen",
        "message_user_de": "Kritischer Hardware-Fehler: Automatische Bus-Wiederherstellung war nicht erfolgreich",
        "troubleshooting_de": [
            "1. ESP32 neu starten (manueller Reset)",
            "2. Sensor physisch abklemmen und wieder anschließen",
            "3. I2C-Adresse des Sensors prüfen (Adresskonflikt?)",
            "4. Sensor könnte defekt sein — mit Ersatzsensor testen",
        ],
        "docs_link": "/docs/hardware/i2c#recovery-failed",
        "recoverable": False,
        "user_action_required": True,
    },
    1018: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "I2C-Bus erfolgreich wiederhergestellt",
        "message_user_de": "System-Info: I2C-Bus wurde erfolgreich wiederhergestellt, normaler Betrieb",
        "troubleshooting_de": [
            "1. Keine Aktion nötig — Bus funktioniert wieder normal",
            "2. Bei häufigem Auftreten: Hardware-Verkabelung überprüfen",
        ],
        "docs_link": "/docs/hardware/i2c#recovery",
        "recoverable": True,
        "user_action_required": False,
    },
    1019: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "I2C-Protokoll nicht unterstützt",
        "message_user_de": "Konfigurations-Fehler: Der Sensor-Typ hat kein registriertes I2C-Kommunikationsprotokoll",
        "troubleshooting_de": [
            "1. Sensor-Datenblatt prüfen — unterstützt der Sensor I2C?",
            "2. I2C-Standard-Modus verwenden (100kHz)",
            "3. Alternative Sensor-Library prüfen oder Sensor-Typ korrigieren",
        ],
        "docs_link": "/docs/hardware/i2c#protocols",
        "recoverable": True,
        "user_action_required": True,
    },
}

# OneWire Errors (1020-1029)
ESP32_ONEWIRE_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1020: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "OneWire-Bus Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: OneWire-Bus konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. GPIO-Pin in Konfiguration prüfen",
            "2. Pull-up Widerstand (4.7k Ohm) zwischen Data und VCC anschließen",
            "3. Prüfen ob Pin nicht anderweitig belegt ist",
        ],
        "docs_link": "/docs/hardware/onewire#setup",
        "recoverable": False,
        "user_action_required": True,
    },
    1021: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "Keine OneWire-Geräte am Bus gefunden",
        "message_user_de": "Hardware-Warnung: Kein Sensor am OneWire-Bus erkannt",
        "troubleshooting_de": [
            "1. Sensor-Verkabelung prüfen (VCC, GND, Data)",
            "2. Pull-up Widerstand (4.7k Ohm) prüfen",
            "3. Bei langen Kabeln: Stärkeren Pull-up verwenden (2.2k Ohm)",
            "4. OneWire-Scan ausführen zum Debuggen",
        ],
        "docs_link": "/docs/sensors/ds18b20#no-devices",
        "recoverable": True,
        "user_action_required": True,
    },
    1022: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "OneWire-Lesevorgang fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Sensordaten konnten nicht gelesen werden",
        "troubleshooting_de": [
            "1. Kabelverbindung auf Wackelkontakt prüfen",
            "2. Sensor-Stromversorgung prüfen",
            "3. Bei parasitärer Versorgung: Externe 3.3V verwenden",
            "4. Sensor könnte defekt sein",
        ],
        "docs_link": "/docs/sensors/ds18b20#read-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    1023: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Ungültige OneWire ROM-Code Länge",
        "message_user_de": "Sensor-Konfiguration fehlgeschlagen: ROM-Code muss genau 16 Hex-Zeichen lang sein",
        "troubleshooting_de": [
            "1. OneWire-Scan ausführen: POST /api/v1/sensors/esp/{esp_id}/onewire/scan",
            "2. ROM-Code vollständig kopieren (16 Zeichen, z.B. '28FF641E8D3C0C79')",
            "3. Format prüfen: Nur Hex-Zeichen (0-9, A-F), keine Bindestriche",
        ],
        "docs_link": "/docs/sensors/ds18b20#rom-codes",
        "recoverable": True,
        "user_action_required": True,
    },
    1024: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "ROM-Code Parsing fehlgeschlagen",
        "message_user_de": "Sensor-Konfiguration fehlgeschlagen: ROM-Code konnte nicht verarbeitet werden",
        "troubleshooting_de": [
            "1. ROM-Code auf ungültige Zeichen prüfen",
            "2. Leerzeichen am Anfang oder Ende entfernen",
            "3. OneWire-Scan für korrekten Code nutzen",
        ],
        "docs_link": "/docs/sensors/ds18b20#rom-codes",
        "recoverable": True,
        "user_action_required": True,
    },
    1025: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "ROM-Code Prüfsumme (CRC) ungültig",
        "message_user_de": "Warnung: ROM-Code Prüfsumme ungültig (könnte Übertragungsfehler sein)",
        "troubleshooting_de": [
            "1. Sensor funktioniert möglicherweise trotzdem",
            "2. Falls Probleme: OneWire-Scan wiederholen",
            "3. Kabelverbindung auf Wackelkontakt prüfen",
        ],
        "docs_link": "/docs/sensors/ds18b20#crc",
        "recoverable": True,
        "user_action_required": False,
    },
    1026: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "OneWire Device nicht am Bus gefunden",
        "message_user_de": "Hardware-Fehler: Sensor antwortet nicht am OneWire-Bus",
        "troubleshooting_de": [
            "1. Physische Kabelverbindung prüfen",
            "2. Sensor-Stromversorgung prüfen",
            "3. Pull-up Widerstand (4.7k Ohm) am Bus prüfen",
            "4. OneWire-Scan ausführen, um zu sehen ob überhaupt Devices gefunden werden",
        ],
        "docs_link": "/docs/sensors/ds18b20#troubleshooting",
        "recoverable": True,
        "user_action_required": True,
    },
    1027: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "OneWire Bus nicht initialisiert",
        "message_user_de": "System-Fehler: OneWire-Bus wurde nicht korrekt gestartet",
        "troubleshooting_de": [
            "1. GPIO Pin in der Config prüfen",
            "2. Prüfen ob Pin bereits durch anderen Sensor/Aktor belegt ist",
            "3. ESP32 Pin-Capabilities prüfen (nicht alle Pins unterstützen OneWire)",
        ],
        "docs_link": "/docs/hardware/esp32#pins",
        "recoverable": False,
        "user_action_required": True,
    },
    1028: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "DS18B20 Lese-Timeout",
        "message_user_de": "Hardware-Fehler: Sensor antwortet nicht nach mehreren Versuchen (Timeout)",
        "troubleshooting_de": [
            "1. Kabelverbindung auf Wackelkontakt prüfen",
            "2. Kabellänge prüfen (zu lange Kabel brauchen stärkeren Pull-up)",
            "3. Sensor könnte defekt sein (Hitzeschaden?)",
        ],
        "docs_link": "/docs/sensors/ds18b20#timing",
        "recoverable": True,
        "user_action_required": True,
    },
    1029: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Duplizierter ROM-Code auf ESP32",
        "message_user_de": "Konfigurations-Fehler: Dieser Sensor (ROM) ist bereits auf diesem ESP registriert",
        "troubleshooting_de": [
            "1. Vorhandene Sensoren auf diesem ESP prüfen",
            "2. Falls der Sensor verschoben wurde: Alten Eintrag zuerst löschen",
            "3. OneWire-Scan für eindeutige Zuordnung nutzen",
        ],
        "docs_link": "/docs/sensors/ds18b20#duplicates",
        "recoverable": True,
        "user_action_required": True,
    },
}

# PWM Errors (1030-1032)
ESP32_PWM_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1030: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "PWM-Controller Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: PWM-Steuerung konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. GPIO-Pin auf PWM-Fähigkeit prüfen",
            "2. ESP32 neu starten",
            "3. Bei wiederholtem Fehler: Hardware-Defekt möglich",
        ],
        "docs_link": "/docs/hardware/pwm#setup",
        "recoverable": False,
        "user_action_required": True,
    },
    1031: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Alle PWM-Kanäle belegt",
        "message_user_de": "System-Limit: ESP32 hat nur 16 PWM-Kanäle, alle sind bereits in Verwendung",
        "troubleshooting_de": [
            "1. Anzahl der PWM-Aktoren prüfen (max. 16 pro ESP32)",
            "2. Nicht benötigte PWM-Aktoren entfernen",
            "3. Zweiten ESP32 für zusätzliche PWM-Kanäle verwenden",
        ],
        "docs_link": "/docs/hardware/pwm#channels",
        "recoverable": True,
        "user_action_required": True,
    },
    1032: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "PWM Duty-Cycle konnte nicht gesetzt werden",
        "message_user_de": "Hardware-Warnung: PWM-Wert konnte nicht angewendet werden",
        "troubleshooting_de": [
            "1. Wert-Bereich prüfen (0.0 - 1.0)",
            "2. PWM-Kanal wurde möglicherweise nicht korrekt initialisiert",
            "3. ESP32 neu starten",
        ],
        "docs_link": "/docs/hardware/pwm#duty-cycle",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Sensor Errors (1040-1043)
ESP32_SENSOR_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1040: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Sensor-Lesevorgang fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Sensordaten konnten nicht gelesen werden",
        "troubleshooting_de": [
            "1. Sensor-Verkabelung prüfen",
            "2. Sensor-Stromversorgung prüfen (3.3V oder 5V)",
            "3. Sensor-spezifische Diagnose durchführen (I2C-Scan, OneWire-Scan)",
            "4. Sensor könnte defekt sein",
        ],
        "docs_link": "/docs/sensors#troubleshooting",
        "recoverable": True,
        "user_action_required": True,
    },
    1041: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Sensor-Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Sensor konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. Konfiguration prüfen (GPIO, Sensor-Typ, Bus-Adresse)",
            "2. Sensor-Verkabelung prüfen",
            "3. Bei I2C: Adresse prüfen (I2C-Scan)",
            "4. Bei OneWire: ROM-Code prüfen (OneWire-Scan)",
        ],
        "docs_link": "/docs/sensors#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    1042: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Sensor nicht konfiguriert oder nicht gefunden",
        "message_user_de": "Konfigurations-Fehler: Der angeforderte Sensor existiert nicht auf diesem ESP",
        "troubleshooting_de": [
            "1. Sensor-Konfiguration in Server-DB prüfen",
            "2. Sensor zum ESP hinzufügen: POST /api/v1/sensors/",
            "3. ESP-Config neu laden (Neustart oder Config-Push)",
        ],
        "docs_link": "/docs/sensors#configuration",
        "recoverable": True,
        "user_action_required": True,
    },
    1043: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "Sensor-Lese-Timeout",
        "message_user_de": "Hardware-Warnung: Sensor antwortet nicht rechtzeitig",
        "troubleshooting_de": [
            "1. Kabelverbindung prüfen (Wackelkontakt)",
            "2. Sensor-Stromversorgung prüfen",
            "3. Bei wiederholtem Timeout: Sensor könnte defekt sein",
        ],
        "docs_link": "/docs/sensors#timeouts",
        "recoverable": True,
        "user_action_required": False,
    },
}

# DS18B20 Temperature Errors (1060-1063)
ESP32_DS18B20_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1060: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "DS18B20 Sensor-Fehler: -127°C zeigt Verbindungsproblem oder CRC-Fehler an",
        "message_user_de": "Hardware-Fehler: Temperatursensor meldet -127°C (Sensor getrennt oder defekt)",
        "troubleshooting_de": [
            "1. 4.7kOhm Pull-Up-Widerstand an DQ-Leitung prüfen",
            "2. Versorgungsspannung 3.3V am Sensor prüfen",
            "3. Kabel-Kontakte und Steckverbindungen prüfen",
            "4. Sensor tauschen wenn Problem bestehen bleibt",
        ],
        "docs_link": "/docs/sensors/ds18b20#sensor-fault",
        "recoverable": False,
        "user_action_required": True,
    },
    1061: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "DS18B20 Power-On-Reset erkannt (85°C Default-Wert)",
        "message_user_de": "Hardware-Warnung: Sensor meldet 85°C — keine Messung durchgeführt (Power-On-Reset)",
        "troubleshooting_de": [
            "1. Versorgungsspannung auf Stabilität prüfen (Spannungseinbrüche?)",
            "2. Bei parasitärem Modus: Externe 3.3V Versorgung verwenden (3-Wire)",
            "3. Entkopplungskondensator (100nF) nahe am Sensor einsetzen",
        ],
        "docs_link": "/docs/sensors/ds18b20#power-on-reset",
        "recoverable": True,
        "user_action_required": False,
    },
    1062: {
        "category": "HARDWARE",
        "severity": "WARNING",
        "message_de": "DS18B20 Temperatur außerhalb gültiger Range (-55°C bis +125°C)",
        "message_user_de": "Hardware-Warnung: Gemessene Temperatur liegt außerhalb des physikalisch möglichen Bereichs",
        "troubleshooting_de": [
            "1. Sensor-Umgebung prüfen — liegt die Temperatur wirklich im Extrembereich?",
            "2. Kalibrierung des Sensors prüfen",
            "3. Kurzschluss an DQ-Leitung ausschließen",
        ],
        "docs_link": "/docs/sensors/ds18b20#out-of-range",
        "recoverable": True,
        "user_action_required": False,
    },
    1063: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "DS18B20 Sensor im Betrieb getrennt",
        "message_user_de": "Hardware-Fehler: Temperatursensor war verbunden, ist aber jetzt nicht mehr erreichbar",
        "troubleshooting_de": [
            "1. Stecker und Kabelverbindungen prüfen (Wackelkontakt)",
            "2. OneWire-Bus Länge prüfen (max. ~5m ohne Repeater)",
            "3. Pull-Up-Widerstand (4.7kOhm) vorhanden und korrekt?",
            "4. Bei mehreren Sensoren: Einzeln testen um defekten zu identifizieren",
        ],
        "docs_link": "/docs/sensors/ds18b20#disconnected",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Actuator Errors (1050-1053)
ESP32_ACTUATOR_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    1050: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Aktor-Befehl fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Aktor konnte nicht gesteuert werden",
        "troubleshooting_de": [
            "1. Aktor-Verkabelung prüfen",
            "2. Relay/MOSFET-Treiber prüfen",
            "3. GPIO-Ausgangsfähigkeit prüfen (nicht alle Pins sind Output-fähig)",
            "4. Bei PWM: Wert-Bereich prüfen (0.0 - 1.0)",
        ],
        "docs_link": "/docs/actuators#troubleshooting",
        "recoverable": True,
        "user_action_required": True,
    },
    1051: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Aktor-Initialisierung fehlgeschlagen",
        "message_user_de": "Hardware-Fehler: Aktor konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. Konfiguration prüfen (GPIO, Aktor-Typ)",
            "2. GPIO auf Output-Fähigkeit prüfen",
            "3. Bei PWM-Aktor: Verfügbare PWM-Kanäle prüfen",
            "4. Pin-Konflikt mit Sensoren ausschließen",
        ],
        "docs_link": "/docs/actuators#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    1052: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Aktor nicht konfiguriert oder nicht gefunden",
        "message_user_de": "Konfigurations-Fehler: Der angeforderte Aktor existiert nicht auf diesem ESP",
        "troubleshooting_de": [
            "1. Aktor-Konfiguration in Server-DB prüfen",
            "2. Aktor zum ESP hinzufügen: POST /api/v1/actuators/",
            "3. ESP-Config neu laden (Neustart oder Config-Push)",
        ],
        "docs_link": "/docs/actuators#configuration",
        "recoverable": True,
        "user_action_required": True,
    },
    1053: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Aktor-GPIO-Konflikt mit Sensor",
        "message_user_de": "Konfigurations-Fehler: Dieser GPIO wird bereits von einem Sensor verwendet",
        "troubleshooting_de": [
            "1. GPIO-Belegung des ESP prüfen",
            "2. Anderen GPIO für den Aktor wählen",
            "3. Falls beabsichtigt: Sensor zuerst entfernen",
        ],
        "docs_link": "/docs/actuators#gpio-conflicts",
        "recoverable": True,
        "user_action_required": True,
    },
}


# ============================================
# SERVICE ERROR CODES (2000-2999)
# ============================================

# NVS Errors (2001-2005)
ESP32_NVS_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    2001: {
        "category": "SERVICE",
        "severity": "CRITICAL",
        "message_de": "NVS-Speicher Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: Interner Speicher konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Falls wiederholt: NVS löschen (esptool.py erase_flash)",
            "3. Firmware neu flashen",
            "4. Bei wiederholtem Fehler: Flash-Speicher könnte defekt sein",
        ],
        "docs_link": "/docs/system/nvs#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    2002: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "NVS-Lesevorgang fehlgeschlagen",
        "message_user_de": "System-Fehler: Konfiguration konnte nicht aus Speicher gelesen werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Server-Config neu pushen",
            "3. Falls wiederholt: NVS-Partition könnte korrupt sein",
        ],
        "docs_link": "/docs/system/nvs#read-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    2003: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "NVS-Schreibvorgang fehlgeschlagen",
        "message_user_de": "System-Fehler: Konfiguration konnte nicht gespeichert werden (Speicher voll?)",
        "troubleshooting_de": [
            "1. NVS-Speicher könnte voll sein",
            "2. Nicht benötigte Konfigurationen löschen",
            "3. NVS-Partition komplett löschen und neu konfigurieren",
            "4. Flash-Speicher könnte defekt sein (Write-Cycles erschöpft)",
        ],
        "docs_link": "/docs/system/nvs#write-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    2004: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "NVS-Namespace konnte nicht geöffnet werden",
        "message_user_de": "System-Fehler: Interner Speicherbereich nicht zugänglich",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. NVS-Partition könnte korrupt sein",
            "3. Firmware neu flashen mit NVS-Erase",
        ],
        "docs_link": "/docs/system/nvs#namespaces",
        "recoverable": False,
        "user_action_required": True,
    },
    2005: {
        "category": "SERVICE",
        "severity": "WARNING",
        "message_de": "NVS-Namespace löschen fehlgeschlagen",
        "message_user_de": "System-Warnung: Alte Konfiguration konnte nicht gelöscht werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Falls kritisch: NVS komplett löschen (esptool.py)",
        ],
        "docs_link": "/docs/system/nvs#clear",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Config Errors (2010-2014)
ESP32_CONFIG_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    2010: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Konfigurationsdaten ungültig",
        "message_user_de": "Konfigurations-Fehler: Die empfangenen Daten sind fehlerhaft",
        "troubleshooting_de": [
            "1. Server-Konfiguration prüfen",
            "2. JSON-Format prüfen (Syntax-Fehler?)",
            "3. Pflichtfelder prüfen (esp_id, sensors, actuators)",
        ],
        "docs_link": "/docs/configuration#validation",
        "recoverable": True,
        "user_action_required": True,
    },
    2011: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Erforderliche Konfiguration fehlt",
        "message_user_de": "Konfigurations-Fehler: Wichtige Einstellungen fehlen",
        "troubleshooting_de": [
            "1. Server-Konfiguration vollständig?",
            "2. WiFi-Credentials konfiguriert?",
            "3. MQTT-Broker konfiguriert?",
            "4. ESP im Server registriert?",
        ],
        "docs_link": "/docs/configuration#required-fields",
        "recoverable": True,
        "user_action_required": True,
    },
    2012: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Konfiguration laden fehlgeschlagen",
        "message_user_de": "System-Fehler: Gespeicherte Konfiguration konnte nicht geladen werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Server-Config neu pushen",
            "3. NVS könnte korrupt sein",
        ],
        "docs_link": "/docs/configuration#loading",
        "recoverable": True,
        "user_action_required": True,
    },
    2013: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Konfiguration speichern fehlgeschlagen",
        "message_user_de": "System-Fehler: Neue Konfiguration konnte nicht gespeichert werden",
        "troubleshooting_de": [
            "1. NVS-Speicher könnte voll sein",
            "2. ESP32 neu starten und erneut versuchen",
            "3. Alte Konfigurationen löschen",
        ],
        "docs_link": "/docs/configuration#saving",
        "recoverable": True,
        "user_action_required": True,
    },
    2014: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Konfiguration-Validierung fehlgeschlagen",
        "message_user_de": "Konfigurations-Fehler: Konfiguration enthält ungültige Werte",
        "troubleshooting_de": [
            "1. GPIO-Nummern prüfen (0-39)",
            "2. Sensor-/Aktor-Typen prüfen",
            "3. Doppelte GPIO-Zuweisungen ausschließen",
            "4. Server-Logs für Details prüfen",
        ],
        "docs_link": "/docs/configuration#validation",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Logger Errors (2020-2021)
ESP32_LOGGER_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    2020: {
        "category": "SERVICE",
        "severity": "WARNING",
        "message_de": "Logger-System Initialisierung fehlgeschlagen",
        "message_user_de": "System-Warnung: Logging-System nicht verfügbar",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Speicherverbrauch prüfen (Heap)",
            "3. Kein kritischer Fehler - System läuft weiter ohne Logs",
        ],
        "docs_link": "/docs/system/logging",
        "recoverable": True,
        "user_action_required": False,
    },
    2021: {
        "category": "SERVICE",
        "severity": "WARNING",
        "message_de": "Logger-Buffer voll (Nachrichten verworfen)",
        "message_user_de": "System-Warnung: Log-Nachrichten werden verworfen (Buffer voll)",
        "troubleshooting_de": [
            "1. Hohes Log-Aufkommen reduzieren",
            "2. Log-Level erhöhen (z.B. INFO statt DEBUG)",
            "3. ESP32 neu starten um Buffer zu leeren",
        ],
        "docs_link": "/docs/system/logging#buffer",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Storage Errors (2030-2032)
ESP32_STORAGE_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    2030: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "Storage-Manager Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: Speicher-System konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Firmware neu flashen",
            "3. Flash-Speicher könnte defekt sein",
        ],
        "docs_link": "/docs/system/storage",
        "recoverable": False,
        "user_action_required": True,
    },
    2031: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "Storage-Lesevorgang fehlgeschlagen",
        "message_user_de": "System-Fehler: Daten konnten nicht aus Speicher gelesen werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Datei-System könnte korrupt sein",
            "3. Firmware neu flashen",
        ],
        "docs_link": "/docs/system/storage#read-errors",
        "recoverable": True,
        "user_action_required": True,
    },
    2032: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "Storage-Schreibvorgang fehlgeschlagen",
        "message_user_de": "System-Fehler: Daten konnten nicht gespeichert werden",
        "troubleshooting_de": [
            "1. Speicher könnte voll sein",
            "2. ESP32 neu starten",
            "3. Alte Dateien löschen",
        ],
        "docs_link": "/docs/system/storage#write-errors",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Subzone Errors (2500-2506)
ESP32_SUBZONE_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    2500: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Ungültiges Subzone-ID Format",
        "message_user_de": "Konfigurations-Fehler: Subzone-ID hat ungültiges Format",
        "troubleshooting_de": [
            "1. Subzone-ID muss 1-32 Zeichen lang sein",
            "2. Nur alphanumerische Zeichen und Unterstriche erlaubt",
            "3. Beispiel: 'bewaesserung_nord' oder 'zone_1'",
        ],
        "docs_link": "/docs/zones/subzones#naming",
        "recoverable": True,
        "user_action_required": True,
    },
    2501: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "GPIO bereits anderer Subzone zugewiesen",
        "message_user_de": "Konfigurations-Fehler: Dieser GPIO gehört bereits zu einer anderen Subzone",
        "troubleshooting_de": [
            "1. GPIO-Zuweisung prüfen",
            "2. GPIO aus alter Subzone entfernen",
            "3. Oder anderen GPIO verwenden",
        ],
        "docs_link": "/docs/zones/subzones#gpio-assignment",
        "recoverable": True,
        "user_action_required": True,
    },
    2502: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Parent-Zone stimmt nicht mit ESP-Zone überein",
        "message_user_de": "Konfigurations-Fehler: Die übergeordnete Zone passt nicht zur ESP-Zuweisung",
        "troubleshooting_de": [
            "1. ESP ist einer anderen Zone zugewiesen",
            "2. Zuerst ESP der korrekten Zone zuweisen",
            "3. Oder Subzone unter der richtigen Parent-Zone erstellen",
        ],
        "docs_link": "/docs/zones/subzones#parent-zone",
        "recoverable": True,
        "user_action_required": True,
    },
    2503: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Subzone nicht gefunden",
        "message_user_de": "Konfigurations-Fehler: Die angegebene Subzone existiert nicht",
        "troubleshooting_de": [
            "1. Subzone-ID prüfen",
            "2. Subzone zuerst erstellen",
            "3. GET /api/v1/subzones/ für Liste verfügbarer Subzones",
        ],
        "docs_link": "/docs/zones/subzones#management",
        "recoverable": True,
        "user_action_required": True,
    },
    2504: {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "GPIO nicht in Safe-Pins-Liste",
        "message_user_de": "Konfigurations-Fehler: Dieser GPIO ist nicht für Subzones freigegeben",
        "troubleshooting_de": [
            "1. GPIO muss zuerst als Safe-Pin konfiguriert werden",
            "2. Reservierte System-Pins können nicht verwendet werden",
            "3. Safe-Pins-Liste im ESP-Config prüfen",
        ],
        "docs_link": "/docs/zones/subzones#safe-pins",
        "recoverable": True,
        "user_action_required": True,
    },
    2505: {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Safe-Mode Aktivierung fehlgeschlagen",
        "message_user_de": "System-Fehler: GPIO konnte nicht in sicheren Zustand versetzt werden",
        "troubleshooting_de": [
            "1. GPIO könnte von anderem Prozess blockiert sein",
            "2. ESP32 neu starten",
            "3. Hardware-Konflikt prüfen",
        ],
        "docs_link": "/docs/zones/subzones#safe-mode",
        "recoverable": False,
        "user_action_required": True,
    },
    2506: {
        "category": "SERVICE",
        "severity": "ERROR",
        "message_de": "Subzone-Konfiguration speichern fehlgeschlagen",
        "message_user_de": "System-Fehler: Subzone-Einstellungen konnten nicht gespeichert werden",
        "troubleshooting_de": [
            "1. NVS-Speicher könnte voll sein",
            "2. ESP32 neu starten",
            "3. Alte Subzone-Konfigurationen löschen",
        ],
        "docs_link": "/docs/zones/subzones#persistence",
        "recoverable": True,
        "user_action_required": True,
    },
}


# ============================================
# COMMUNICATION ERROR CODES (3000-3999)
# ============================================

# WiFi Errors (3001-3005)
ESP32_WIFI_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    3001: {
        "category": "COMMUNICATION",
        "severity": "CRITICAL",
        "message_de": "WiFi-Modul Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: WiFi konnte nicht gestartet werden",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Firmware neu flashen",
            "3. Bei wiederholtem Fehler: Hardware-Defekt möglich",
        ],
        "docs_link": "/docs/network/wifi#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    3002: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "WiFi-Verbindung Timeout",
        "message_user_de": "Netzwerk-Fehler: Verbindung zum WLAN-Router nicht möglich (Timeout)",
        "troubleshooting_de": [
            "1. WLAN-Router erreichbar?",
            "2. Signal-Stärke prüfen (ESP zu weit vom Router?)",
            "3. SSID und Passwort korrekt?",
            "4. Router neu starten",
        ],
        "docs_link": "/docs/network/wifi#connection-timeout",
        "recoverable": True,
        "user_action_required": True,
    },
    3003: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "WiFi-Verbindung fehlgeschlagen",
        "message_user_de": "Netzwerk-Fehler: WLAN-Verbindung abgelehnt (falsches Passwort oder SSID nicht gefunden)",
        "troubleshooting_de": [
            "1. SSID korrekt geschrieben? (Groß-/Kleinschreibung beachten)",
            "2. Passwort korrekt?",
            "3. WLAN-Router sendet auf 2.4GHz? (ESP32 unterstützt kein 5GHz)",
            "4. MAC-Adressfilter im Router prüfen",
        ],
        "docs_link": "/docs/network/wifi#connection-failed",
        "recoverable": True,
        "user_action_required": True,
    },
    3004: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "WiFi-Verbindung unerwartet getrennt",
        "message_user_de": "Netzwerk-Warnung: WLAN-Verbindung wurde getrennt",
        "troubleshooting_de": [
            "1. Router-Reichweite prüfen",
            "2. Router überlastet? (zu viele Geräte)",
            "3. Interferenzen durch andere Geräte",
            "4. ESP versucht automatisch Reconnect",
        ],
        "docs_link": "/docs/network/wifi#disconnection",
        "recoverable": True,
        "user_action_required": False,
    },
    3005: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "WiFi-SSID nicht konfiguriert",
        "message_user_de": "Konfigurations-Fehler: Keine WLAN-Zugangsdaten hinterlegt",
        "troubleshooting_de": [
            "1. WLAN-Credentials im Server konfigurieren",
            "2. ESP-Config pushen",
            "3. Oder ESP im AP-Modus neu provisionieren",
        ],
        "docs_link": "/docs/network/wifi#provisioning",
        "recoverable": True,
        "user_action_required": True,
    },
}

# MQTT Errors (3010-3016)
ESP32_MQTT_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    3010: {
        "category": "COMMUNICATION",
        "severity": "CRITICAL",
        "message_de": "MQTT-Client Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: MQTT-Verbindung konnte nicht vorbereitet werden",
        "troubleshooting_de": [
            "1. Heap-Speicher prüfen (zu wenig RAM?)",
            "2. ESP32 neu starten",
            "3. Firmware-Bug möglich - Logs prüfen",
        ],
        "docs_link": "/docs/network/mqtt#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    3011: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "MQTT-Broker Verbindung fehlgeschlagen",
        "message_user_de": "Netzwerk-Fehler: Verbindung zum MQTT-Server nicht möglich",
        "troubleshooting_de": [
            "1. MQTT-Broker läuft? (mosquitto)",
            "2. Broker-IP und Port korrekt? (Standard: 1883)",
            "3. Firewall blockiert Port 1883?",
            "4. Bei TLS: Zertifikate prüfen",
        ],
        "docs_link": "/docs/network/mqtt#connection",
        "recoverable": True,
        "user_action_required": True,
    },
    3012: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "MQTT-Publish fehlgeschlagen",
        "message_user_de": "Netzwerk-Warnung: Nachricht konnte nicht gesendet werden",
        "troubleshooting_de": [
            "1. MQTT-Verbindung noch aktiv?",
            "2. Topic-Name korrekt?",
            "3. Payload zu groß? (max. 256KB)",
            "4. Nachricht wird bei Reconnect wiederholt",
        ],
        "docs_link": "/docs/network/mqtt#publishing",
        "recoverable": True,
        "user_action_required": False,
    },
    3013: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "MQTT-Subscribe fehlgeschlagen",
        "message_user_de": "Netzwerk-Fehler: Topic-Abonnement nicht möglich",
        "troubleshooting_de": [
            "1. MQTT-Verbindung aktiv?",
            "2. Topic-Name korrekt formatiert?",
            "3. Berechtigungen auf Broker prüfen",
            "4. ESP32 neu starten",
        ],
        "docs_link": "/docs/network/mqtt#subscribing",
        "recoverable": True,
        "user_action_required": True,
    },
    3014: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "MQTT-Verbindung zum Broker getrennt",
        "message_user_de": "Netzwerk-Warnung: Verbindung zum MQTT-Server verloren",
        "troubleshooting_de": [
            "1. MQTT-Broker läuft noch?",
            "2. Netzwerk-Verbindung stabil?",
            "3. ESP versucht automatisch Reconnect",
            "4. Offline-Nachrichten werden zwischengespeichert",
        ],
        "docs_link": "/docs/network/mqtt#disconnection",
        "recoverable": True,
        "user_action_required": False,
    },
    3015: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "MQTT-Offline-Buffer voll (Nachrichten verworfen)",
        "message_user_de": "System-Warnung: Offline-Speicher für Nachrichten ist voll",
        "troubleshooting_de": [
            "1. MQTT-Verbindung wiederherstellen",
            "2. Ältere Nachrichten werden verworfen",
            "3. Nach Reconnect werden neuere Nachrichten gesendet",
        ],
        "docs_link": "/docs/network/mqtt#offline-buffer",
        "recoverable": True,
        "user_action_required": False,
    },
    3016: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "MQTT-Payload ungültig oder fehlerhaft",
        "message_user_de": "Daten-Fehler: Empfangene MQTT-Nachricht konnte nicht verarbeitet werden",
        "troubleshooting_de": [
            "1. JSON-Format der Nachricht prüfen",
            "2. Pflichtfelder vorhanden?",
            "3. Server-Logs für Details prüfen",
        ],
        "docs_link": "/docs/network/mqtt#payload-format",
        "recoverable": True,
        "user_action_required": True,
    },
}

# HTTP Errors (3020-3023)
ESP32_HTTP_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    3020: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "HTTP-Client Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: HTTP-Verbindung konnte nicht vorbereitet werden",
        "troubleshooting_de": [
            "1. Heap-Speicher prüfen",
            "2. ESP32 neu starten",
            "3. TLS-Zertifikate korrekt?",
        ],
        "docs_link": "/docs/network/http#initialization",
        "recoverable": False,
        "user_action_required": True,
    },
    3021: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "HTTP-Request fehlgeschlagen (Server nicht erreichbar)",
        "message_user_de": "Netzwerk-Fehler: Server ist nicht erreichbar",
        "troubleshooting_de": [
            "1. Server läuft?",
            "2. URL korrekt?",
            "3. Firewall blockiert Verbindung?",
            "4. DNS-Auflösung funktioniert?",
        ],
        "docs_link": "/docs/network/http#requests",
        "recoverable": True,
        "user_action_required": True,
    },
    3022: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "HTTP-Antwort ungültig oder fehlerhaft",
        "message_user_de": "Daten-Fehler: Server-Antwort konnte nicht verarbeitet werden",
        "troubleshooting_de": [
            "1. Server-API korrekt?",
            "2. Response-Format prüfen",
            "3. Server-Logs für Details prüfen",
        ],
        "docs_link": "/docs/network/http#responses",
        "recoverable": True,
        "user_action_required": True,
    },
    3023: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "HTTP-Request Timeout",
        "message_user_de": "Netzwerk-Warnung: Server antwortet nicht rechtzeitig",
        "troubleshooting_de": [
            "1. Server überlastet?",
            "2. Netzwerk-Verbindung langsam?",
            "3. Request wird automatisch wiederholt",
        ],
        "docs_link": "/docs/network/http#timeouts",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Network Errors (3030-3032)
ESP32_NETWORK_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    3030: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "Netzwerk nicht erreichbar",
        "message_user_de": "Netzwerk-Fehler: Keine Verbindung zum Netzwerk möglich",
        "troubleshooting_de": [
            "1. WiFi-Verbindung prüfen",
            "2. Router-Verbindung zum Internet prüfen",
            "3. Gateway erreichbar?",
        ],
        "docs_link": "/docs/network#connectivity",
        "recoverable": True,
        "user_action_required": True,
    },
    3031: {
        "category": "COMMUNICATION",
        "severity": "ERROR",
        "message_de": "DNS-Auflösung fehlgeschlagen",
        "message_user_de": "Netzwerk-Fehler: Hostname konnte nicht aufgelöst werden",
        "troubleshooting_de": [
            "1. DNS-Server im Router korrekt konfiguriert?",
            "2. Hostname korrekt geschrieben?",
            "3. Alternativ: IP-Adresse direkt verwenden",
        ],
        "docs_link": "/docs/network#dns",
        "recoverable": True,
        "user_action_required": True,
    },
    3032: {
        "category": "COMMUNICATION",
        "severity": "WARNING",
        "message_de": "Netzwerk-Verbindung verloren",
        "message_user_de": "Netzwerk-Warnung: Verbindung wurde unterbrochen",
        "troubleshooting_de": [
            "1. WiFi-Signal prüfen",
            "2. Router-Status prüfen",
            "3. ESP versucht automatisch Reconnect",
        ],
        "docs_link": "/docs/network#connection-lost",
        "recoverable": True,
        "user_action_required": False,
    },
}


# ============================================
# APPLICATION ERROR CODES (4000-4999)
# ============================================

# State Errors (4001-4003)
ESP32_STATE_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4001: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Ungültiger System-Zustand",
        "message_user_de": "System-Fehler: ESP befindet sich in ungültigem Zustand",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Server-Config neu pushen",
            "3. Firmware-Bug möglich - Logs prüfen",
        ],
        "docs_link": "/docs/system/states",
        "recoverable": True,
        "user_action_required": True,
    },
    4002: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Ungültiger Zustandsübergang",
        "message_user_de": "System-Fehler: Angeforderte Aktion im aktuellen Zustand nicht möglich",
        "troubleshooting_de": [
            "1. Aktueller Zustand des ESP prüfen",
            "2. Zuerst in gültigen Zustand wechseln",
            "3. Beispiel: Sensoren können nur im OPERATIONAL-Zustand gelesen werden",
        ],
        "docs_link": "/docs/system/states#transitions",
        "recoverable": True,
        "user_action_required": True,
    },
    4003: {
        "category": "APPLICATION",
        "severity": "CRITICAL",
        "message_de": "State-Machine blockiert (keine gültigen Übergänge)",
        "message_user_de": "System-Fehler: ESP ist in einem Deadlock-Zustand gefangen",
        "troubleshooting_de": [
            "1. ESP32 MUSS neu gestartet werden",
            "2. Logs vor Neustart sichern",
            "3. Firmware-Bug melden",
        ],
        "docs_link": "/docs/system/states#deadlock",
        "recoverable": False,
        "user_action_required": True,
    },
}

# Operation Errors (4010-4012)
ESP32_OPERATION_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4010: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "Operation Timeout",
        "message_user_de": "System-Warnung: Operation wurde nicht rechtzeitig abgeschlossen",
        "troubleshooting_de": [
            "1. Operation wird automatisch wiederholt",
            "2. Bei wiederholtem Timeout: Hardware prüfen",
            "3. Timeout-Einstellungen anpassen",
        ],
        "docs_link": "/docs/system/operations#timeouts",
        "recoverable": True,
        "user_action_required": False,
    },
    4011: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Operation fehlgeschlagen",
        "message_user_de": "System-Fehler: Angeforderte Operation konnte nicht ausgeführt werden",
        "troubleshooting_de": [
            "1. Detaillierte Fehler-Logs prüfen",
            "2. Operation erneut versuchen",
            "3. Voraussetzungen für Operation prüfen",
        ],
        "docs_link": "/docs/system/operations#failures",
        "recoverable": True,
        "user_action_required": True,
    },
    4012: {
        "category": "APPLICATION",
        "severity": "INFO",
        "message_de": "Operation abgebrochen",
        "message_user_de": "System-Info: Operation wurde vom Benutzer oder System abgebrochen",
        "troubleshooting_de": [
            "1. Kein Fehler - Operation wurde absichtlich gestoppt",
            "2. Bei unerwartetem Abbruch: Logs prüfen",
        ],
        "docs_link": "/docs/system/operations#cancellation",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Command Errors (4020-4022)
ESP32_COMMAND_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4020: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Befehl ungültig oder unbekannt",
        "message_user_de": "Befehls-Fehler: Unbekannter oder ungültiger Befehl empfangen",
        "troubleshooting_de": [
            "1. Befehlsname prüfen",
            "2. API-Dokumentation konsultieren",
            "3. Server-Firmware aktuell?",
        ],
        "docs_link": "/docs/commands",
        "recoverable": True,
        "user_action_required": True,
    },
    4021: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Befehl konnte nicht geparst werden",
        "message_user_de": "Befehls-Fehler: Befehlsformat fehlerhaft",
        "troubleshooting_de": [
            "1. JSON-Syntax prüfen",
            "2. Pflichtfelder vorhanden?",
            "3. Datentypen korrekt?",
        ],
        "docs_link": "/docs/commands#format",
        "recoverable": True,
        "user_action_required": True,
    },
    4022: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Befehlsausführung fehlgeschlagen",
        "message_user_de": "Befehls-Fehler: Befehl konnte nicht ausgeführt werden",
        "troubleshooting_de": [
            "1. Voraussetzungen für Befehl prüfen",
            "2. ESP-Zustand prüfen",
            "3. Hardware-Komponente funktionsfähig?",
        ],
        "docs_link": "/docs/commands#execution",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Payload Errors (4030-4032)
ESP32_PAYLOAD_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4030: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Payload ungültig oder fehlerhaft",
        "message_user_de": "Daten-Fehler: Empfangene Daten sind ungültig",
        "troubleshooting_de": [
            "1. JSON-Format prüfen",
            "2. Pflichtfelder vorhanden?",
            "3. Datentypen korrekt?",
        ],
        "docs_link": "/docs/api/payloads",
        "recoverable": True,
        "user_action_required": True,
    },
    4031: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Payload zu groß",
        "message_user_de": "Daten-Fehler: Datenpaket überschreitet maximale Größe",
        "troubleshooting_de": [
            "1. Maximale Payload-Größe: 256KB",
            "2. Daten aufteilen (Batch-Requests)",
            "3. Unnötige Felder entfernen",
        ],
        "docs_link": "/docs/api/payloads#size-limits",
        "recoverable": True,
        "user_action_required": True,
    },
    4032: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Payload-Parsing fehlgeschlagen (JSON-Syntax-Fehler)",
        "message_user_de": "Daten-Fehler: JSON konnte nicht verarbeitet werden",
        "troubleshooting_de": [
            "1. JSON-Syntax validieren (jsonlint.com)",
            "2. Anführungszeichen und Kommas prüfen",
            "3. Escape-Sequenzen korrekt?",
        ],
        "docs_link": "/docs/api/payloads#json-format",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Memory Errors (4040-4042)
ESP32_MEMORY_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4040: {
        "category": "APPLICATION",
        "severity": "CRITICAL",
        "message_de": "Speicher voll (Heap erschöpft)",
        "message_user_de": "System-Fehler: ESP32 hat keinen freien Arbeitsspeicher mehr",
        "troubleshooting_de": [
            "1. ESP32 SOFORT neu starten",
            "2. Anzahl Sensoren/Aktoren reduzieren",
            "3. Firmware-Speicherleck möglich - melden",
        ],
        "docs_link": "/docs/system/memory",
        "recoverable": False,
        "user_action_required": True,
    },
    4041: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Speicher-Allokation fehlgeschlagen",
        "message_user_de": "System-Fehler: Speicher konnte nicht reserviert werden",
        "troubleshooting_de": [
            "1. Freier Heap-Speicher prüfen (Diagnostics)",
            "2. ESP32 neu starten",
            "3. Konfiguration vereinfachen (weniger Sensoren)",
        ],
        "docs_link": "/docs/system/memory#allocation",
        "recoverable": True,
        "user_action_required": True,
    },
    4042: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "Speicherleck erkannt",
        "message_user_de": "System-Warnung: Mögliches Speicherleck erkannt",
        "troubleshooting_de": [
            "1. Heap-Verbrauch über Zeit beobachten",
            "2. Bei stetigem Anstieg: Firmware-Bug melden",
            "3. ESP32 regelmäßig neu starten als Workaround",
        ],
        "docs_link": "/docs/system/memory#leaks",
        "recoverable": True,
        "user_action_required": True,
    },
}

# System Errors (4050-4052)
ESP32_SYSTEM_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4050: {
        "category": "APPLICATION",
        "severity": "CRITICAL",
        "message_de": "System-Initialisierung fehlgeschlagen",
        "message_user_de": "System-Fehler: ESP32 konnte nicht korrekt starten",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Serial-Monitor für Boot-Logs prüfen",
            "3. Firmware neu flashen",
            "4. Hardware-Defekt möglich",
        ],
        "docs_link": "/docs/system/boot",
        "recoverable": False,
        "user_action_required": True,
    },
    4051: {
        "category": "APPLICATION",
        "severity": "INFO",
        "message_de": "System-Neustart angefordert",
        "message_user_de": "System-Info: ESP32 wird neu gestartet",
        "troubleshooting_de": [
            "1. Kein Fehler - geplanter Neustart",
            "2. ESP startet automatisch neu",
            "3. Bei unerwartetem Neustart: Logs prüfen",
        ],
        "docs_link": "/docs/system/restart",
        "recoverable": True,
        "user_action_required": False,
    },
    4052: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "System im Safe-Mode (Fehler erkannt)",
        "message_user_de": "System-Warnung: ESP32 läuft im eingeschränkten Safe-Mode",
        "troubleshooting_de": [
            "1. Kritische Fehler haben Safe-Mode ausgelöst",
            "2. Fehler-Logs prüfen und beheben",
            "3. ESP32 neu starten um Safe-Mode zu verlassen",
        ],
        "docs_link": "/docs/system/safe-mode",
        "recoverable": True,
        "user_action_required": True,
    },
}

# Task Errors (4060-4062)
ESP32_TASK_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4060: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "FreeRTOS-Task fehlgeschlagen",
        "message_user_de": "System-Fehler: Hintergrund-Aufgabe ist abgestürzt",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. Stack-Overflow möglich - Task-Stack erhöhen",
            "3. Firmware-Bug melden mit Logs",
        ],
        "docs_link": "/docs/system/tasks",
        "recoverable": True,
        "user_action_required": True,
    },
    4061: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "FreeRTOS-Task Timeout",
        "message_user_de": "System-Warnung: Hintergrund-Aufgabe reagiert nicht rechtzeitig",
        "troubleshooting_de": [
            "1. System könnte überlastet sein",
            "2. Wird automatisch überwacht",
            "3. Bei wiederholtem Timeout: ESP32 neu starten",
        ],
        "docs_link": "/docs/system/tasks#timeouts",
        "recoverable": True,
        "user_action_required": False,
    },
    4062: {
        "category": "APPLICATION",
        "subcategory": "MQTT_PUBLISH_BACKPRESSURE",
        "severity": "WARNING",
        "message_de": "FreeRTOS Task-Queue voll",
        "message_user_de": "System-Warnung: MQTT-Veroeffentlichung unter Last (kurzfristiger Burst)",
        "troubleshooting_de": [
            "1. System verarbeitet Aufgaben langsamer als neue ankommen",
            "2. Ältere Aufgaben werden verworfen",
            "3. Sensor-Polling-Rate reduzieren",
            "4. Backpressure: Queue-Fuellstand aus Heartbeat pruefen (publish_queue_hwm, shed/drop)",
            "5. Bei anhaltendem Druck: Firmware-Emitter-Raten fuer Non-Critical-Pfade reduzieren",
        ],
        "docs_link": "/docs/system/tasks#queues",
        "recoverable": True,
        "user_action_required": False,
    },
}

# Watchdog Errors (4070-4072)
ESP32_WATCHDOG_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4070: {
        "category": "APPLICATION",
        "severity": "CRITICAL",
        "message_de": "Watchdog-Timeout erkannt (System-Hang)",
        "message_user_de": "System-Fehler: ESP32 hat nicht rechtzeitig reagiert (möglicher System-Hang)",
        "troubleshooting_de": [
            "1. ESP32 wird automatisch neu gestartet",
            "2. Logs vor Watchdog-Reset prüfen",
            "3. Blockierende Operation identifizieren",
            "4. Firmware-Bug melden",
        ],
        "docs_link": "/docs/system/watchdog",
        "recoverable": False,
        "user_action_required": True,
    },
    4071: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "Watchdog-Feed blockiert: Circuit-Breaker offen",
        "message_user_de": "System-Warnung: Watchdog wird nicht gefüttert wegen offener Circuit-Breaker",
        "troubleshooting_de": [
            "1. Fehlerhafte Komponenten prüfen",
            "2. Circuit-Breaker schützen vor Kaskadenfehlern",
            "3. Fehler beheben um Circuit-Breaker zu schließen",
        ],
        "docs_link": "/docs/system/watchdog#circuit-breaker",
        "recoverable": True,
        "user_action_required": True,
    },
    4072: {
        "category": "APPLICATION",
        "severity": "CRITICAL",
        "message_de": "Watchdog-Feed blockiert: Kritische Fehler aktiv",
        "message_user_de": "System-Fehler: Watchdog gestoppt wegen kritischer Fehler",
        "troubleshooting_de": [
            "1. Kritische Fehler SOFORT beheben",
            "2. ESP32 wird möglicherweise neu gestartet",
            "3. Fehler-Logs analysieren",
        ],
        "docs_link": "/docs/system/watchdog#critical-errors",
        "recoverable": False,
        "user_action_required": True,
    },
}

# Device Discovery Errors (4200-4202)
ESP32_DISCOVERY_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    4200: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Gerät vom Server-Administrator abgelehnt",
        "message_user_de": "Registrierungs-Fehler: Dieser ESP wurde vom Administrator abgelehnt",
        "troubleshooting_de": [
            "1. Administrator kontaktieren",
            "2. ESP-ID prüfen (korrekt?)",
            "3. Neuen Registrierungsantrag stellen",
        ],
        "docs_link": "/docs/discovery#rejected",
        "recoverable": True,
        "user_action_required": True,
    },
    4201: {
        "category": "APPLICATION",
        "severity": "WARNING",
        "message_de": "Timeout bei Server-Genehmigung",
        "message_user_de": "Registrierungs-Warnung: Keine Antwort vom Server bei Registrierung",
        "troubleshooting_de": [
            "1. Server erreichbar?",
            "2. Administrator muss ESP freigeben",
            "3. ESP versucht automatisch erneut",
        ],
        "docs_link": "/docs/discovery#timeout",
        "recoverable": True,
        "user_action_required": True,
    },
    4202: {
        "category": "APPLICATION",
        "severity": "ERROR",
        "message_de": "Zuvor genehmigtes Gerät wurde widerrufen",
        "message_user_de": "Registrierungs-Fehler: Die Genehmigung für diesen ESP wurde zurückgezogen",
        "troubleshooting_de": [
            "1. Administrator kontaktieren",
            "2. Mögliche Gründe: Sicherheitsbedenken, Gerätewechsel",
            "3. Neue Genehmigung anfordern",
        ],
        "docs_link": "/docs/discovery#revoked",
        "recoverable": True,
        "user_action_required": True,
    },
}


# ============================================
# CONFIG ERROR CODES (String-based, from ESP32)
# ============================================

# ESP32 Config-Response Error Codes (String-basiert)
# Diese werden bei config_response MQTT-Nachrichten verwendet
ESP32_CONFIG_ERROR_MESSAGES_DE: Dict[str, Dict[str, Any]] = {
    "NONE": {
        "category": "CONFIG",
        "severity": "INFO",
        "message_de": "Erfolgreich",
        "message_user_de": "Konfiguration erfolgreich übernommen",
        "troubleshooting_de": [],
        "recoverable": True,
        "user_action_required": False,
    },
    "JSON_PARSE_ERROR": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "JSON-Parsing fehlgeschlagen",
        "message_user_de": "Die Konfigurationsdaten konnten nicht verarbeitet werden (ungültiges JSON-Format)",
        "troubleshooting_de": [
            "1. Server-Konfiguration auf Syntax-Fehler prüfen",
            "2. JSON-Format validieren (jsonlint.com)",
            "3. Server-Logs für Details prüfen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "VALIDATION_FAILED": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Validierung fehlgeschlagen",
        "message_user_de": "Die Konfiguration enthält ungültige Werte und wurde vom ESP32 abgelehnt",
        "troubleshooting_de": [
            "1. GPIO-Nummern auf Gültigkeit prüfen (0-39)",
            "2. Sensor-/Aktor-Typen prüfen",
            "3. Doppelte GPIO-Zuweisungen ausschließen",
            "4. ESP32-Logs für Details prüfen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "GPIO_CONFLICT": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "GPIO-Konflikt erkannt",
        "message_user_de": "Der GPIO-Pin wird bereits von einem anderen Sensor oder Aktor verwendet",
        "troubleshooting_de": [
            "1. Aktuelle GPIO-Belegung des ESP prüfen",
            "2. Konflikt auflösen: Anderen GPIO wählen oder bestehende Komponente entfernen",
            "3. Bei OneWire: Mehrere Sensoren können denselben Bus-Pin teilen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "NVS_WRITE_FAILED": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "NVS-Speicherung fehlgeschlagen",
        "message_user_de": "Die Konfiguration konnte nicht im ESP32-Speicher gespeichert werden (Speicher voll oder beschädigt)",
        "troubleshooting_de": [
            "1. ESP32 neu starten",
            "2. NVS-Speicher könnte voll sein - alte Konfigurationen löschen",
            "3. Bei wiederholtem Fehler: NVS komplett löschen und neu flashen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "TYPE_MISMATCH": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Typ-Konflikt",
        "message_user_de": "Ein Konfigurationsfeld hat den falschen Datentyp",
        "troubleshooting_de": [
            "1. Datentypen in Konfiguration prüfen",
            "2. GPIO-Nummern als Integer angeben",
            "3. Server-API-Dokumentation konsultieren",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "MISSING_FIELD": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Pflichtfeld fehlt",
        "message_user_de": "Ein erforderliches Konfigurationsfeld fehlt in den übermittelten Daten",
        "troubleshooting_de": [
            "1. Alle Pflichtfelder in der Konfiguration prüfen",
            "2. Für Sensoren: gpio, sensor_type sind erforderlich",
            "3. Für Aktoren: gpio, actuator_type sind erforderlich",
            "4. Server-Logs für fehlende Felder prüfen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "OUT_OF_RANGE": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Wert außerhalb des gültigen Bereichs",
        "message_user_de": "Ein Konfigurationswert liegt außerhalb des erlaubten Bereichs",
        "troubleshooting_de": [
            "1. GPIO-Nummer prüfen (0-39 für ESP32)",
            "2. PWM-Werte prüfen (0.0 - 1.0)",
            "3. Polling-Intervalle prüfen (min. 1000ms empfohlen)",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "UNKNOWN_ERROR": {
        "category": "CONFIG",
        "severity": "ERROR",
        "message_de": "Unbekannter Fehler",
        "message_user_de": "Ein unerwarteter Fehler ist auf dem ESP32 aufgetreten",
        "troubleshooting_de": [
            "1. ESP32-Serial-Logs für Details prüfen",
            "2. ESP32 neu starten",
            "3. Bei wiederholtem Fehler: Firmware-Bug melden",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "SENSOR_ARRAY_EMPTY": {
        "category": "CONFIG",
        "severity": "WARNING",
        "message_de": "Sensor-Konfiguration ist leer",
        "message_user_de": "Keine Sensoren in der Konfiguration vorhanden",
        "troubleshooting_de": [
            "1. Dies ist normal, wenn nur Aktoren konfiguriert werden sollen",
            "2. Falls Sensoren erwartet: Sensor-Konfiguration im Server prüfen",
        ],
        "recoverable": True,
        "user_action_required": False,
    },
    "ACTUATOR_ARRAY_EMPTY": {
        "category": "CONFIG",
        "severity": "WARNING",
        "message_de": "Aktor-Konfiguration ist leer",
        "message_user_de": "Keine Aktoren in der Konfiguration vorhanden",
        "troubleshooting_de": [
            "1. Dies ist normal, wenn nur Sensoren konfiguriert werden sollen",
            "2. Falls Aktoren erwartet: Aktor-Konfiguration im Server prüfen",
        ],
        "recoverable": True,
        "user_action_required": False,
    },
}


# ============================================
# ACTUATOR ALERT TYPES (String-based, from ESP32)
# ============================================

# Actuator Alert Types mit deutschen Übersetzungen
# Verwendet von actuator_alert_handler.py
ESP32_ACTUATOR_ALERT_MESSAGES_DE: Dict[str, Dict[str, Any]] = {
    "emergency_stop": {
        "category": "SAFETY",
        "severity": "CRITICAL",
        "message_de": "Notfall-Stopp ausgelöst",
        "message_user_de": "Aktor wurde durch Notfall-Stopp deaktiviert",
        "troubleshooting_de": [
            "1. Prüfen was den Notfall-Stopp ausgelöst hat",
            "2. Physische Anlage auf Probleme untersuchen",
            "3. Nach Behebung: Notfall-Stopp im Dashboard zurücksetzen",
            "4. Aktor kann erst nach Reset wieder aktiviert werden",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "runtime_protection": {
        "category": "SAFETY",
        "severity": "WARNING",
        "message_de": "Laufzeitschutz aktiviert",
        "message_user_de": "Aktor wurde automatisch abgeschaltet (maximale Laufzeit überschritten)",
        "troubleshooting_de": [
            "1. Dies ist ein Sicherheitsfeature - kein Fehler",
            "2. Aktor kann nach Abkühlung wieder aktiviert werden",
            "3. Falls häufig: Maximale Laufzeit in Konfiguration erhöhen",
            "4. Bei Pumpen: Prüfen ob Durchfluss blockiert ist",
        ],
        "recoverable": True,
        "user_action_required": False,
    },
    "safety_violation": {
        "category": "SAFETY",
        "severity": "CRITICAL",
        "message_de": "Sicherheitsverletzung erkannt",
        "message_user_de": "Aktor wurde aufgrund einer Sicherheitsverletzung deaktiviert",
        "troubleshooting_de": [
            "1. SOFORT physische Anlage prüfen",
            "2. Alle beteiligten Sensoren auf korrekte Werte prüfen",
            "3. Ursache der Sicherheitsverletzung identifizieren",
            "4. Aktor kann erst nach Behebung wieder aktiviert werden",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "hardware_error": {
        "category": "HARDWARE",
        "severity": "ERROR",
        "message_de": "Hardware-Fehler am Aktor",
        "message_user_de": "Der Aktor meldet einen Hardware-Fehler",
        "troubleshooting_de": [
            "1. Verkabelung des Aktors prüfen",
            "2. Stromversorgung des Aktors prüfen",
            "3. Relay/MOSFET-Treiber auf Beschädigung prüfen",
            "4. GPIO-Pin auf korrekte Funktion testen",
        ],
        "recoverable": True,
        "user_action_required": True,
    },
    "unknown": {
        "category": "SYSTEM",
        "severity": "WARNING",
        "message_de": "Unbekannter Alert",
        "message_user_de": "Ein unbekannter Alert wurde vom Aktor gemeldet",
        "troubleshooting_de": [
            "1. ESP32-Logs für Details prüfen",
            "2. Aktor-Status im Dashboard prüfen",
            "3. Bei wiederholtem Alert: Firmware-Version prüfen",
        ],
        "recoverable": True,
        "user_action_required": False,
    },
}


# ============================================
# COMBINED ERROR DICTIONARY
# ============================================

# Alle Error-Dictionaries in einem kombiniert
ALL_ESP32_ERROR_MESSAGES: Dict[int, Dict[str, Any]] = {
    # HARDWARE (1000-1999)
    **ESP32_GPIO_ERROR_MESSAGES,
    **ESP32_I2C_ERROR_MESSAGES,
    **ESP32_ONEWIRE_ERROR_MESSAGES,
    **ESP32_PWM_ERROR_MESSAGES,
    **ESP32_SENSOR_ERROR_MESSAGES,
    **ESP32_DS18B20_ERROR_MESSAGES,
    **ESP32_ACTUATOR_ERROR_MESSAGES,
    # SERVICE (2000-2999)
    **ESP32_NVS_ERROR_MESSAGES,
    **ESP32_CONFIG_ERROR_MESSAGES,
    **ESP32_LOGGER_ERROR_MESSAGES,
    **ESP32_STORAGE_ERROR_MESSAGES,
    **ESP32_SUBZONE_ERROR_MESSAGES,
    # COMMUNICATION (3000-3999)
    **ESP32_WIFI_ERROR_MESSAGES,
    **ESP32_MQTT_ERROR_MESSAGES,
    **ESP32_HTTP_ERROR_MESSAGES,
    **ESP32_NETWORK_ERROR_MESSAGES,
    # APPLICATION (4000-4999)
    **ESP32_STATE_ERROR_MESSAGES,
    **ESP32_OPERATION_ERROR_MESSAGES,
    **ESP32_COMMAND_ERROR_MESSAGES,
    **ESP32_PAYLOAD_ERROR_MESSAGES,
    **ESP32_MEMORY_ERROR_MESSAGES,
    **ESP32_SYSTEM_ERROR_MESSAGES,
    **ESP32_TASK_ERROR_MESSAGES,
    **ESP32_WATCHDOG_ERROR_MESSAGES,
    **ESP32_DISCOVERY_ERROR_MESSAGES,
}


# ============================================
# API FUNCTIONS
# ============================================


def get_error_info(error_code: int, language: str = "de") -> Optional[Dict[str, Any]]:
    """
    Get error information for ESP32 error code.

    IMPORTANT: This function is for ENRICHMENT only!
    - Server TRUSTS ESP32 error codes completely
    - Return None for unknown codes (caller handles gracefully)
    - System MUST NOT break on unknown error codes

    Args:
        error_code: ESP32 error code (1000-4999)
        language: Language code (de, en) - currently only German supported

    Returns:
        Error info dict with keys:
        - category: Error category (HARDWARE, SERVICE, COMMUNICATION, APPLICATION, CONFIG)
        - severity: Severity level (CRITICAL, ERROR, WARNING, INFO)
        - message: User-friendly message
        - troubleshooting: List of troubleshooting steps
        - docs_link: Link to documentation
        - recoverable: Whether error is potentially recoverable
        - user_action_required: Whether user needs to take action

        Returns None if error code is unknown (caller should handle gracefully)
    """
    if error_code not in ALL_ESP32_ERROR_MESSAGES:
        return None

    info = ALL_ESP32_ERROR_MESSAGES[error_code].copy()

    # Language-specific fields
    if language == "de":
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]
    else:
        # Fallback to German if English not available (can be extended later)
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]

    return info


def get_error_category(error_code: int) -> str:
    """
    Get error category from error code range.

    Args:
        error_code: ESP32 error code

    Returns:
        Category string: HARDWARE, SERVICE, COMMUNICATION, APPLICATION, or UNKNOWN
    """
    if 1000 <= error_code < 2000:
        return "HARDWARE"
    elif 2000 <= error_code < 3000:
        return "SERVICE"
    elif 3000 <= error_code < 4000:
        return "COMMUNICATION"
    elif 4000 <= error_code < 5000:
        return "APPLICATION"
    return "UNKNOWN"


def get_error_severity(error_code: int) -> str:
    """
    Get error severity from mapping or derive from category.

    Args:
        error_code: ESP32 error code

    Returns:
        Severity string: CRITICAL, ERROR, WARNING, INFO, or UNKNOWN
    """
    if error_code in ALL_ESP32_ERROR_MESSAGES:
        return ALL_ESP32_ERROR_MESSAGES[error_code].get("severity", "ERROR")
    return "UNKNOWN"


def get_all_error_codes() -> Dict[int, str]:
    """
    Get all error codes with short descriptions.

    Useful for API documentation and frontend error code lists.

    Returns:
        Dict mapping error_code to short German description
    """
    return {code: info["message_de"] for code, info in ALL_ESP32_ERROR_MESSAGES.items()}


def get_error_codes_by_category(category: str) -> Dict[int, str]:
    """
    Get error codes filtered by category.

    Args:
        category: HARDWARE, SERVICE, COMMUNICATION, APPLICATION, or CONFIG

    Returns:
        Dict mapping error_code to short German description
    """
    return {
        code: info["message_de"]
        for code, info in ALL_ESP32_ERROR_MESSAGES.items()
        if info.get("category") == category
    }


def is_recoverable_error(error_code: int) -> bool:
    """
    Check if error is potentially recoverable.

    Args:
        error_code: Error code to check

    Returns:
        True if error is recoverable, False if not, None if unknown
    """
    if error_code in ALL_ESP32_ERROR_MESSAGES:
        return ALL_ESP32_ERROR_MESSAGES[error_code].get("recoverable", True)
    return True  # Default: assume recoverable for unknown codes


def requires_user_action(error_code: int) -> bool:
    """
    Check if error requires user action.

    Args:
        error_code: Error code to check

    Returns:
        True if user action required, False if not
    """
    if error_code in ALL_ESP32_ERROR_MESSAGES:
        return ALL_ESP32_ERROR_MESSAGES[error_code].get("user_action_required", False)
    return False  # Default: no user action for unknown codes


# Legacy compatibility
def get_all_ds18b20_error_codes() -> Dict[int, str]:
    """
    Get all DS18B20 error codes with short descriptions.
    Legacy function for backwards compatibility.

    Returns:
        Dict mapping error_code to short German description
    """
    return {code: info["message_de"] for code, info in ESP32_ONEWIRE_ERROR_MESSAGES.items()}


def is_ds18b20_error_code(error_code: int) -> bool:
    """
    Check if error code is a DS18B20/OneWire error.
    Legacy function for backwards compatibility.

    Args:
        error_code: Error code to check

    Returns:
        True if code is in OneWire range (1020-1029)
    """
    return error_code in ESP32_ONEWIRE_ERROR_MESSAGES


def get_config_error_info(error_code: str, language: str = "de") -> Optional[Dict[str, Any]]:
    """
    Get error information for ESP32 config error codes (string-based).

    Used by config_handler.py to translate config_response errors to German.

    Args:
        error_code: ESP32 config error code string (e.g., "MISSING_FIELD", "GPIO_CONFLICT")
        language: Language code (de, en) - currently only German supported

    Returns:
        Error info dict with keys:
        - category: Error category (CONFIG)
        - severity: Severity level (ERROR, WARNING, INFO)
        - message: User-friendly message (German)
        - troubleshooting: List of troubleshooting steps (German)
        - recoverable: Whether error is potentially recoverable
        - user_action_required: Whether user needs to take action

        Returns None if error code is unknown (caller should handle gracefully)
    """
    if error_code not in ESP32_CONFIG_ERROR_MESSAGES_DE:
        return None

    info = ESP32_CONFIG_ERROR_MESSAGES_DE[error_code].copy()

    # Language-specific fields
    if language == "de":
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]
    else:
        # Fallback to German if English not available
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]

    return info


def get_config_error_description(error_code: str, language: str = "de") -> str:
    """
    Get short German description for ESP32 config error code.

    Convenience function for simple use cases.

    Args:
        error_code: ESP32 config error code string
        language: Language code (currently only "de" supported)

    Returns:
        German error description or fallback string for unknown codes
    """
    if error_code in ESP32_CONFIG_ERROR_MESSAGES_DE:
        return ESP32_CONFIG_ERROR_MESSAGES_DE[error_code]["message_de"]
    return f"Unbekannter Konfigurationsfehler: {error_code}"


def get_actuator_alert_info(alert_type: str, language: str = "de") -> Optional[Dict[str, Any]]:
    """
    Get alert information for ESP32 actuator alert types.

    Used by actuator_alert_handler.py to translate alerts to German.

    Args:
        alert_type: Actuator alert type string (e.g., "emergency_stop", "runtime_protection")
        language: Language code (de, en) - currently only German supported

    Returns:
        Alert info dict with keys:
        - category: Alert category (SAFETY, HARDWARE, SYSTEM)
        - severity: Severity level (CRITICAL, ERROR, WARNING)
        - message: User-friendly message (German)
        - troubleshooting: List of troubleshooting steps (German)
        - recoverable: Whether error is potentially recoverable
        - user_action_required: Whether user needs to take action

        Returns fallback info for unknown alert types
    """
    # Normalisiere alert_type (lowercase)
    alert_type_normalized = alert_type.lower() if alert_type else "unknown"

    if alert_type_normalized not in ESP32_ACTUATOR_ALERT_MESSAGES_DE:
        alert_type_normalized = "unknown"

    info = ESP32_ACTUATOR_ALERT_MESSAGES_DE[alert_type_normalized].copy()

    # Language-specific fields
    if language == "de":
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]
    else:
        # Fallback to German
        info["message"] = info["message_user_de"]
        info["troubleshooting"] = info["troubleshooting_de"]

    return info
