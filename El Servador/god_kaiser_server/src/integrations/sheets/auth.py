"""
Google Sheets Service-Account Authentication (AUT-442 / S1: AUT-443).

Provides:
- load_service_account_credentials(): returns ready-to-use
  google.oauth2.service_account.Credentials, lazily importing google-auth
  so the dependency stays optional until the export pipeline is enabled.
- validate_credentials_config(): startup-time configuration check that
  fails fast with a clear ConfigurationException when the feature is
  enabled but the configuration is incomplete or invalid.

Security:
- Service-Account JSON MUST live OUTSIDE the repository (e.g.
  /secrets/sheets_sa.json or a Docker secret mount).
- This module NEVER logs raw credentials, only paths and metadata
  (project_id, client_email) for diagnostics.
- File mode is validated on POSIX systems; group/other-readable
  credentials trigger a warning (not a hard fail to support shared
  container mounts that intentionally use 644).

Reference: docs/plans/BELEG-sheets-export-baseline-2026-05-23.md
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from ...core.config import SheetsExportSettings, get_settings
from ...core.error_codes import ConfigErrorCode
from ...core.exceptions import ConfigurationException
from ...core.logging_config import get_logger

if TYPE_CHECKING:
    from google.oauth2.service_account import Credentials

logger = get_logger(__name__)

REQUIRED_SA_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "token_uri",
)


class SheetsAuthError(ConfigurationException):
    """Raised when the Google Sheets Service-Account configuration is invalid."""

    def __init__(
        self,
        message: str,
        *,
        numeric_code: int = ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(config_key="sheets_export.sa_credentials_path", message=message)
        self.numeric_code = numeric_code
        if details:
            self.details.update(details)


def _settings() -> SheetsExportSettings:
    return get_settings().sheets_export


def _check_credentials_path(path_value: Optional[str]) -> Path:
    if not path_value:
        raise SheetsAuthError(
            "SHEETS_EXPORT_ENABLED=true but SHEETS_SA_CREDENTIALS_PATH is empty. "
            "Set the absolute path to the Service-Account JSON file "
            "(outside the repository).",
            numeric_code=ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED,
        )

    path = Path(path_value).expanduser()
    if not path.is_absolute():
        raise SheetsAuthError(
            "SHEETS_SA_CREDENTIALS_PATH must be an absolute path, "
            f"received: {path_value!r}.",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_NOT_FOUND,
            details={"path": str(path)},
        )

    if not path.exists():
        raise SheetsAuthError(
            f"Service-Account credentials file not found at: {path}. "
            "Provision the file via deployment secrets (do not commit it).",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_NOT_FOUND,
            details={"path": str(path)},
        )

    if not path.is_file():
        raise SheetsAuthError(
            f"SHEETS_SA_CREDENTIALS_PATH points to a non-regular file: {path}.",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID,
            details={"path": str(path)},
        )

    return path


def _warn_unsafe_permissions(path: Path) -> None:
    """Log a warning when SA-JSON is group/other-readable on POSIX."""
    if os.name != "posix":
        return
    try:
        mode = path.stat().st_mode
        readable_by_group_or_others = bool(mode & (stat.S_IRGRP | stat.S_IROTH))
        if readable_by_group_or_others:
            logger.warning(
                "Sheets SA credentials file %s is readable by group/others (mode=%o). "
                "Recommended permission: 0600. Continuing anyway.",
                path,
                stat.S_IMODE(mode),
            )
    except OSError as exc:
        logger.debug("Could not stat() SA credentials file %s: %s", path, exc)


def _load_and_validate_json(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SheetsAuthError(
            f"Service-Account JSON at {path} is not valid JSON: {exc.msg}",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID,
            details={"path": str(path), "json_error": exc.msg},
        ) from exc
    except OSError as exc:
        raise SheetsAuthError(
            f"Cannot read Service-Account JSON at {path}: {exc.strerror or exc!s}",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_NOT_FOUND,
            details={"path": str(path)},
        ) from exc

    if not isinstance(data, dict):
        raise SheetsAuthError(
            f"Service-Account JSON at {path} must be an object, "
            f"got {type(data).__name__}.",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID,
            details={"path": str(path)},
        )

    missing = [field for field in REQUIRED_SA_FIELDS if not data.get(field)]
    if missing:
        raise SheetsAuthError(
            "Service-Account JSON is missing required fields: "
            f"{', '.join(missing)} (path={path}).",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID,
            details={"path": str(path), "missing_fields": missing},
        )

    if data.get("type") != "service_account":
        raise SheetsAuthError(
            "Provided credentials file is not a service-account key "
            f"(type={data.get('type')!r}, path={path}).",
            numeric_code=ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID,
            details={"path": str(path), "type": data.get("type")},
        )

    return data


def validate_credentials_config(
    settings: Optional[SheetsExportSettings] = None,
) -> Optional[Dict[str, Any]]:
    """
    Validate the Sheets export configuration at server startup.

    - Returns None when the feature is disabled (no-op, server starts cleanly).
    - When enabled: verifies the SA JSON exists, is well-formed, and contains
      the required service_account fields. Returns the parsed (non-sensitive)
      metadata dict (project_id, client_email) on success.

    Never returns or logs the private_key.

    Raises:
        SheetsAuthError: When enabled but the configuration is invalid.
    """
    cfg = settings or _settings()

    if not cfg.enabled:
        logger.debug("Sheets export disabled (SHEETS_EXPORT_ENABLED=false), skipping validation.")
        return None

    path = _check_credentials_path(cfg.sa_credentials_path)
    _warn_unsafe_permissions(path)
    data = _load_and_validate_json(path)

    metadata = {
        "project_id": data.get("project_id"),
        "client_email": data.get("client_email"),
        "credentials_path": str(path),
        "spreadsheet_id_configured": bool(cfg.spreadsheet_id),
    }
    logger.info(
        "Sheets export auth configuration validated "
        "(project_id=%s, client_email=%s, spreadsheet_configured=%s)",
        metadata["project_id"],
        metadata["client_email"],
        metadata["spreadsheet_id_configured"],
    )
    return metadata


def load_service_account_credentials(
    settings: Optional[SheetsExportSettings] = None,
) -> "Credentials":
    """
    Build a google.oauth2 Service-Account Credentials object from the
    configured JSON file.

    Lazy-imports google-auth so the dependency is only required when the
    feature is actually used (S2+).

    Raises:
        SheetsAuthError: When the feature is disabled, the file is missing,
            invalid, or google-auth is not installed.
    """
    cfg = settings or _settings()

    if not cfg.enabled:
        raise SheetsAuthError(
            "SHEETS_EXPORT_ENABLED=false — cannot load Service-Account credentials.",
            numeric_code=ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED,
        )

    path = _check_credentials_path(cfg.sa_credentials_path)
    _warn_unsafe_permissions(path)
    _load_and_validate_json(path)

    try:
        from google.oauth2 import service_account
    except ImportError as exc:
        raise SheetsAuthError(
            "google-auth is not installed. Run `poetry install` to pull in the "
            "Sheets export dependencies before enabling SHEETS_EXPORT_ENABLED.",
            numeric_code=ConfigErrorCode.SHEETS_DEPENDENCY_MISSING,
            details={"missing_package": "google-auth"},
        ) from exc

    return service_account.Credentials.from_service_account_file(
        str(path),
        scopes=list(cfg.scopes),
    )
