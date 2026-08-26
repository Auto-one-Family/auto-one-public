"""
Unit tests for src.integrations.sheets.auth (AUT-443 / S1).

Covers:
- disabled-by-default behaviour (validate is no-op)
- happy path with a valid Service-Account JSON file
- missing path / relative path / non-existent file
- malformed JSON / wrong type / missing required SA fields
- lazy import of google-auth (load_service_account_credentials)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest

from src.core.config import SheetsExportSettings
from src.core.error_codes import ConfigErrorCode
from src.integrations.sheets.auth import (
    SheetsAuthError,
    load_service_account_credentials,
    validate_credentials_config,
)


_RSA_PRIVATE_KEY_PEM_CACHE: str | None = None


def _generate_test_rsa_pem() -> str:
    """
    Generate an ephemeral RSA private key in PEM format for tests that need
    a key parseable by google-auth. Cached per process to keep tests fast.
    Falls back to a syntactic placeholder when `cryptography` is absent.
    """
    global _RSA_PRIVATE_KEY_PEM_CACHE
    if _RSA_PRIVATE_KEY_PEM_CACHE is not None:
        return _RSA_PRIVATE_KEY_PEM_CACHE

    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
    except ImportError:
        _RSA_PRIVATE_KEY_PEM_CACHE = (
            "-----BEGIN PRIVATE KEY-----\nFAKE\n-----END PRIVATE KEY-----\n"
        )
        return _RSA_PRIVATE_KEY_PEM_CACHE

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _RSA_PRIVATE_KEY_PEM_CACHE = pem_bytes.decode("utf-8")
    return _RSA_PRIVATE_KEY_PEM_CACHE


def _sa_payload(**overrides: Any) -> Dict[str, Any]:
    """Build a minimal valid Service-Account JSON payload for tests."""
    payload: Dict[str, Any] = {
        "type": "service_account",
        "project_id": "autoone-sheets-test",
        "private_key_id": "deadbeef",
        "private_key": _generate_test_rsa_pem(),
        "client_email": "autoone-sheets-test@autoone-sheets-test.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    payload.update(overrides)
    return payload


def _settings(
    enabled: bool = True,
    sa_path: str | None = None,
    spreadsheet_id: str | None = None,
) -> SheetsExportSettings:
    return SheetsExportSettings(
        SHEETS_EXPORT_ENABLED=enabled,
        SHEETS_SA_CREDENTIALS_PATH=sa_path,
        SHEETS_SPREADSHEET_ID=spreadsheet_id,
    )


def test_validate_disabled_returns_none() -> None:
    """When SHEETS_EXPORT_ENABLED=false the validator is a clean no-op."""
    settings = _settings(enabled=False, sa_path=None)
    assert validate_credentials_config(settings) is None


def test_validate_enabled_without_path_raises(tmp_path: Path) -> None:
    settings = _settings(enabled=True, sa_path=None)
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED


def test_validate_relative_path_raises(tmp_path: Path) -> None:
    settings = _settings(enabled=True, sa_path="relative/path/sa.json")
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_NOT_FOUND


def test_validate_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    settings = _settings(enabled=True, sa_path=str(missing))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_NOT_FOUND


def test_validate_directory_instead_of_file_raises(tmp_path: Path) -> None:
    settings = _settings(enabled=True, sa_path=str(tmp_path))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID


def test_validate_malformed_json_raises(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text("{not valid json", encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID


def test_validate_wrong_type_raises(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID


def test_validate_missing_required_fields_raises(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps({"type": "service_account"}), encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID
    assert "missing_fields" in exc.value.details


def test_validate_wrong_type_field_raises(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(_sa_payload(type="user_account")), encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))
    with pytest.raises(SheetsAuthError) as exc:
        validate_credentials_config(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_CREDENTIALS_FILE_INVALID


def test_validate_happy_path_returns_metadata(tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(_sa_payload()), encoding="utf-8")
    if os.name == "posix":
        os.chmod(sa, 0o600)

    settings = _settings(enabled=True, sa_path=str(sa), spreadsheet_id="abc123")
    metadata = validate_credentials_config(settings)
    assert metadata is not None
    assert metadata["project_id"] == "autoone-sheets-test"
    assert metadata["client_email"].endswith("iam.gserviceaccount.com")
    assert metadata["spreadsheet_id_configured"] is True
    assert metadata["credentials_path"] == str(sa)


def test_validate_warns_on_world_readable_permissions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    if os.name != "posix":
        pytest.skip("Permission check is POSIX only")
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(_sa_payload()), encoding="utf-8")
    os.chmod(sa, 0o644)
    settings = _settings(enabled=True, sa_path=str(sa))

    with caplog.at_level("WARNING"):
        metadata = validate_credentials_config(settings)
    assert metadata is not None
    assert any("readable by group/others" in rec.message for rec in caplog.records)


def test_load_credentials_disabled_raises() -> None:
    settings = _settings(enabled=False)
    with pytest.raises(SheetsAuthError) as exc:
        load_service_account_credentials(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_AUTH_NOT_CONFIGURED


def test_load_credentials_happy_path_with_google_auth(tmp_path: Path) -> None:
    try:
        from google.oauth2 import service_account  # noqa: F401
    except ImportError:
        pytest.skip("google-auth not installed in this environment")

    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(_sa_payload()), encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))

    creds = load_service_account_credentials(settings)
    assert creds is not None
    assert getattr(creds, "service_account_email", "").endswith("iam.gserviceaccount.com")


def test_load_credentials_missing_google_auth(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text(json.dumps(_sa_payload()), encoding="utf-8")
    settings = _settings(enabled=True, sa_path=str(sa))

    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any):
        if name == "google.oauth2" or name.startswith("google.oauth2"):
            raise ImportError("simulated missing google-auth")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(SheetsAuthError) as exc:
        load_service_account_credentials(settings)
    assert exc.value.numeric_code == ConfigErrorCode.SHEETS_DEPENDENCY_MISSING
