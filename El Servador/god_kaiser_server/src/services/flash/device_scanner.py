"""
USB Device Scanner for ESP32 Flash Workflow — AUT-765

Scans connected USB serial ports and classifies ESP32 boards via VID/PID lookup.
Handles platform detection: works natively on Windows and on Linux (Pi) when
docker device-binds are configured; returns degraded-mode signal for Docker
on Windows without USB passthrough.
"""

import os
import platform
import sys
from pathlib import Path

from serial.tools import list_ports

from ...core.logging_config import get_logger
from ...schemas.flash import UsbDevice

logger = get_logger(__name__)

# --- Runtime host detection (no magic strings) ---

HOST_NATIVE_WINDOWS = "native-windows"
HOST_NATIVE_MACOS = "native-macos"
HOST_DOCKER_DESKTOP = "docker-desktop"
HOST_LINUX = "linux-host"

# Kernel-release markers that identify a Linux container running under
# Docker Desktop (Windows/Mac). WSL2 backend → "microsoft"/"wsl";
# legacy Hyper-V/Mac backend → "linuxkit".
_DOCKER_DESKTOP_KERNEL_MARKERS = ("microsoft", "wsl", "linuxkit")

# --- USB VID/PID constants (no magic numbers) ---

_VID_CH340 = 0x1A86
_PID_CH340 = 0x7523  # CH340 USB-UART — most common ESP32 WROOM-32 dev board
_PID_CH9102 = 0x55D4  # CH9102 USB-UART — newer boards (NodeMCU-32, Lolin D32)
# TODO AUT-766: FT232RL (VID 0x0403 PID 0x6001) — FTDI, used in some older ESP32 devboards

_VID_SILABS = 0x10C4
_PID_CP2102 = 0xEA60  # CP2102 USB-UART — Silabs variant for ESP32 WROOM-32

_VID_ESPRESSIF = 0x303A
_PID_ESP32S3_BUILTIN_USB = 0x1001  # ESP32-S3 built-in USB (Seeed XIAO ESP32-S3)
_PID_ESP32S3_JTAG = 0x0002  # ESP32-S3 JTAG/OTA (DevKitC-1)
_PID_ESP32C3_CDC_JTAG = 0x4001  # ESP32-C3 USB Serial/JTAG (built-in CDC)

# (chip_family, board_type) lookup keyed by (vid, pid)
_USB_CHIP_MAP: dict[tuple[int, int], tuple[str, str]] = {
    (_VID_CH340, _PID_CH340): ("ESP32", "WROOM-32"),
    (_VID_CH340, _PID_CH9102): ("ESP32", "WROOM-32-CH9102"),
    (_VID_SILABS, _PID_CP2102): ("ESP32", "WROOM-32-CP"),
    (_VID_ESPRESSIF, _PID_ESP32S3_BUILTIN_USB): ("ESP32-S3", "S3-XIAO"),
    (_VID_ESPRESSIF, _PID_ESP32S3_JTAG): ("ESP32-S3", "S3-DevKit"),
    (_VID_ESPRESSIF, _PID_ESP32C3_CDC_JTAG): ("ESP32-C3", "C3-DevKit"),
}


def is_usb_scanning_supported() -> bool:
    """
    Detect if USB serial scanning is supported in the current runtime.

    Windows native (sys.platform == "win32"):
        Always supported — pyserial sees COM ports directly.

    macOS (sys.platform == "darwin"):
        Always supported — pyserial sees /dev/cu.* ports directly.

    Linux + USB_SCANNING_AVAILABLE=true env var:
        Explicit override (e.g. usbipd-win WSL2 passthrough configured).

    Linux + USB_SCANNING_AVAILABLE=false env var:
        Explicit degraded-mode (override auto-detection).

    Linux, no env override, serial devices present (/dev/ttyUSB* or /dev/ttyACM*):
        Supported — Pi with docker-compose device-bind configured.

    Linux, no env override, no serial devices:
        Degraded — Docker on Windows without USB passthrough.
        Note: WSL2 without usbipd-win also falls into this case.
    """
    if sys.platform in ("win32", "darwin"):
        return True

    env_override = os.environ.get("USB_SCANNING_AVAILABLE", "").strip().lower()
    if env_override == "true":
        return True
    if env_override == "false":
        return False

    dev = Path("/dev")
    return bool(list(dev.glob("ttyUSB*")) or list(dev.glob("ttyACM*")))


def detect_runtime_host() -> str:
    """
    Best-effort detection of the host the server actually runs on.

    Used to pick the correct degraded-mode guidance: a Linux Docker container
    reports ``sys.platform == "linux"`` regardless of whether the Docker host
    is a Raspberry Pi (where ``docker restart`` re-binds the serial device) or
    Windows/macOS via Docker Desktop (where USB passthrough needs usbipd-win or
    running the server natively).

    Returns one of:
        HOST_NATIVE_WINDOWS — server runs directly on Windows (pyserial sees COM ports).
        HOST_NATIVE_MACOS   — server runs directly on macOS.
        HOST_DOCKER_DESKTOP — Linux container under Docker Desktop / WSL2 (Windows/Mac host).
        HOST_LINUX          — Linux container/process on a real Linux host (e.g. Raspberry Pi).
    """
    if sys.platform == "win32":
        return HOST_NATIVE_WINDOWS
    if sys.platform == "darwin":
        return HOST_NATIVE_MACOS

    release = platform.uname().release.lower()
    if any(marker in release for marker in _DOCKER_DESKTOP_KERNEL_MARKERS):
        return HOST_DOCKER_DESKTOP
    return HOST_LINUX


def scan_usb_devices() -> list[UsbDevice]:
    """
    Scan all USB serial ports and classify ESP32 boards via VID/PID lookup.

    Unknown VID/PID combinations are included in the result with
    chip_family="unknown" — they are not silently filtered.

    Returns:
        List of UsbDevice instances for every detected serial port.

    Raises:
        RuntimeError: If the underlying pyserial scan fails.
    """
    logger.debug("Starting USB serial port scan")
    try:
        ports = list_ports.comports()
    except Exception as exc:
        logger.error("USB port scan failed: %s", exc, exc_info=True)
        raise RuntimeError(f"USB port scan failed: {exc}") from exc

    devices: list[UsbDevice] = []
    for port in ports:
        vid = port.vid if port.vid is not None else 0
        pid = port.pid if port.pid is not None else 0
        chip_family, board_type = _USB_CHIP_MAP.get((vid, pid), ("unknown", "unknown"))
        devices.append(
            UsbDevice(
                port=port.device,
                description=port.description or "",
                hwid=port.hwid or "",
                chip_family=chip_family,
                board_type=board_type,
                vid=vid,
                pid=pid,
            )
        )
        logger.debug(
            "Port %s: vid=0x%04X pid=0x%04X → chip=%s board=%s",
            port.device,
            vid,
            pid,
            chip_family,
            board_type,
        )

    logger.info("USB scan complete: %d device(s) found", len(devices))
    return devices
