"""AUT-1350 — Ledger EC ×1000 adapter (single boundary)."""

import pytest

from src.services.ledger_ec_units import (
    US_PER_MS,
    ledger_ms_cm_to_us_cm,
    optional_ledger_ms_cm_to_us_cm,
    optional_us_cm_to_ledger_ms_cm,
    us_cm_to_ledger_ms_cm,
)
from src.services.tank_service import TankService


class TestLedgerEcUnits:
    def test_factor_is_1000(self) -> None:
        assert US_PER_MS == pytest.approx(1000.0)

    def test_read_ms_to_us(self) -> None:
        assert ledger_ms_cm_to_us_cm(1.4) == pytest.approx(1400.0)
        assert ledger_ms_cm_to_us_cm(2.269) == pytest.approx(2269.0)

    def test_write_us_to_ms(self) -> None:
        assert us_cm_to_ledger_ms_cm(1400.0) == pytest.approx(1.4)
        assert us_cm_to_ledger_ms_cm(488.0) == pytest.approx(0.488)

    def test_roundtrip(self) -> None:
        us = 1600.0
        assert ledger_ms_cm_to_us_cm(us_cm_to_ledger_ms_cm(us)) == pytest.approx(us)

    def test_optional_helpers(self) -> None:
        assert optional_ledger_ms_cm_to_us_cm(None) is None
        assert optional_us_cm_to_ledger_ms_cm(None) is None
        assert optional_ledger_ms_cm_to_us_cm(1.0) == pytest.approx(1000.0)


class TestTankServiceBoundaryHelpers:
    def test_to_ledger_ec_ms_cm_delegates(self) -> None:
        assert TankService.to_ledger_ec_ms_cm(2000.0) == pytest.approx(2.0)
