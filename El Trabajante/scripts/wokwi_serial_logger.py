#!/usr/bin/env python3
"""
Wokwi Serial Logger für AutomationOne
Streamt Serial-Output in eine Log-Datei für Claude-Zugriff

Voraussetzung: Wokwi-Simulation muss in VS Code laufen

Verwendung:
  1. VS Code: F1 → "Wokwi: Start Simulator"
  2. Terminal: python scripts/wokwi_serial_logger.py
  3. Claude: "Analysiere El Trabajante/logs/wokwi_serial.log"

Konfiguration:
  - RFC2217 Port: 4000 (definiert in wokwi.toml)
  - Baudrate: 115200 (definiert in wokwi.toml)
  - Log-Datei: logs/wokwi_serial.log
"""

import serial
import datetime
import sys
import json
import re
from pathlib import Path

# Konfiguration
RFC2217_PORT = 4000
BAUDRATE = 115200
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
LOG_DIR = PROJECT_DIR / "logs"
LOG_FILE = LOG_DIR / "wokwi_serial.log"
DEBUG_LOG_FILE = PROJECT_DIR / ".cursor" / "debug.log"


def parse_debug_line(line):
    """Parse [DEBUG] JSON line and return JSON object or None"""
    if not line.startswith('[DEBUG]'):
        return None
    try:
        json_str = line[8:]  # Remove '[DEBUG]' prefix
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return None

def write_debug_log(debug_obj):
    """Write NDJSON entry to debug.log"""
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(debug_obj) + '\n')
            f.flush()
    except Exception as e:
        print(f"Warning: Failed to write to debug.log: {e}")

def main():
    # Log-Verzeichnisse erstellen
    LOG_DIR.mkdir(exist_ok=True)
    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"╔═══════════════════════════════════════════════╗")
    print(f"║  Wokwi Serial Logger für AutomationOne        ║")
    print(f"╠═══════════════════════════════════════════════╣")
    print(f"║  Port: localhost:{RFC2217_PORT}                        ║")
    print(f"║  Log:  logs/wokwi_serial.log                  ║")
    print(f"║  Debug: .cursor/debug.log                      ║")
    print(f"║  Stop: Ctrl+C                                 ║")
    print(f"╚═══════════════════════════════════════════════╝")
    print()

    print(f"Verbinde zu Wokwi Serial...")

    try:
        ser = serial.serial_for_url(
            f'rfc2217://localhost:{RFC2217_PORT}',
            baudrate=BAUDRATE,
            timeout=1
        )
    except Exception as e:
        print(f"Verbindungsfehler: {e}")
        print()
        print("   Moegliche Ursachen:")
        print("   1. Wokwi-Simulation nicht gestartet")
        print("      -> VS Code: F1 -> 'Wokwi: Start Simulator'")
        print("   2. rfc2217ServerPort nicht in wokwi.toml")
        print("      -> Zeile hinzufuegen: rfc2217ServerPort = 4000")
        print("   3. Wokwi-Tab nicht sichtbar (Simulation pausiert)")
        print("      -> Tab in VS Code sichtbar halten")
        sys.exit(1)

    print(f"Verbunden!")
    print(f"Schreibe nach: {LOG_FILE}")
    print(f"Debug-Logs nach: {DEBUG_LOG_FILE}")
    print()

    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            header = f"=== Wokwi Serial Log - {datetime.datetime.now().isoformat()} ===\n"
            f.write(header)
            f.flush()
            print(header.strip())

            while True:
                try:
                    line = ser.readline()
                    if line:
                        decoded = line.decode('utf-8', errors='ignore').rstrip()
                        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        log_line = f"[{timestamp}] {decoded}"

                        # Console + Datei
                        print(log_line)
                        f.write(log_line + '\n')
                        f.flush()
                        
                        # Check for [DEBUG] lines and write to debug.log
                        if '[DEBUG]' in decoded:
                            debug_obj = parse_debug_line(decoded)
                            if debug_obj:
                                # Add timestamp if not present
                                if 'timestamp' not in debug_obj or debug_obj['timestamp'] == 0:
                                    debug_obj['timestamp'] = int(datetime.datetime.now().timestamp() * 1000)
                                write_debug_log(debug_obj)

                except serial.SerialException as e:
                    print(f"\nSerial-Verbindung unterbrochen: {e}")
                    break

    except KeyboardInterrupt:
        print("\n")
        print("Logger beendet")
    finally:
        ser.close()
        print(f"Log gespeichert: {LOG_FILE}")
        print(f"Debug-Log gespeichert: {DEBUG_LOG_FILE}")


if __name__ == '__main__':
    main()
