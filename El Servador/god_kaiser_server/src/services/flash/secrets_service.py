"""
NVS Secrets Service for Flash Workflow — AUT-766/AUT-768

Reads, writes, and builds NVS credential CSVs for the ESP32 flash workflow.
Flash execution (esptool) is also here — same file, same secrets-dir convention.
Secrets are stored at FLASH_SECRETS_DIR (env var, default /app/flash_secrets).

Credential flow: server CSV → nvs_partition_gen → .bin → esptool
"""

import csv
import os
import subprocess
import sys
from pathlib import Path

from ...core.logging_config import get_logger
from ...schemas.flash import NvsSecretsResponse, NvsSecretsCreate, SecretsBuildResponse

logger = get_logger(__name__)

# --- Constants ---
_SECRETS_DIR_ENV = "FLASH_SECRETS_DIR"
_DEFAULT_SECRETS_DIR = Path("/app/flash_secrets")
_NVS_SIZE = hex(0x8000)  # 32KB — matches partitions_custom.csv NVS partition size
_NVS_ADDR = "0x9000"  # NVS partition start — from El Trabajante/partitions_custom.csv
_NVS_NAMESPACE = "wifi_config"
_CSV_HEADER = ["key", "type", "encoding", "value"]
_PASSWORD_MASK = "***"
_FLASH_BAUD = "460800"

_FIRMWARE_BUILDS_DIR_ENV = "FIRMWARE_BUILDS_DIR"
_DEFAULT_FIRMWARE_BUILDS_DIR = Path("/app/firmware_builds")

# chip_family → esptool --chip arg + binary offsets (A4/A5 verified)
_ESPTOOL_CHIP_ARG: dict[str, str] = {
    "ESP32": "esp32",
    "ESP32-S3": "esp32s3",
    "ESP32-C3": "esp32c3",
}
_CHIP_OFFSETS: dict[str, dict[str, str]] = {
    "ESP32":    {"bootloader": "0x1000", "partitions": "0x8000", "app": "0x20000"},
    "ESP32-S3": {"bootloader": "0x0",    "partitions": "0x8000", "app": "0x10000"},
    "ESP32-C3": {"bootloader": "0x0",    "partitions": "0x8000", "app": "0x20000"},
}


def get_secrets_dir() -> Path:
    """Return the secrets directory from FLASH_SECRETS_DIR env var or default."""
    env_val = os.environ.get(_SECRETS_DIR_ENV, "").strip()
    if env_val:
        return Path(env_val)
    return _DEFAULT_SECRETS_DIR


def get_firmware_builds_dir() -> Path:
    """Return the firmware builds directory from FIRMWARE_BUILDS_DIR env var or default."""
    env_val = os.environ.get(_FIRMWARE_BUILDS_DIR_ENV, "").strip()
    return Path(env_val) if env_val else _DEFAULT_FIRMWARE_BUILDS_DIR


def _get_firmware_paths(board: str) -> dict[str, Path]:
    """Return {bootloader, partitions, firmware} bin paths for board."""
    base = get_firmware_builds_dir() / board
    return {
        "bootloader": base / "bootloader.bin",
        "partitions": base / "partitions.bin",
        "firmware": base / "firmware.bin",
    }


def _validate_firmware_artifacts(board: str) -> dict[str, Path]:
    """Verify all three .bin files exist. Raises FileNotFoundError if not."""
    paths = _get_firmware_paths(board)
    missing = [name for name, p in paths.items() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Firmware artifacts missing for board='{board}': {missing}. "
            f"Run 'pio run -e {board}' on host and copy binaries to firmware_builds/{board}/."
        )
    return paths


def _csv_path(secrets_dir: Path, env: str) -> Path:
    return secrets_dir / f"nvs_secrets.{env}.csv"


def _bin_path(secrets_dir: Path, env: str) -> Path:
    return secrets_dir / f"nvs_secrets.{env}.bin"


def read_secrets(env: str) -> NvsSecretsResponse:
    """
    Read NVS credential CSV for env and return structured response.

    Passwords are always masked as '***' in the response.

    Raises:
        FileNotFoundError: If CSV does not exist for the given env.
    """
    secrets_dir = get_secrets_dir()
    path = _csv_path(secrets_dir, env)

    if not path.exists():
        raise FileNotFoundError(f"NVS secrets CSV not found: {path}")

    values: dict[str, str] = {}
    with path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = row.get("key", "")
            val = row.get("value", "")
            row_type = row.get("type", "")
            if row_type == "data" and key:
                values[key] = val

    logger.debug("Read NVS secrets for env=%s keys=%s", env, list(values.keys()))

    return NvsSecretsResponse(
        env=env,
        ssid=values.get("ssid", ""),
        password=_PASSWORD_MASK,
        server_address=values.get("server_address", ""),
        mqtt_port=int(values.get("mqtt_port", 1883)),
        mqtt_username=values.get("mqtt_username", ""),
        mqtt_password=_PASSWORD_MASK,
        configured=int(values.get("configured", 0)),
    )


def _read_csv_values(path: Path) -> dict[str, str]:
    """Return {key: value} for all data rows in an existing CSV."""
    values: dict[str, str] = {}
    with path.open("r", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = row.get("key", "")
            val = row.get("value", "")
            if row.get("type", "") == "data" and key:
                values[key] = val
    return values


def write_secrets(env: str, secrets: NvsSecretsCreate) -> Path:
    """
    Write NVS credential CSV for env.

    Creates the secrets directory if it does not exist.
    Overwrites any existing CSV for the same env.

    password / mqtt_password may be None to signal "keep existing value".
    If None and no CSV exists yet, raises ValueError (caller maps to HTTP 422).

    Returns:
        Path of the written CSV file.
    """
    secrets_dir = get_secrets_dir()
    secrets_dir.mkdir(parents=True, exist_ok=True)
    path = _csv_path(secrets_dir, env)

    # Resolve optional passwords — None means "keep existing"
    wifi_password = secrets.password
    mqtt_password = secrets.mqtt_password

    if wifi_password is None or mqtt_password is None:
        if not path.exists():
            missing = [
                name
                for name, val in (("password", wifi_password), ("mqtt_password", mqtt_password))
                if val is None
            ]
            raise ValueError(
                f"Cannot keep existing {'/'.join(missing)}: "
                f"no CSV exists yet for env '{env}'. "
                "Supply the password(s) explicitly on the first write."
            )
        existing = _read_csv_values(path)
        if wifi_password is None:
            wifi_password = existing.get("password", "")
        if mqtt_password is None:
            mqtt_password = existing.get("mqtt_password", "")

    rows = [
        _CSV_HEADER,
        [_NVS_NAMESPACE, "namespace", "", ""],
        ["ssid", "data", "string", secrets.ssid],
        ["password", "data", "string", wifi_password],
        ["server_address", "data", "string", secrets.server_address],
        ["mqtt_port", "data", "u16", str(secrets.mqtt_port)],
        ["mqtt_username", "data", "string", secrets.mqtt_username],
        ["mqtt_password", "data", "string", mqtt_password],
        ["configured", "data", "u8", str(secrets.configured)],
    ]

    with path.open("w", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerows(rows)

    logger.info("Wrote NVS secrets CSV: env=%s path=%s", env, path)
    return path


def build_nvs_binary(env: str) -> SecretsBuildResponse:
    """
    Generate NVS partition binary via nvs_partition_gen.

    The CSV must exist (run write_secrets first).
    Uses the same subprocess invocation as flash_nvs.py.

    Returns:
        SecretsBuildResponse with binary_path and size_bytes.

    Raises:
        FileNotFoundError: If CSV does not exist for the given env.
        RuntimeError: If nvs_partition_gen fails.
    """
    secrets_dir = get_secrets_dir()
    csv_p = _csv_path(secrets_dir, env)
    bin_p = _bin_path(secrets_dir, env)

    if not csv_p.exists():
        raise FileNotFoundError(
            f"NVS secrets CSV not found for env '{env}' — run PUT /flash/secrets/{env} first"
        )

    cmd = [
        sys.executable,
        "-m",
        "esp_idf_nvs_partition_gen.nvs_partition_gen",
        "generate",
        str(csv_p),
        str(bin_p),
        _NVS_SIZE,
    ]

    logger.info("Building NVS binary: env=%s", env)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(
            "nvs_partition_gen failed: env=%s returncode=%d stderr=%s stdout=%s",
            env,
            result.returncode,
            result.stderr,
            result.stdout,
        )
        raise RuntimeError(
            f"nvs_partition_gen failed (exit {result.returncode}): "
            f"{result.stderr or result.stdout}"
        )

    size_bytes = bin_p.stat().st_size
    logger.info(
        "NVS binary ready: env=%s path=%s size_bytes=%d", env, bin_p, size_bytes
    )

    return SecretsBuildResponse(
        env=env,
        binary_path=str(bin_p),
        size_bytes=size_bytes,
    )


def flash_nvs_partition(env: str, port: str) -> str:
    """
    Flash NVS partition binary to an ESP32 via esptool.

    Reads the pre-built .bin from FLASH_SECRETS_DIR (run build_nvs_binary first).
    Blocks until the flash completes — caller must run this in a thread executor
    to avoid blocking the async event loop.

    Port exclusivity: esptool holds the serial port for the duration of the flash.
    No other process (serial monitor, etc.) may open the same port while flashing.

    Returns:
        Combined stdout+stderr output from esptool.

    Raises:
        FileNotFoundError: NVS binary does not exist — run POST /flash/secrets/{env}/build first.
        RuntimeError: esptool exited with non-zero code.
    """
    secrets_dir = get_secrets_dir()
    bin_p = _bin_path(secrets_dir, env)

    if not bin_p.exists():
        raise FileNotFoundError(
            f"NVS binary not found for env '{env}' — "
            f"run POST /api/v1/flash/secrets/{env}/build first"
        )

    cmd = [
        sys.executable,
        "-m",
        "esptool",
        "--port", port,
        "--baud", _FLASH_BAUD,
        "--after", "hard_reset",
        "write-flash",
        _NVS_ADDR,
        str(bin_p),
    ]

    logger.info("Flashing NVS partition: env=%s port=%s addr=%s", env, port, _NVS_ADDR)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"esptool timed out after 120s on port {port}")

    output = (result.stdout + result.stderr).strip()

    if result.returncode != 0:
        logger.error(
            "esptool flash failed: env=%s port=%s returncode=%d output=%s",
            env,
            port,
            result.returncode,
            output,
        )
        raise RuntimeError(
            f"esptool failed (exit {result.returncode}): {output}"
        )

    logger.info("Flash complete: env=%s port=%s", env, port)
    return output


# =============================================================================
# WP2 — Port Exclusivity (AUT-854)
# =============================================================================


def _release_port_holder(port: str) -> None:
    """Kill any host-side process holding the serial port (e.g. pio device monitor).

    Uses fuser to find and SIGTERM the holder. No-op if fuser unavailable or port is free.
    Container-side processes never hold the port persistently — only host-side monitors do.
    """
    import time

    try:
        result = subprocess.run(["fuser", port], capture_output=True, text=True)
        pids = result.stdout.strip().split()
        if not pids:
            return
        for pid in pids:
            try:
                subprocess.run(["kill", pid], capture_output=True, check=False)
                logger.info("Released port holder: port=%s pid=%s", port, pid)
            except Exception as exc:
                logger.warning("Failed to kill port holder pid=%s: %s", pid, exc)
        time.sleep(1.5)
    except FileNotFoundError:
        pass  # fuser not installed — skip silently (container lacks fuser by default)


# =============================================================================
# WP1 — firmware + full Flash modes (AUT-854)
# =============================================================================


def flash_firmware(port: str, env: str, chip_family: str, board: str) -> str:
    """Flash bootloader + partitions + firmware + NVS without erasing.

    Mirrors flash_nvs_partition — same subprocess/executor/error pattern.
    Does NOT erase first — existing data outside written regions is preserved.

    Args:
        port: Serial port, e.g. /dev/ttyUSB0
        env: NVS env name (pi-home, dev-local, pi-elbherb)
        chip_family: From device_scanner, e.g. "ESP32", "ESP32-S3"
        board: firmware_builds subdirectory name, e.g. "esp32_dev"

    Returns:
        Combined esptool stdout+stderr.

    Raises:
        FileNotFoundError: Firmware artifacts missing or NVS binary not found.
        ValueError: Unsupported chip_family.
        RuntimeError: esptool exited non-zero or timed out.
    """
    paths = _validate_firmware_artifacts(board)
    chip_arg = _ESPTOOL_CHIP_ARG.get(chip_family)
    offsets = _CHIP_OFFSETS.get(chip_family)
    if chip_arg is None or offsets is None:
        raise ValueError(
            f"Unsupported chip_family='{chip_family}' — supported: {list(_CHIP_OFFSETS)}"
        )
    secrets_dir = get_secrets_dir()
    bin_p = _bin_path(secrets_dir, env)
    if not bin_p.exists():
        raise FileNotFoundError(
            f"NVS binary not found for env='{env}' — run POST /flash/secrets/{env}/build first"
        )

    _release_port_holder(port)

    cmd = [
        sys.executable, "-m", "esptool",
        "--chip", chip_arg,
        "--port", port,
        "--baud", _FLASH_BAUD,
        "--after", "hard-reset",
        "write-flash",
        "--flash-size", "detect",
        offsets["bootloader"], str(paths["bootloader"]),
        offsets["partitions"], str(paths["partitions"]),
        offsets["app"],        str(paths["firmware"]),
        _NVS_ADDR,             str(bin_p),
    ]

    logger.info(
        "Flashing firmware+nvs: env=%s port=%s chip=%s board=%s", env, port, chip_family, board
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"esptool timed out after 180s on port {port}")

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        logger.error(
            "esptool firmware-flash failed: env=%s port=%s returncode=%d output=%s",
            env, port, result.returncode, output,
        )
        raise RuntimeError(f"esptool failed (exit {result.returncode}): {output}")

    logger.info("Firmware+NVS flash complete: env=%s port=%s", env, port)
    return output


def flash_full(port: str, env: str, chip_family: str, board: str) -> str:
    """Erase entire flash then write bootloader + partitions + firmware + NVS.

    DESTRUCTIVE — wipes all existing data including OTA state, stored WiFi, logs.
    Only call after erase_confirm=True has been validated by the API layer.

    Args / Returns / Raises: same as flash_firmware.
    """
    paths = _validate_firmware_artifacts(board)
    chip_arg = _ESPTOOL_CHIP_ARG.get(chip_family)
    offsets = _CHIP_OFFSETS.get(chip_family)
    if chip_arg is None or offsets is None:
        raise ValueError(
            f"Unsupported chip_family='{chip_family}' — supported: {list(_CHIP_OFFSETS)}"
        )
    secrets_dir = get_secrets_dir()
    bin_p = _bin_path(secrets_dir, env)
    if not bin_p.exists():
        raise FileNotFoundError(
            f"NVS binary not found for env='{env}' — run POST /flash/secrets/{env}/build first"
        )

    _release_port_holder(port)

    cmd = [
        sys.executable, "-m", "esptool",
        "--chip", chip_arg,
        "--port", port,
        "--baud", _FLASH_BAUD,
        "--after", "hard-reset",
        "write-flash",
        "--erase-all",
        "--flash-size", "detect",
        offsets["bootloader"], str(paths["bootloader"]),
        offsets["partitions"], str(paths["partitions"]),
        offsets["app"],        str(paths["firmware"]),
        _NVS_ADDR,             str(bin_p),
    ]

    logger.info(
        "Full-flash (erase+fw+nvs): env=%s port=%s chip=%s board=%s", env, port, chip_family, board
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"esptool timed out after 240s on port {port}")

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        logger.error(
            "esptool full-flash failed: env=%s port=%s returncode=%d output=%s",
            env, port, result.returncode, output,
        )
        raise RuntimeError(f"esptool failed (exit {result.returncode}): {output}")

    logger.info("Full-flash complete: env=%s port=%s", env, port)
    return output
