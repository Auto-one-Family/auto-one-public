#!/usr/bin/env python3
"""Persistent ESP32 serial logger for a field device.

Headless alternative to `pio device monitor` and `tio` when systemd runs without TTY.
Reconnects on USB replug; rotates log files by size.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import sys
import time

import serial
from serial.serialutil import SerialException

DEVICE = os.environ.get("ESP_SERIAL_DEVICE", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP_SERIAL_BAUD", "115200"))
LOG_FILE = os.environ.get(
    "ESP_SERIAL_LOG",
    "/var/log/autoone/esp-serial/esp_serial.log",
)
MAX_BYTES = int(os.environ.get("ESP_SERIAL_MAX_BYTES", str(200 * 1024 * 1024)))
KEEP_ROTATED = int(os.environ.get("ESP_SERIAL_KEEP_ROTATED", "7"))
RECONNECT_DELAY_S = float(os.environ.get("ESP_SERIAL_RECONNECT_DELAY_S", "2"))


def utc_ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def ensure_log_dir() -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def rotate_if_needed() -> None:
    try:
        size = os.path.getsize(LOG_FILE)
    except OSError:
        return
    if size < MAX_BYTES:
        return

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rotated = f"{LOG_FILE}.{stamp}"
    os.rename(LOG_FILE, rotated)

    rotated_files = sorted(glob.glob(f"{LOG_FILE}.*"), reverse=True)
    for old in rotated_files[KEEP_ROTATED:]:
        try:
            os.remove(old)
        except OSError:
            pass

    sys.stderr.write(f"[esp_serial_daemon] rotated log -> {rotated}\n")
    sys.stderr.flush()


def open_serial() -> serial.Serial:
    return serial.Serial(DEVICE, BAUD, timeout=1)


def write_line(out, raw: bytes) -> None:
    decoded = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    if not decoded:
        return
    out.write(f"[{utc_ts()}] {decoded}\n")
    out.flush()


def run_forever() -> None:
    ensure_log_dir()
    sys.stderr.write(
        f"[esp_serial_daemon] start device={DEVICE} baud={BAUD} log={LOG_FILE}\n"
    )
    sys.stderr.flush()

    while True:
        ser = None
        try:
            ser = open_serial()
            sys.stderr.write(f"[esp_serial_daemon] opened {DEVICE}\n")
            sys.stderr.flush()
            rotate_if_needed()
            with open(LOG_FILE, "a", encoding="utf-8") as out:
                while True:
                    line = ser.readline()
                    if line:
                        write_line(out, line)
                    rotate_if_needed()
        except (SerialException, OSError) as exc:
            sys.stderr.write(
                f"[esp_serial_daemon] serial error ({exc}); retry in {RECONNECT_DELAY_S}s\n"
            )
            sys.stderr.flush()
            time.sleep(RECONNECT_DELAY_S)
        finally:
            if ser is not None and ser.is_open:
                ser.close()


if __name__ == "__main__":
    run_forever()
