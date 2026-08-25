#!/usr/bin/env python3
"""Flash complete ESP32 image: bootloader + partitions + firmware + NVS credentials.

Flash addresses (esp32_dev / partitions_custom.csv):
    bootloader.bin  0x1000   framework-arduinoespressif32/tools/platformio-build.py:211
    partitions.bin  0x8000   framework-arduinoespressif32/tools/platformio-build.py:214
    firmware.bin    0x20000  platformio.ini [env:esp32_dev] board_upload.offset_address
    nvs_secrets.bin 0x9000   partitions_custom.csv nvs partition

Flash settings (esp32dev.json board defaults, no env:esp32_dev override):
    --flash_mode dio   (build.flash_mode)
    --flash_freq 40m   (build.f_flash = 40000000L)
    --flash_size 4MB

Usage:
    python scripts/esp/flash_full.py --env dev-local --port COM5
    python scripts/esp/flash_full.py --env dev-local --generate-only
    python scripts/esp/flash_full.py --env dev-local --port /dev/ttyUSB0 --erase

Prerequisites:
    pio run -e esp32_dev          # build firmware binaries first
    pip install esp-idf-nvs-partition-gen
"""

import argparse
import glob
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "secrets"))
BUILD_DIR = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", ".pio", "build", "esp32_dev"))
ESPTOOL_PY = os.path.normpath(os.path.join(
    os.path.expanduser("~"), ".platformio", "packages", "tool-esptoolpy", "esptool.py"
))

NVS_ADDR = "0x9000"
NVS_SIZE = hex(0x8000)
BOOTLOADER_ADDR = "0x1000"
PARTITIONS_ADDR = "0x8000"
FIRMWARE_ADDR = "0x20000"

FLASH_MODE = "dio"
FLASH_FREQ = "40m"
FLASH_SIZE = "4MB"
BAUD = "460800"

VALID_ENVS = ("dev-local", "lab", "field")

REQUIRED_BINARIES: tuple[tuple[str, str], ...] = (
    ("bootloader.bin", BOOTLOADER_ADDR),
    ("partitions.bin", PARTITIONS_ADDR),
    ("firmware.bin", FIRMWARE_ADDR),
)


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


def _check_firmware_binaries(force: bool = False) -> list[tuple[str, str]]:
    missing = []
    found = []
    for name, addr in REQUIRED_BINARIES:
        path = os.path.join(BUILD_DIR, name)
        if not os.path.isfile(path):
            missing.append(name)
        else:
            found.append((path, addr))
    if missing:
        raise FileNotFoundError(
            f"Missing firmware binaries in {BUILD_DIR}:\n"
            + "\n".join(f"  {m}" for m in missing)
            + "\n\nBuild first:  pio run -e esp32_dev"
        )
    firmware_bin = os.path.join(BUILD_DIR, "firmware.bin")
    src_root = os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "src"))
    config_files = [
        os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "platformio.ini")),
        os.path.normpath(os.path.join(_SCRIPT_DIR, "..", "..", "partitions_custom.csv")),
    ]
    src_files = (
        glob.glob(os.path.join(src_root, "**", "*.cpp"), recursive=True)
        + glob.glob(os.path.join(src_root, "**", "*.h"), recursive=True)
    )
    watch_files = [f for f in src_files + config_files if os.path.isfile(f)]
    if watch_files and not force:
        newest_src = max(os.path.getmtime(f) for f in watch_files)
        bin_mtime = os.path.getmtime(firmware_bin)
        if newest_src > bin_mtime:
            raise FileNotFoundError(
                "firmware.bin is older than source files — "
                "run 'pio run -e esp32_dev' first, or use --force to flash the existing binary."
            )
    return found


def _flash_full(
    firmware_pairs: list[tuple[str, str]],
    nvs_bin_path: str,
    port: str,
    erase: bool,
) -> None:
    if not os.path.isfile(ESPTOOL_PY):
        raise FileNotFoundError(
            f"esptool.py not found: {ESPTOOL_PY}\n"
            "Ensure PlatformIO is installed."
        )
    cmd = [
        sys.executable, ESPTOOL_PY,
        "--chip", "esp32",
        "--port", port,
        "--baud", BAUD,
        "write_flash",
        "--flash_mode", FLASH_MODE,
        "--flash_freq", FLASH_FREQ,
        "--flash_size", FLASH_SIZE,
    ]
    if erase:
        cmd.append("--erase-all")
    for path, addr in firmware_pairs:
        cmd += [addr, path]
    cmd += [NVS_ADDR, nvs_bin_path]
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
    parser.add_argument("--generate-only", action="store_true", help="Generate NVS binary only, skip flash")
    parser.add_argument("--erase", action="store_true", help="Erase all flash before writing (esptool --erase-all)")
    parser.add_argument("--force", action="store_true", help="Flash even if firmware.bin is older than source files")
    args = parser.parse_args()

    csv_path = os.path.join(SECRETS_DIR, f"nvs_secrets.{args.env}.csv")
    bin_path = os.path.join(SECRETS_DIR, f"nvs_secrets.{args.env}.bin")

    if not os.path.isfile(csv_path):
        print(f"ERROR: credential file not found: {csv_path}", file=sys.stderr)
        print(f"  Copy:  cp {os.path.basename(csv_path)}.example {os.path.basename(csv_path)}", file=sys.stderr)
        print("  Then fill in PLACEHOLDER values with actual credentials.", file=sys.stderr)
        return 1

    print(f"[flash_full] env={args.env}")
    print(f"  Generating NVS binary: {bin_path}")
    _generate_nvs_binary(csv_path, bin_path)
    print(f"  NVS binary ready: {bin_path} (addr={NVS_ADDR}, size={NVS_SIZE})")

    if args.generate_only:
        print(f"  Flash with:  python {__file__} --env {args.env} --port <PORT>")
        return 0

    if not args.port:
        print("ERROR: --port required unless --generate-only", file=sys.stderr)
        return 1

    try:
        firmware_pairs = _check_firmware_binaries(force=args.force)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.env == "field":
        print("  Strict env — confirmation required before flashing.")
        print(f"  NVS binary: {bin_path}")
        flash_pairs = " ".join(f"{addr} {os.path.basename(path)}" for path, addr in firmware_pairs)
        nvs_part = f"{NVS_ADDR} {os.path.basename(bin_path)}"
        erase_flag = " --erase-all" if args.erase else ""
        print(
            f"  Command: python esptool.py --chip esp32 --port {args.port} --baud {BAUD} "
            f"write_flash --flash_mode {FLASH_MODE} --flash_freq {FLASH_FREQ} "
            f"--flash_size {FLASH_SIZE}{erase_flag} {flash_pairs} {nvs_part}"
        )
        return 0

    erase_note = " (--erase-all)" if args.erase else ""
    print(f"  Flashing full image to {args.port}{erase_note} ...")
    _flash_full(firmware_pairs, bin_path, args.port, args.erase)
    print(f"[flash_full] Done — full ESP32 flash complete ({args.env})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
