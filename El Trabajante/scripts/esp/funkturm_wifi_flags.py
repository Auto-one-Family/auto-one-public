# PlatformIO pre-script: compile-time WiFi/MQTT for one-shot Funkturm flash (esp32_funkturm).
# Secrets only via environment — never committed.
#
# Required: FUNKTURM_WIFI_PASSWORD
# Optional: FUNKTURM_WIFI_SSID (default Funkturm), FUNKTURM_MQTT_HOST (default 192.168.178.60),
#           FUNKTURM_MQTT_PORT (default 1883)
#
# Example:
#   export FUNKTURM_WIFI_PASSWORD='...'
#   pio run -e esp32_funkturm -t upload --upload-port /dev/ttyUSB0

import os

Import("env")


def _c_string_macro_value(s: str) -> str:
    """Value for -DNAME=... so C++ sees a string literal token."""
    esc = []
    for c in s:
        if c == "\\":
            esc.append("\\\\")
        elif c == '"':
            esc.append('\\"')
        else:
            esc.append(c)
    return '\\"' + "".join(esc) + '\\"'


def _append_string_macro(name: str, value: str) -> None:
    env.Append(BUILD_FLAGS=[f"-D{name}={_c_string_macro_value(value)}"])


ssid = os.environ.get("FUNKTURM_WIFI_SSID", "Funkturm")
password = os.environ.get("FUNKTURM_WIFI_PASSWORD")
if not password:
    print(
        "\n[funkturm_wifi_flags] FEHLER: Umgebungsvariable FUNKTURM_WIFI_PASSWORD ist nicht gesetzt.\n"
        "  Beispiel:  export FUNKTURM_WIFI_PASSWORD='...'\n"
        "  Optional:  FUNKTURM_WIFI_SSID, FUNKTURM_MQTT_HOST, FUNKTURM_MQTT_PORT\n"
    )
    env.Exit(1)

host = os.environ.get("FUNKTURM_MQTT_HOST", "192.168.178.60")
port = os.environ.get("FUNKTURM_MQTT_PORT", "1883")
if not port.isdigit() or not (1 <= int(port) <= 65535):
    print(f"\n[funkturm_wifi_flags] FEHLER: FUNKTURM_MQTT_PORT ungueltig: {port!r}\n")
    env.Exit(1)

env.Append(BUILD_FLAGS=["-DFUNKTURM_COMPILE_WIFI=1"])
_append_string_macro("FUNKTURM_WIFI_SSID", ssid)
_append_string_macro("FUNKTURM_WIFI_PASSWORD", password)
_append_string_macro("FUNKTURM_MQTT_HOST", host)
env.Append(BUILD_FLAGS=[f"-DFUNKTURM_MQTT_PORT={int(port)}"])
