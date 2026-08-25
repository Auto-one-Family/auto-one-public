"""Camera REST API — AUT-572 Welle 1 (Snapshot-Service).

GET /api/v1/camera/status    — capability signal + health from camera service
GET /api/v1/camera/snapshot  — proxy latest JPEG from camera service

Both endpoints require a valid user session (JWT, any role).
When CAMERA_ENABLED is false or the camera service is unreachable, the endpoints
respond with structured errors — no stack-trace logging for expected offline states.
"""

import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Response

from ...api.deps import ActiveUser
from ...core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/camera", tags=["camera"])

_CAMERA_SERVICE_URL: str = os.environ.get("CAMERA_SERVICE_URL", "http://automationone-camera:8080")
_PROXY_TIMEOUT: float = 5.0


def _camera_enabled() -> bool:
    return os.environ.get("CAMERA_ENABLED", "false").strip().lower() == "true"


@router.get(
    "/status",
    summary="Camera capability and health",
    description=(
        "Returns whether the camera feature is enabled (CAMERA_ENABLED env flag) "
        "and, if enabled, the current health from the camera service. "
        "Always returns HTTP 200 — the `enabled` and `available` fields convey state."
    ),
)
async def get_camera_status(current_user: ActiveUser) -> dict[str, Any]:
    if not _camera_enabled():
        return {"enabled": False, "available": False}

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            resp = await client.get(f"{_CAMERA_SERVICE_URL}/health")
            data: dict[str, Any] = resp.json()
            return {"enabled": True, "available": data.get("status") == "ok", **data}
    except Exception as exc:
        logger.warning("Camera service unreachable: %s", exc)
        return {"enabled": True, "available": False, "error": "Camera service unreachable"}


@router.get(
    "/snapshot",
    summary="Latest camera snapshot (JPEG)",
    description=(
        "Proxies the latest JPEG frame from the camera service. "
        "Returns 404 when CAMERA_ENABLED is false, 503 when the camera service "
        "is unavailable or the camera itself is not ready."
    ),
    responses={
        200: {"content": {"image/jpeg": {}}},
        404: {"description": "Camera feature not enabled"},
        503: {"description": "Camera service unavailable"},
    },
)
async def get_camera_snapshot(current_user: ActiveUser) -> Response:
    if not _camera_enabled():
        raise HTTPException(status_code=404, detail="Camera feature not enabled")

    try:
        async with httpx.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
            resp = await client.get(f"{_CAMERA_SERVICE_URL}/latest.jpg")
            if resp.status_code == 503:
                raise HTTPException(status_code=503, detail="Camera not ready")
            return Response(
                content=resp.content,
                media_type="image/jpeg",
                headers={"Cache-Control": "no-store"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Camera snapshot proxy failed: %s", exc)
        raise HTTPException(status_code=503, detail="Camera service unavailable")
