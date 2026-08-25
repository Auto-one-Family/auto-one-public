#!/usr/bin/env python3
"""Camera Snapshot Service — AutomationOne AUT-572 Welle 1.

Captures JPEG frames from the Raspberry Pi Camera (IMX708) via libcamera/Picamera2
at a configurable interval and serves the latest frame via a minimal HTTP server.

Endpoints:
    GET /latest.jpg  — latest JPEG frame (503 if camera unavailable)
    GET /health      — JSON health/status (always 200)
"""
import io
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

CAMERA_SNAPSHOT_INTERVAL: int = int(os.environ.get("CAMERA_SNAPSHOT_INTERVAL", "5"))
LISTEN_PORT: int = int(os.environ.get("CAMERA_SERVICE_PORT", "8080"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_latest_frame: bytes | None = None
_last_capture_ts: str | None = None
_camera_model: str = "unknown"
_camera_error: str | None = None
_lock = threading.Lock()


def _capture_loop() -> None:
    global _latest_frame, _last_capture_ts, _camera_model, _camera_error

    retry_delay = 10
    while True:
        try:
            from picamera2 import Picamera2  # noqa: PLC0415

            if not Picamera2.global_camera_info():
                raise RuntimeError("No camera detected by libcamera")

            cam = Picamera2()
            props = cam.camera_properties
            model = props.get("Model", "unknown")
            logger.info("Camera '%s' detected, interval=%ds", model, CAMERA_SNAPSHOT_INTERVAL)

            with _lock:
                _camera_model = model
                _camera_error = None

            cfg = cam.create_still_configuration(main={"size": (1536, 864)})
            cam.configure(cfg)
            cam.start()

            while True:
                buf = io.BytesIO()
                cam.capture_file(buf, format="jpeg")
                frame = buf.getvalue()
                ts = datetime.now(timezone.utc).isoformat()
                with _lock:
                    _latest_frame = frame
                    _last_capture_ts = ts
                    _camera_error = None
                logger.debug("Captured %d bytes at %s", len(frame), ts)
                time.sleep(CAMERA_SNAPSHOT_INTERVAL)

        except Exception as exc:
            logger.error("Camera capture failed: %s — retry in %ds", exc, retry_delay, exc_info=True)
            with _lock:
                _camera_error = str(exc)
            time.sleep(retry_delay)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:  # suppress default access log
        pass

    def do_GET(self) -> None:
        if self.path == "/latest.jpg":
            self._serve_snapshot()
        elif self.path == "/health":
            self._serve_health()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_snapshot(self) -> None:
        with _lock:
            frame = _latest_frame
            error = _camera_error

        if error or frame is None:
            self.send_response(503)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            msg = (error or "No frame captured yet").encode()
            self.wfile.write(msg)
            return

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(frame)

    def _serve_health(self) -> None:
        with _lock:
            ts = _last_capture_ts
            model = _camera_model
            error = _camera_error

        status = "ok" if error is None and ts is not None else "error"
        body = json.dumps(
            {
                "status": status,
                "model": model,
                "last_capture": ts,
                "interval_seconds": CAMERA_SNAPSHOT_INTERVAL,
                "error": error,
            }
        ).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    capture_thread = threading.Thread(target=_capture_loop, daemon=True, name="capture")
    capture_thread.start()

    logger.info("Camera service listening on :%d", LISTEN_PORT)
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), _Handler)
    server.serve_forever()
