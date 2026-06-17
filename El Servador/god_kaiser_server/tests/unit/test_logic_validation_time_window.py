import pytest
from pydantic import ValidationError

from src.db.models.logic_validation import validate_condition


class TestTimeWindowMinuteValidation:
    def test_time_window_accepts_explicit_minutes(self):
        cond = validate_condition(
            {
                "type": "time_window",
                "start_hour": 7,
                "start_minute": 30,
                "end_hour": 8,
                "end_minute": 15,
                "days_of_week": [0, 1, 2, 3, 4],
            }
        )
        assert cond.start_minute == 30
        assert cond.end_minute == 15

    def test_time_alias_is_accepted(self):
        cond = validate_condition(
            {
                "type": "time",
                "start_hour": 9,
                "start_minute": 5,
                "end_hour": 9,
                "end_minute": 6,
            }
        )
        assert cond.type == "time"

    def test_end_hour_24_requires_end_minute_zero(self):
        with pytest.raises(ValidationError):
            validate_condition(
                {
                    "type": "time_window",
                    "start_hour": 23,
                    "start_minute": 0,
                    "end_hour": 24,
                    "end_minute": 1,
                }
            )

    def test_invalid_minute_is_rejected(self):
        with pytest.raises(ValidationError):
            validate_condition(
                {
                    "type": "time_window",
                    "start_hour": 7,
                    "start_minute": 60,
                    "end_hour": 8,
                    "end_minute": 0,
                }
            )
