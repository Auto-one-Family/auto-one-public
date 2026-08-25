#!/usr/bin/env python3
"""Generate and flash NVS partition binary with MQTT/WiFi credentials.

NVS partition: address=0x9000, size=0x8000 (32KB) — from partitions_custom.csv
Credential flow: NVS -> config_manager.cpp:236-237 -> WiFiConfig -> main.cpp:3293-3294

Usage:
    python scripts/esp/flash_nvs.py --env dev-local [--port COM5]
    python scripts/esp/flash_nvs.py --env dev-local --generate-only

Prerequisites:
    pip install esp-idf-nvs-partition-gen
"""

import argparse
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "secrets"))
ESPTOOL_PY = os.path.normpath(os.path.join(
    os.path.expanduser("~"), ".platformio", "packages", "tool-esptoolpy", "esptool.py"
))

NVS_ADDR = "0x9000"
NVS_SIZE = hex(0x8000)

VALID_ENVS = ("dev-local", "lab", "field")


def _generate_nvs_binary(csv_path: str, bin_path: str) -> None:
    cmd = [
        sys.executable, "-m", "esp_idf_nvs_partition_gen.nvs_partition_gen",
        "generate", csv_path, bin_path, NVS_SIZE,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"nvs_partition_gen failed:\n{result.stdout}\n{result.stderr}\n\n"
            "Install with:  pip install esp-idf-nvs-partition-gen"
        )


def _flash_nvs_binary(bin_path: str, port: str) -> None:
    if not os.path.isfile(ESPTOOL_PY):
        raise FileNotFoundError(
            f"esptool.py not found: {ESPTOOL_PY}\n"
            "Ensure PlatformIO is installed."
        )
    cmd = [
        sys.executable, ESPTOOL_PY,
        "--chip", "esp32",
        "--port", port,
        "--baud", "460800",
        "write_flash",
        NVS_ADDR, bin_path,
    ]
    print(f"  esptool: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"esptool.py failed (exit {result.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--env", required=True, choices=VALID_ENVS, help="Target environment")
    parser.add_argument("--port", default=None, help="Serial port (COM5, /dev/ttyUSB0, ...)")
    parser.add_argument("--generate-only", action="store_true", help="Generate binary only, skip flash")
    args = parser.parse_args()

    csv_path = os.path.join(SECRETS_DIR, f"nvs_secrets.{args.env}.csv")
    bin_path = os.path.join(SECRETS_DIR, f"nvs_secrets.{args.env}.bin")

    if not os.path.isfile(csv_path):
        print(f"ERROR: credential file not found: {csv_path}", file=sys.stderr)
        print(f"  Copy:  cp {os.path.basename(csv_path)}.example {os.path.basename(csv_path)}", file=sys.stderr)
        print("  Then fill in PLACEHOLDER values with actual credentials.", file=sys.stderr)
        return 1

    print(f"[flash_nvs] env={args.env}")
    print(f"  Generating: {bin_path}")
    _generate_nvs_binary(csv_path, bin_path)
    print(f"  Binary ready: {bin_path} (addr={NVS_ADDR}, size={NVS_SIZE})")

    if args.generate_only:
        print(f"  Flash with:  python {__file__} --env {args.env} --port <PORT>")
        return 0

    if not args.port:
        print("ERROR: --port required unless --generate-only", file=sys.stderr)
        return 1

    if args.env == "field":
        print("  Strict env — confirmation required before flashing.")
        print(f"  Binary: {bin_path}")
        print(f"  Command: python esptool.py --chip esp32 --port <PORT> write_flash {NVS_ADDR} {os.path.basename(bin_path)}")
        return 0

    print(f"  Flashing to {args.port} ...")
    _flash_nvs_binary(bin_path, args.port)
    print(f"[flash_nvs] Done — NVS flashed at {NVS_ADDR} ({args.env})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
