"""
Unit Tests: SubzoneAssignRequest Schema Validation

Tests that validate_subzone_id_format() enforces the documented format:
- ASCII letters, numbers, and underscores only
- Max 32 characters (NVS compatibility)
- Normalized to lowercase on return

Related: src/schemas/subzone.py
"""

import pytest
from pydantic import ValidationError

from src.schemas.subzone import SubzoneAssignRequest

# =============================================================================
# Helpers
# =============================================================================

_VALID_BASE = {
    "subzone_id": "test_subzone",
    "assigned_gpios": [4, 5],
}


def make_request(**kwargs) -> SubzoneAssignRequest:
    """Build a SubzoneAssignRequest with minimal valid defaults."""
    return SubzoneAssignRequest(**{**_VALID_BASE, **kwargs})


# =============================================================================
# Test: subzone_id format validation
# =============================================================================


class TestSubzoneIdFormat:
    """Tests for subzone_id field validation in SubzoneAssignRequest."""

    def test_lowercase_ascii_accepted(self):
        """Lowercase ASCII letters and numbers pass validation."""
        req = make_request(subzone_id="irrigation_section_a")
        assert req.subzone_id == "irrigation_section_a"

    def test_uppercase_ascii_accepted_and_lowercased(self):
        """Uppercase ASCII letters are accepted and normalized to lowercase."""
        req = make_request(subzone_id="IrrigationSectionA")
        assert req.subzone_id == "irrigationsectiona"

    def test_numbers_and_underscores_accepted(self):
        """Numbers and underscores are accepted."""
        req = make_request(subzone_id="zone_01_v2")
        assert req.subzone_id == "zone_01_v2"

    def test_umlaut_ae_rejected(self):
        """German umlaut 'ae' (ae) must be rejected — not valid ASCII alphanumeric."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="außen")

    def test_umlaut_oe_rejected(self):
        """German umlaut 'oe' must be rejected."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="grün")

    def test_umlaut_capital_rejected(self):
        """Uppercase umlaut (Ä, Ö, Ü) must be rejected."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="Äpfel")

    def test_sharp_s_rejected(self):
        """German sharp-s (ß) must be rejected."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="straße")

    def test_space_rejected(self):
        """Spaces must be rejected."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="invalid id")

    def test_hyphen_rejected(self):
        """Hyphens must be rejected (subzone_id only allows underscores)."""
        with pytest.raises(ValidationError, match="subzone_id"):
            make_request(subzone_id="invalid-id")

    def test_existing_ascii_slugs_pass(self):
        """Existing ASCII slugs like 'au_en' (transliterated umlauts) pass."""
        req = make_request(subzone_id="au_en")
        assert req.subzone_id == "au_en"

    def test_result_is_lowercase(self):
        """Validator always returns lowercase."""
        req = make_request(subzone_id="UPPER_CASE_123")
        assert req.subzone_id == "upper_case_123"
