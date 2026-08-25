# PlatformIO pre-script: compile-time WiFi/MQTT for one-shot flash (esp32_oneshot).
# Secrets only via environment — never committed.
#
# Required: ONESHOT_WIFI_PASSWORD
# Optional: ONESHOT_WIFI_SSID (default PLACEHOLDER_WIFI_SSID),
#           ONESHOT_MQTT_HOST (default 192.0.2.10),
#           ONESHOT_MQTT_PORT (default 1883)
#
# Example:
#   export ONESHOT_WIFI_PASSWORD='...'
#   pio run -e esp32_oneshot -t upload --upload-port /dev/ttyUSB0

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


ssid = os.environ.get("ONESHOT_WIFI_SSID", "PLACEHOLDER_WIFI_SSID")
password = os.environ.get("ONESHOT_WIFI_PASSWORD")
if not password:
    print(
        "\n[oneshot_wifi_flags] FEHLER: Umgebungsvariable ONESHOT_WIFI_PASSWORD ist nicht gesetzt.\n"
        "  Beispiel:  export ONESHOT_WIFI_PASSWORD='...'\n"
        "  Optional:  ONESHOT_WIFI_SSID, ONESHOT_MQTT_HOST, ONESHOT_MQTT_PORT\n"
    )
    env.Exit(1)

host = os.environ.get("ONESHOT_MQTT_HOST", "192.0.2.10")
port = os.environ.get("ONESHOT_MQTT_PORT", "1883")
if not port.isdigit() or not (1 <= int(port) <= 65535):
    print(f"\n[oneshot_wifi_flags] FEHLER: ONESHOT_MQTT_PORT ungueltig: {port!r}\n")
    env.Exit(1)

env.Append(BUILD_FLAGS=["-DONESHOT_COMPILE_WIFI=1"])
_append_string_macro("ONESHOT_WIFI_SSID", ssid)
_append_string_macro("ONESHOT_WIFI_PASSWORD", password)
_append_string_macro("ONESHOT_MQTT_HOST", host)
env.Append(BUILD_FLAGS=[f"-DONESHOT_MQTT_PORT={int(port)}"])
