"""Shared grower phase vocabulary — legacy zone strings → PLANT_PHASES."""

import pytest

from src.services.growth_phase_vocabulary import (
    CANONICAL_PHASE_SET,
    majority_phase,
    normalize_growth_phase,
    require_canonical_phase,
    to_threshold_bucket,
)


class TestNormalizeGrowthPhase:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("veg-frueh", "veg-frueh"),
            ("VEG-FRUEH", "veg-frueh"),
            ("vegetative", "veg-frueh"),
            ("seedling", "clone"),
            ("pre_flower", "uebergang-vorbluete"),
            ("flower_week_1", "bluete-stretch"),
            ("flower_week_4", "bluete-stretch"),
            ("flower_week_5", "bluete-bulk"),
            ("flower_week_8", "bluete-bulk"),
            ("flower_week_9", "bluete-ende"),
            ("flower_week_10", "bluete-ende"),
            ("flower_week_12", "bluete-ende"),
            ("flush", "bluete-ende"),
            ("harvest", "harvested"),
            ("drying", "harvested"),
            ("flower_early", "bluete-stretch"),
            ("flower_late", "bluete-bulk"),
            ("", None),
            (None, None),
            ("not-a-phase", None),
        ],
    )
    def test_maps_legacy_and_canonical(self, raw: str | None, expected: str | None) -> None:
        assert normalize_growth_phase(raw) == expected

    def test_canonical_keys_are_identity(self) -> None:
        for key in CANONICAL_PHASE_SET:
            assert normalize_growth_phase(key) == key

    def test_require_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown growth phase"):
            require_canonical_phase("totally-unknown")


class TestThresholdBucket:
    def test_canonical_bloom_maps_to_flower_buckets(self) -> None:
        assert to_threshold_bucket("bluete-stretch") == "flower_early"
        assert to_threshold_bucket("bluete-bulk") == "flower_late"
        assert to_threshold_bucket("flower_week_5") == "flower_late"

    def test_empty_falls_back_to_vegetative(self) -> None:
        assert to_threshold_bucket(None) == "vegetative"
        assert to_threshold_bucket("") == "vegetative"


class TestMajorityPhase:
    def test_majority_prefers_most_common_canonical(self) -> None:
        assert (
            majority_phase(["flower_week_5", "bluete-bulk", "veg-frueh", "vegetative"])
            == "bluete-bulk"
        )

    def test_tie_keeps_first_seen(self) -> None:
        assert majority_phase(["veg-frueh", "bluete-bulk"]) == "veg-frueh"

    def test_ignores_unknown(self) -> None:
        assert majority_phase(["???", None, ""]) is None
