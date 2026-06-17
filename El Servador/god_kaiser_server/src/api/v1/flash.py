"""
Flash Workflow REST API — AUT-765/AUT-766/AUT-768

GET  /api/v1/flash/devices             — detect connected ESP32 USB boards
GET  /api/v1/flash/secrets/{env}       — read NVS credential secrets (passwords masked)
PUT  /api/v1/flash/secrets/{env}       — write/overwrite NVS credential secrets
POST /api/v1/flash/secrets/{env}/build — generate NVS partition binary
POST /api/v1/flash/execute             — flash NVS binary to ESP32 via esptool (synchronous)

All endpoints require Operator role (JWT).
"""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException

from ...api.deps import OperatorUser
from ...core.error_codes import FlashDeviceError
from ...core.logging_config import get_logger
from ...schemas.flash import (
    DeviceListResponse,
    FlashEnvResponse,
    FlashExecuteRequest,
    FlashExecuteResponse,
    NvsEnv,
    NvsSecretsCreate,
    NvsSecretsResponse,
    SecretsBuildResponse,
    SecretsWriteResponse,
)
from ...services.flash.device_scanner import is_usb_scanning_supported, scan_usb_devices

# board_type from device_scanner → firmware_builds subdirectory name
_BOARD_DIR_MAP: dict[str, str] = {
    "WROOM-32": "esp32_dev",
    "WROOM-32-CH9102": "esp32_dev",
    "WROOM-32-CP": "esp32_dev",
}
from ...services.flash.secrets_service import (
    build_nvs_binary,
    flash_firmware,
    flash_full,
    flash_nvs_partition,
    read_secrets,
    write_secrets,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/flash", tags=["flash"])

_SCANNER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="usb-scanner")
_NVS_BUILD_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nvs-builder")
_FLASH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nvs-flasher")
_FIRMWARE_FLASH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fw-flasher")


@router.get(
    "/env",
    response_model=FlashEnvResponse,
    summary="Get current flash environment",
    description=(
        "Returns the flash environment name this server instance is configured for. "
        "Set via FLASH_ENV_NAME env var (default: dev-local). "
        "Used by the frontend to address the correct secrets CSV without hardcoding."
    ),
)
async def get_flash_env(current_user: OperatorUser) -> FlashEnvResponse:
    return FlashEnvResponse(env=os.getenv("FLASH_ENV_NAME", "dev-local"))


@router.get(
    "/devices",
    response_model=DeviceListResponse,
    summary="List connected ESP32 USB serial devices",
    description=(
        "Scans USB serial ports and classifies ESP32 boards via VID/PID. "
        "Returns 503 with error code 3101 when USB scanning is not available "
        "(Docker on Windows without passthrough). "
        "Unknown devices are listed with chip_family='unknown'."
    ),
)
async def list_flash_devices(current_user: OperatorUser) -> DeviceListResponse:
    if not is_usb_scanning_supported():
        if sys.platform == "linux":
            platform_note = "linux-no-serial-device"
            detail_msg = (
                "Kein USB-Gerät erkannt. Mögliche Ursachen: "
                "ESP32 nicht angeschlossen, oder Container wurde vor dem Anschließen gestartet. "
                "ESP32 anschließen und Container neu starten: "
                "docker restart automationone-server"
            )
        else:
            platform_note = "docker-windows-degraded"
            detail_msg = (
                "USB serial scanning is not available. "
                "Server is running in a Docker container on Windows without USB passthrough. "
                "To enable scanning: (1) configure usbipd-win and set "
                "USB_SCANNING_AVAILABLE=true, or (2) run the server natively on Windows "
                "(uvicorn outside Docker). "
                "On Raspberry Pi: add device-binds to docker-compose.override.yml."
            )
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": int(FlashDeviceError.PLATFORM_USB_UNAVAILABLE),
                "detail": detail_msg,
                "platform_note": platform_note,
            },
        )

    loop = asyncio.get_event_loop()
    try:
        devices = await loop.run_in_executor(_SCANNER_EXECUTOR, scan_usb_devices)
    except RuntimeError as exc:
        logger.error("USB device scan failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": int(FlashDeviceError.DEVICE_SCAN_FAILED),
                "detail": str(exc),
            },
        )

    return DeviceListResponse(
        devices=devices,
        scanning_available=True,
        count=len(devices),
    )


# =============================================================================
# NVS Secrets — AUT-766
# =============================================================================


@router.get(
    "/secrets/{env}",
    response_model=NvsSecretsResponse,
    summary="Read NVS credential secrets for env",
    description=(
        "Returns the current NVS credential CSV as structured JSON. "
        "Passwords are always masked as '***'. "
        "Returns 404 with error code 3102 if the CSV does not exist for the given env."
    ),
)
async def get_flash_secrets(
    env: NvsEnv,
    current_user: OperatorUser,
) -> NvsSecretsResponse:
    try:
        return read_secrets(env.value)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": int(FlashDeviceError.SECRETS_NOT_FOUND),
                "detail": (
                    f"NVS secrets CSV not found for env '{env.value}'. "
                    f"Run PUT /api/v1/flash/secrets/{env.value} to create it."
                ),
            },
        )


@router.put(
    "/secrets/{env}",
    response_model=SecretsWriteResponse,
    summary="Write NVS credential secrets for env",
    description=(
        "Writes or overwrites the NVS credential CSV for the given env. "
        "All required credential fields must be present. "
        "The file is written to the FLASH_SECRETS_DIR path (never committed to the repo)."
    ),
)
async def put_flash_secrets(
    env: NvsEnv,
    secrets: NvsSecretsCreate,
    current_user: OperatorUser,
) -> SecretsWriteResponse:
    loop = asyncio.get_event_loop()
    try:
        path = await loop.run_in_executor(
            _NVS_BUILD_EXECUTOR,
            lambda: write_secrets(env.value, secrets),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return SecretsWriteResponse(path=str(path))


@router.post(
    "/secrets/{env}/build",
    response_model=SecretsBuildResponse,
    summary="Generate NVS partition binary for env",
    description=(
        "Runs nvs_partition_gen to produce the .bin file from the existing credential CSV. "
        "Returns 422 with error code 3102 if the CSV does not exist (run PUT first). "
        "Returns 500 with error code 3103 if nvs_partition_gen fails. "
        "Does not flash — flash support comes in Stufe 5."
    ),
)
async def build_flash_secrets(
    env: NvsEnv,
    current_user: OperatorUser,
) -> SecretsBuildResponse:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(
            _NVS_BUILD_EXECUTOR,
            lambda: build_nvs_binary(env.value),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": int(FlashDeviceError.SECRETS_NOT_FOUND),
                "detail": (
                    f"NVS secrets CSV not found for env '{env.value}'. "
                    f"Run PUT /api/v1/flash/secrets/{env.value} first."
                ),
            },
        )
    except RuntimeError as exc:
        logger.error("NVS binary build failed for env=%s: %s", env.value, exc)
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": int(FlashDeviceError.BUILD_FAILED),
                "detail": str(exc),
            },
        )


# =============================================================================
# Flash Execute — AUT-768
# =============================================================================


@router.post(
    "/execute",
    response_model=FlashExecuteResponse,
    summary="Flash NVS partition binary to ESP32",
    description=(
        "Flashes the pre-built NVS binary to an ESP32 via esptool (synchronous). "
        "Run POST /flash/secrets/{env}/build first to generate the binary. "
        "Port exclusivity: no other process may hold the serial port during flash. "
        "Returns 400 if env=pi-elbherb and confirm is not True. "
        "Returns 422 with error code 3102 if the NVS binary does not exist. "
        "Returns 500 with error code 3105 if esptool fails."
    ),
)
async def execute_flash(
    request: FlashExecuteRequest,
    current_user: OperatorUser,
) -> FlashExecuteResponse:
    if request.env == NvsEnv.pi_elbherb and not request.confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": (
                    "confirm=true is required for env=pi-elbherb (STRICT production environment). "
                    "Set confirm=true in the request body to proceed."
                ),
            },
        )

    if request.flash_type == "full" and not request.erase_confirm:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": int(FlashDeviceError.ERASE_CONFIRM_REQUIRED),
                "detail": (
                    "erase_confirm=true is required for flash_type=full (destructive erase). "
                    "Silent erase is forbidden — set erase_confirm=true to confirm."
                ),
            },
        )

    loop = asyncio.get_event_loop()

    if request.flash_type == "nvs":
        try:
            output = await loop.run_in_executor(
                _FLASH_EXECUTOR,
                lambda: flash_nvs_partition(request.env.value, request.port),
            )
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": int(FlashDeviceError.SECRETS_NOT_FOUND),
                    "detail": str(exc),
                },
            )
        except RuntimeError as exc:
            logger.error(
                "Flash execute failed: env=%s port=%s flash_type=nvs: %s",
                request.env.value,
                request.port,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": int(FlashDeviceError.FLASH_EXECUTE_FAILED),
                    "detail": str(exc),
                },
            )
    else:
        # firmware or full — need chip_family from device scanner
        try:
            devices = await loop.run_in_executor(_SCANNER_EXECUTOR, scan_usb_devices)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": int(FlashDeviceError.DEVICE_SCAN_FAILED),
                    "detail": str(exc),
                },
            )

        device = next((d for d in devices if d.port == request.port), None)
        if device is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "detail": f"Port {request.port} not found — ESP connected and port correct?"
                },
            )
        if device.chip_family == "unknown":
            raise HTTPException(
                status_code=400,
                detail={
                    "detail": (
                        f"Unknown chip_family for {request.port} "
                        f"(vid={device.vid:#06x} pid={device.pid:#06x}). "
                        "Add VID/PID to device_scanner._USB_CHIP_MAP."
                    ),
                },
            )
        board_dir = _BOARD_DIR_MAP.get(device.board_type, device.board_type.lower().replace("-", "_"))

        flash_fn = flash_firmware if request.flash_type == "firmware" else flash_full
        executor = _FIRMWARE_FLASH_EXECUTOR

        try:
            output = await loop.run_in_executor(
                executor,
                lambda: flash_fn(request.port, request.env.value, device.chip_family, board_dir),
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": int(FlashDeviceError.FIRMWARE_NOT_FOUND),
                    "detail": str(exc),
                },
            )
        except RuntimeError as exc:
            logger.error(
                "Flash execute failed: env=%s port=%s flash_type=%s: %s",
                request.env.value,
                request.port,
                request.flash_type,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error_code": int(FlashDeviceError.FLASH_EXECUTE_FAILED),
                    "detail": str(exc),
                },
            )

    return FlashExecuteResponse(
        port=request.port,
        env=request.env.value,
        flash_type=request.flash_type,
        output=output,
    )
