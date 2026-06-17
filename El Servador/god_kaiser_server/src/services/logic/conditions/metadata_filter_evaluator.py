"""
Metadata Filter Condition Evaluator

AUT-214: Evaluates conditions based on payload metadata fields (e.g.
sensor_metadata.quality, plant_id, device tags). Supports nested field
access via dot-notation and 7 comparison operators.

The evaluator is designed to be safe: unknown operators, missing fields
and type-mismatch errors all resolve to False so that the LogicEngine
can continue processing other rules and conditions.
"""

from typing import Any, Dict, FrozenSet, Optional

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)

# Supported operators for the metadata_filter condition type.
_SUPPORTED_OPERATORS: FrozenSet[str] = frozenset(
    {"eq", "neq", "lt", "gt", "in", "is_null", "is_not_null"}
)

# Operators that do not require a "value" entry on the condition dict.
_NULLARY_OPERATORS: FrozenSet[str] = frozenset({"is_null", "is_not_null"})


class MetadataFilterEvaluator(BaseConditionEvaluator):
    """
    Evaluates conditions against arbitrary payload metadata.

    Condition format:
        {
            "type": "metadata_filter",
            "field": "plant_id",            # dot-notation supported,
                                            # e.g. "sensor_metadata.quality"
            "operator": "eq",               # eq | neq | lt | gt | in
                                            # | is_null | is_not_null
            "value": "some-uuid"            # optional for is_null /
                                            # is_not_null operators
        }

    Field resolution:
        - Dot-separated paths walk into nested dicts (and dict-like
          mappings via __getitem__).
        - Any KeyError, TypeError or AttributeError during traversal
          resolves to None (treated as "field missing").

    Operator semantics:
        - eq / neq:    Equality comparison. When both sides are numeric
                       (int/float, no bools), they are compared as floats
                       to avoid 1 == 1.0 mismatches.
        - lt / gt:     Numeric comparison; both sides cast to float.
        - in:          Membership test; the condition value MUST be a list
                       (or other container that supports `in`).
        - is_null:     True when the resolved field value is None.
        - is_not_null: True when the resolved field value is not None.

    Error handling:
        - Unknown operator → False (logged at WARNING).
        - Numeric cast failure (e.g. float("abc")) → False.
        - Missing field for non-null operators → False.
    """

    def supports(self, condition_type: str) -> bool:
        """Check if this evaluator supports metadata filter conditions."""
        return condition_type == "metadata_filter"

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate a metadata filter condition.

        Args:
            condition: Condition dictionary (see class docstring).
            context: Evaluation context. The payload to filter is taken
                from ``context["sensor_data"]`` when present (the standard
                LogicEngine context shape), otherwise from the context
                dict itself as a fallback.

        Returns:
            True if the condition matches, False otherwise (including on
            error — never raises).
        """
        field = condition.get("field")
        operator = condition.get("operator")

        if not field or not isinstance(field, str):
            logger.warning(
                "MetadataFilterEvaluator: missing or invalid 'field' in condition"
            )
            return False

        if operator not in _SUPPORTED_OPERATORS:
            logger.warning(
                "MetadataFilterEvaluator: unknown operator '%s' (supported: %s)",
                operator,
                sorted(_SUPPORTED_OPERATORS),
            )
            return False

        # Standard LogicEngine context places the per-trigger payload under
        # "sensor_data". Fall back to the context dict itself for direct
        # callers / tests that pass a flat payload.
        payload = context.get("sensor_data")
        if not isinstance(payload, dict):
            payload = context

        field_value = self._resolve_field(payload, field)

        if operator == "is_null":
            return field_value is None
        if operator == "is_not_null":
            return field_value is not None

        # All remaining operators require a "value" entry.
        if "value" not in condition:
            logger.warning(
                "MetadataFilterEvaluator: operator '%s' requires 'value' field",
                operator,
            )
            return False

        expected_value = condition.get("value")

        try:
            if operator == "eq":
                return self._compare_eq(field_value, expected_value)
            if operator == "neq":
                return not self._compare_eq(field_value, expected_value)
            if operator == "lt":
                return float(field_value) < float(expected_value)
            if operator == "gt":
                return float(field_value) > float(expected_value)
            if operator == "in":
                if not isinstance(expected_value, (list, tuple, set, frozenset)):
                    logger.warning(
                        "MetadataFilterEvaluator: operator 'in' requires list value, "
                        "got %s",
                        type(expected_value).__name__,
                    )
                    return False
                return field_value in expected_value
        except (TypeError, ValueError) as exc:
            logger.debug(
                "MetadataFilterEvaluator: comparison failed for field='%s' "
                "operator='%s' value=%r field_value=%r: %s",
                field,
                operator,
                expected_value,
                field_value,
                exc,
            )
            return False

        # Defensive: should be unreachable thanks to the supported-operator gate.
        return False

    @staticmethod
    def _resolve_field(payload: Dict, field_path: str) -> Optional[Any]:
        """
        Walk a dot-notation field path into a (possibly nested) payload.

        Returns None when any segment is missing or cannot be traversed.
        """
        current: Any = payload
        for segment in field_path.split("."):
            if current is None:
                return None
            try:
                current = current[segment]
            except (KeyError, TypeError, AttributeError):
                return None
        return current

    @staticmethod
    def _compare_eq(field_value: Any, expected_value: Any) -> bool:
        """
        Type-safe equality comparison.

        When both operands are numeric (int/float, excluding bool), they
        are coerced to float so that ``1 == 1.0`` evaluates to True.
        Otherwise, Python's standard equality is used.
        """
        if MetadataFilterEvaluator._is_numeric(
            field_value
        ) and MetadataFilterEvaluator._is_numeric(expected_value):
            try:
                return float(field_value) == float(expected_value)
            except (TypeError, ValueError):
                return False
        return field_value == expected_value

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        """Return True for int/float values, but NOT for bool."""
        return isinstance(value, (int, float)) and not isinstance(value, bool)
