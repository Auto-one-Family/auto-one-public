"""
Google Sheets integration package.

S1 (AUT-443): Service-Account authentication bootstrap.
S2+ (AUT-442 follow-ups): Export pipeline, scheduler, tab rotation.

Public surface (S1):
- load_service_account_credentials: returns a google.oauth2 SA Credentials object
- validate_credentials_config: startup-time configuration validator
- SheetsAuthError: dedicated configuration exception
"""

from .auth import (
    SheetsAuthError,
    load_service_account_credentials,
    validate_credentials_config,
)

__all__ = [
    "SheetsAuthError",
    "load_service_account_credentials",
    "validate_credentials_config",
]
