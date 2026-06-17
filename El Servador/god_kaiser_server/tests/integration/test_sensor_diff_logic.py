"""
Sensor Pair Difference Logic Tests

Tests for sensor_diff condition evaluator and rule template instantiation.
"""

import pytest
import uuid
from datetime import datetime, timezone

from src.db.models.logic_validation import SensorDiffCondition, validate_condition
from src.services.logic.conditions import SensorDiffConditionEvaluator
from src.services.logic.template_loader import TemplateLoader, TemplateLoadError

# =============================================================================
# Tests: SensorDiffCondition Validation
# =============================================================================


@pytest.mark.logic
class TestSensorDiffValidation:
    """Tests for SensorDiffCondition Pydantic model."""

    def test_valid_sensor_diff_condition(self):
        """Test that valid sensor_diff condition validates."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">",
            "value": 0.8,
            "consecutive_count": 3,
        }

        validated = validate_condition(condition)
        assert isinstance(validated, SensorDiffCondition)
        assert validated.sensor_a_id == sensor_a
        assert validated.sensor_b_id == sensor_b
        assert validated.operator == ">"
        assert validated.value == 0.8
        assert validated.consecutive_count == 3

    def test_sensor_diff_missing_sensor_ids(self):
        """Test validation fails without sensor IDs."""
        condition = {
            "type": "sensor_diff",
            "sensor_a_id": str(uuid.uuid4()),
            "operator": ">",
            "value": 0.8,
        }

        with pytest.raises(Exception):  # Pydantic ValidationError
            validate_condition(condition)

    def test_sensor_diff_missing_operator(self):
        """Test validation fails without operator."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "value": 0.8,
        }

        with pytest.raises(Exception):
            validate_condition(condition)

    def test_sensor_diff_same_sensor_ids(self):
        """Test validation fails when sensor_a and sensor_b are the same."""
        sensor_id = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_id,
            "sensor_b_id": sensor_id,
            "operator": ">",
            "value": 0.8,
        }

        with pytest.raises(Exception):
            validate_condition(condition)

    def test_sensor_diff_invalid_uuid_format(self):
        """Test validation fails with invalid UUID format."""
        condition = {
            "type": "sensor_diff",
            "sensor_a_id": "not-a-uuid",
            "sensor_b_id": str(uuid.uuid4()),
            "operator": ">",
            "value": 0.8,
        }

        with pytest.raises(Exception):
            validate_condition(condition)

    def test_sensor_diff_invalid_operator(self):
        """Test validation fails with invalid operator."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": "between",  # Not valid for sensor_diff
            "value": 0.8,
        }

        with pytest.raises(Exception):
            validate_condition(condition)

    def test_sensor_diff_default_consecutive_count(self):
        """Test that consecutive_count defaults to 1."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">=",
            "value": 1.5,
        }

        validated = validate_condition(condition)
        assert validated.consecutive_count == 1


# =============================================================================
# Tests: SensorDiffConditionEvaluator
# =============================================================================


@pytest.mark.logic
class TestSensorDiffEvaluator:
    """Tests for sensor_diff condition evaluator."""

    @pytest.mark.asyncio
    async def test_evaluator_supports_sensor_diff(self):
        """Test that evaluator supports sensor_diff type."""
        evaluator = SensorDiffConditionEvaluator()
        assert evaluator.supports("sensor_diff")
        assert not evaluator.supports("sensor_threshold")

    @pytest.mark.asyncio
    async def test_evaluator_simple_greater_than(self):
        """Test evaluation with simple greater-than comparison."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">",
            "value": 1.0,
            "consecutive_count": 1,
        }

        context = {
            "sensor_values": {
                sensor_a: {"value": 10.0, "sensor_type": "temperature"},
                sensor_b: {"value": 12.0, "sensor_type": "temperature"},
            }
        }

        evaluator = SensorDiffConditionEvaluator()
        result = await evaluator.evaluate(condition, context)

        # 12.0 - 10.0 = 2.0 > 1.0 → True
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluator_less_than(self):
        """Test evaluation with less-than comparison."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": "<",
            "value": 1.0,
            "consecutive_count": 1,
        }

        context = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                sensor_b: {"value": 8.5},
            }
        }

        evaluator = SensorDiffConditionEvaluator()
        result = await evaluator.evaluate(condition, context)

        # 8.5 - 10.0 = -1.5 < 1.0 → True
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluator_consecutive_count_tracking(self):
        """Test that consecutive count is tracked correctly."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">",
            "value": 1.0,
            "consecutive_count": 3,  # Require 3 consecutive
        }

        context = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                sensor_b: {"value": 12.0},  # diff = 2.0 > 1.0
            }
        }

        evaluator = SensorDiffConditionEvaluator()

        # First evaluation
        result1 = await evaluator.evaluate(condition, context)
        assert result1 is False  # 1/3

        # Second evaluation
        result2 = await evaluator.evaluate(condition, context)
        assert result2 is False  # 2/3

        # Third evaluation
        result3 = await evaluator.evaluate(condition, context)
        assert result3 is True  # 3/3

    @pytest.mark.asyncio
    async def test_evaluator_missing_sensor_data(self):
        """Test that evaluation returns False when sensor data missing."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">",
            "value": 1.0,
        }

        context = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                # sensor_b missing
            }
        }

        evaluator = SensorDiffConditionEvaluator()
        result = await evaluator.evaluate(condition, context)
        assert result is False

    @pytest.mark.asyncio
    async def test_evaluator_equality_comparison(self):
        """Test equality comparison."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": "==",
            "value": 2.0,
            "consecutive_count": 1,
        }

        context = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                sensor_b: {"value": 12.0},
            }
        }

        evaluator = SensorDiffConditionEvaluator()
        result = await evaluator.evaluate(condition, context)

        # 12.0 - 10.0 = 2.0 == 2.0 → True
        assert result is True

    @pytest.mark.asyncio
    async def test_evaluator_threshold_not_met_resets_count(self):
        """Test that consecutive count resets when threshold not met."""
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        condition = {
            "type": "sensor_diff",
            "sensor_a_id": sensor_a,
            "sensor_b_id": sensor_b,
            "operator": ">",
            "value": 2.0,
            "consecutive_count": 3,
        }

        evaluator = SensorDiffConditionEvaluator()

        # First: threshold met
        context1 = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                sensor_b: {"value": 13.0},  # diff = 3.0 > 2.0
            }
        }
        result1 = await evaluator.evaluate(condition, context1)
        assert result1 is False  # 1/3

        # Second: threshold NOT met
        context2 = {
            "sensor_values": {
                sensor_a: {"value": 10.0},
                sensor_b: {"value": 11.0},  # diff = 1.0 < 2.0
            }
        }
        result2 = await evaluator.evaluate(condition, context2)
        assert result2 is False  # Count reset to 0

        # Third: threshold met again
        result3 = await evaluator.evaluate(condition, context1)
        assert result3 is False  # Back to 1/3 (not 2/3)


# =============================================================================
# Tests: Template Loader
# =============================================================================


@pytest.mark.logic
class TestTemplateLoader:
    """Tests for rule template loader."""

    def test_loader_lists_available_templates(self):
        """Test that loader lists available templates."""
        loader = TemplateLoader()
        templates = loader.list_templates()

        # Should find at least sensor_pair_diff template
        assert len(templates) > 0
        assert "sensor_pair_diff" in templates

    def test_loader_loads_sensor_pair_diff_template(self):
        """Test loading sensor_pair_diff template."""
        loader = TemplateLoader()
        template = loader.load("sensor_pair_diff")

        assert template.name == "Sensor-Paar Differenz-Ueberwachung"
        assert template.template_id == "sensor_pair_diff_v1"
        assert "sensor_a_id" in template.required_parameters
        assert "sensor_b_id" in template.required_parameters

    def test_loader_instantiate_template_with_required_params(self):
        """Test instantiating template with required parameters."""
        loader = TemplateLoader()
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        instantiated = loader.instantiate(
            "sensor_pair_diff",
            sensor_a_id=sensor_a,
            sensor_b_id=sensor_b,
            threshold=1.5,
            operator=">=",
        )

        # Check rule structure
        assert "trigger_conditions" in instantiated
        assert "actions" in instantiated
        assert len(instantiated["trigger_conditions"]) > 0

        # Check condition substitution
        condition = instantiated["trigger_conditions"][0]
        assert condition["type"] == "sensor_diff"
        assert condition["sensor_a_id"] == sensor_a
        assert condition["sensor_b_id"] == sensor_b
        assert condition["value"] == 1.5
        assert condition["operator"] == ">="

    def test_loader_missing_required_param_raises_error(self):
        """Test that missing required parameter raises error."""
        loader = TemplateLoader()

        with pytest.raises(Exception):  # TemplateLoadError
            loader.instantiate(
                "sensor_pair_diff",
                # Missing sensor_a_id
                sensor_b_id=str(uuid.uuid4()),
            )

    def test_loader_template_info(self):
        """Test getting template info without instantiation."""
        loader = TemplateLoader()
        info = loader.get_template_info("sensor_pair_diff")

        assert info["template_id"] == "sensor_pair_diff_v1"
        assert "Sensor-Paar" in info["name"]
        assert "sensor_a_id" in info["required_parameters"]
        assert "threshold" in info["optional_parameters"]

    def test_loader_default_parameter_values(self):
        """Test that template uses default parameter values."""
        loader = TemplateLoader()
        sensor_a = str(uuid.uuid4())
        sensor_b = str(uuid.uuid4())

        # Only provide required params, use defaults for optional
        instantiated = loader.instantiate(
            "sensor_pair_diff",
            sensor_a_id=sensor_a,
            sensor_b_id=sensor_b,
        )

        condition = instantiated["trigger_conditions"][0]
        # Should use default threshold (0.8)
        assert condition["value"] == 0.8
        # Should use default consecutive_count (3)
        assert condition["consecutive_count"] == 3

    def test_loader_nonexistent_template(self):
        """Test loading nonexistent template raises error."""
        loader = TemplateLoader()

        with pytest.raises(Exception):  # TemplateLoadError
            loader.load("nonexistent_template")

    def test_loader_caches_templates(self):
        """Test that loader caches loaded templates."""
        loader = TemplateLoader()

        # Load same template twice
        template1 = loader.load("sensor_pair_diff")
        template2 = loader.load("sensor_pair_diff")

        # Should be same object (from cache)
        assert template1 is template2
