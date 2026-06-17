"""
Base MQTT Handler

DEPRECATION NOTICE (AUT-225, 2026-05):
====================================================================
This abstract base class is currently UNUSED. None of the 19 concrete
MQTT handlers (HeartbeatHandler, SensorDataHandler, ActuatorResponseHandler,
LWTHandler, ConfigHandler, CalibrationResponseHandler, ZoneAckHandler,
SubzoneAckHandler, EmergencyAckHandler, RecoveryConfirmHandler,
DiagnosticsHandler, ErrorEventHandler, IntentOutcomeHandler,
IntentOutcomeLifecycleHandler, QueuePressureHandler, ActuatorAlertHandler,
ActuatorStatusHandler, HeartbeatMetricsHandler) inherit from
BaseMQTTHandler. Each handler implements its own validation/parsing.

Status: KEPT for backwards compatibility / future migration.
Migration: tracked via follow-up issue (planned post AUT-225). Do NOT
extend this class for NEW handlers without a clear migration plan
covering all 19 existing handlers. Adding partial inheritance would
introduce two parallel handler patterns and increase confusion.

If you are starting a new handler, follow the pattern of one of the
existing concrete handlers (e.g., ``heartbeat_handler.py``) until the
migration is scheduled.

Original purpose (preserved for reference):
- Standardized topic parsing
- Payload validation with structured errors
- ESP device lookup with error handling
- WebSocket broadcasting
- Audit logging
- Consistent error patterns

Phase: Runtime Config Flow Implementation
Priority: MEDIUM
Status: DEPRECATED-UNUSED (AUT-225)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.error_codes import (
    ValidationErrorCode,
)
from ...core.logging_config import get_logger
from ...db.models.esp import ESPDevice
from ...db.repositories import ESPRepository
from ...db.repositories.audit_log_repo import AuditLogRepository

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class ValidationResult:
    """
    Result of payload validation.

    Attributes:
        valid: Whether validation passed
        error_code: Error code if validation failed
        error_message: Human-readable error message
        errors: List of specific field errors
        data: Validated and transformed data (if valid)
    """

    valid: bool = True
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None

    @classmethod
    def success(cls, data: Optional[Dict[str, Any]] = None) -> "ValidationResult":
        """Create successful validation result."""
        return cls(valid=True, data=data)

    @classmethod
    def failure(
        cls,
        error_code: int,
        error_message: str,
        errors: Optional[List[Dict[str, Any]]] = None,
    ) -> "ValidationResult":
        """Create failed validation result."""
        return cls(
            valid=False,
            error_code=error_code,
            error_message=error_message,
            errors=errors or [],
        )


@dataclass
class TopicParseResult:
    """
    Result of topic parsing.

    Attributes:
        valid: Whether parsing succeeded
        kaiser_id: Extracted kaiser ID
        esp_id: Extracted ESP device ID
        extra: Any additional parsed components
        error: Error message if parsing failed
    """

    valid: bool = True
    kaiser_id: Optional[str] = None
    esp_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @classmethod
    def success(
        cls,
        kaiser_id: str,
        esp_id: str,
        **extra: Any,
    ) -> "TopicParseResult":
        """Create successful parse result."""
        return cls(valid=True, kaiser_id=kaiser_id, esp_id=esp_id, extra=extra)

    @classmethod
    def failure(cls, error: str) -> "TopicParseResult":
        """Create failed parse result."""
        return cls(valid=False, error=error)


class BaseMQTTHandler(ABC):
    """
    Base class for all MQTT message handlers.

    Provides:
    - Standardized topic parsing
    - Payload validation framework
    - ESP device lookup with caching
    - WebSocket broadcast helper
    - Audit logging integration
    - Consistent error handling

    Subclasses must implement:
    - parse_topic(topic): Parse MQTT topic string
    - validate_payload(payload): Validate message payload
    - process_message(topic_result, payload, esp_device): Business logic

    Usage:
        class MySensorHandler(BaseMQTTHandler):
            def parse_topic(self, topic: str) -> TopicParseResult:
                # Parse sensor topic
                ...

            def validate_payload(self, payload: Dict) -> ValidationResult:
                # Validate sensor data
                ...

            async def process_message(
                self,
                topic_result: TopicParseResult,
                payload: Dict,
                esp_device: Optional[ESPDevice],
            ) -> None:
                # Process sensor data
                ...
    """

    # Handler name for logging
    handler_name: str = "base"

    # Whether ESP device must exist for this handler
    require_esp_device: bool = True

    # WebSocket event name for broadcasts
    ws_event_name: Optional[str] = None

    def __init__(
        self,
        db: AsyncSession,
        ws_manager: Optional[Any] = None,
    ):
        """
        Initialize handler.

        Args:
            db: Database session
            ws_manager: WebSocket manager for broadcasts (optional)
        """
        self.db = db
        self.ws_manager = ws_manager
        self.esp_repo = ESPRepository(db)
        self.audit_repo = AuditLogRepository(db)
        self._esp_cache: Dict[str, ESPDevice] = {}

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    async def handle(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Handle incoming MQTT message.

        This is the main entry point called by the MQTT client.
        It orchestrates topic parsing, validation, ESP lookup, and processing.

        Args:
            topic: MQTT topic string
            payload: Parsed JSON payload
        """
        handler_logger = get_logger(f"{__name__}.{self.handler_name}")

        # 1. Parse topic
        topic_result = self.parse_topic(topic)
        if not topic_result.valid:
            handler_logger.warning(f"Failed to parse topic: {topic} - {topic_result.error}")
            return

        # 2. Validate payload
        validation_result = self.validate_payload(payload)
        if not validation_result.valid:
            handler_logger.warning(
                f"Payload validation failed for {topic}: "
                f"{validation_result.error_code} - {validation_result.error_message}"
            )
            await self._log_validation_error(topic_result, validation_result)
            return

        # 3. Lookup ESP device (if required)
        esp_device = None
        if topic_result.esp_id:
            esp_device = await self._get_esp_device(topic_result.esp_id)

            if self.require_esp_device and not esp_device:
                handler_logger.warning(f"Unknown ESP device: {topic_result.esp_id}")
                return

        # 4. Process message (implemented by subclass)
        try:
            await self.process_message(
                topic_result,
                validation_result.data or payload,
                esp_device,
            )
        except Exception as e:
            handler_logger.error(
                f"Error processing message for {topic}: {e}",
                exc_info=True,
            )
            await self._log_processing_error(topic_result, str(e))

    # =========================================================================
    # Abstract Methods (Must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    def parse_topic(self, topic: str) -> TopicParseResult:
        """
        Parse MQTT topic string.

        Args:
            topic: Full MQTT topic string

        Returns:
            TopicParseResult with extracted components
        """
        pass

    @abstractmethod
    def validate_payload(self, payload: Dict[str, Any]) -> ValidationResult:
        """
        Validate message payload.

        Args:
            payload: Parsed JSON payload

        Returns:
            ValidationResult with validation status and errors
        """
        pass

    @abstractmethod
    async def process_message(
        self,
        topic_result: TopicParseResult,
        payload: Dict[str, Any],
        esp_device: Optional[ESPDevice],
    ) -> None:
        """
        Process validated message.

        Args:
            topic_result: Parsed topic components
            payload: Validated payload data
            esp_device: ESP device model (if found)
        """
        pass

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def validate_required_fields(
        self,
        payload: Dict[str, Any],
        required_fields: List[str],
    ) -> ValidationResult:
        """
        Validate that required fields are present.

        Args:
            payload: Payload to validate
            required_fields: List of required field names

        Returns:
            ValidationResult
        """
        errors = []
        for field_name in required_fields:
            if field_name not in payload:
                errors.append(
                    {
                        "field": field_name,
                        "error": "Missing required field",
                    }
                )

        if errors:
            return ValidationResult.failure(
                error_code=ValidationErrorCode.MISSING_REQUIRED_FIELD,
                error_message=f"Missing required fields: {[e['field'] for e in errors]}",
                errors=errors,
            )

        return ValidationResult.success(data=payload)

    def validate_field_type(
        self,
        payload: Dict[str, Any],
        field_name: str,
        expected_type: Type[T],
        allow_none: bool = False,
    ) -> Optional[str]:
        """
        Validate field type.

        Args:
            payload: Payload containing field
            field_name: Field name to validate
            expected_type: Expected Python type
            allow_none: Whether None is allowed

        Returns:
            Error message if invalid, None if valid
        """
        value = payload.get(field_name)

        if value is None:
            if not allow_none and field_name in payload:
                return f"{field_name} cannot be null"
            return None

        if not isinstance(value, expected_type):
            return f"{field_name} must be {expected_type.__name__}, got {type(value).__name__}"

        return None

    def validate_string_field(
        self,
        payload: Dict[str, Any],
        field_name: str,
        min_length: int = 0,
        max_length: int = 1000,
        pattern: Optional[str] = None,
    ) -> Optional[str]:
        """
        Validate string field.

        Args:
            payload: Payload containing field
            field_name: Field name to validate
            min_length: Minimum string length
            max_length: Maximum string length
            pattern: Optional regex pattern

        Returns:
            Error message if invalid, None if valid
        """
        import re

        value = payload.get(field_name)
        if value is None:
            return None

        if not isinstance(value, str):
            return f"{field_name} must be a string"

        if len(value) < min_length:
            return f"{field_name} must be at least {min_length} characters"

        if len(value) > max_length:
            return f"{field_name} must not exceed {max_length} characters"

        if pattern and not re.match(pattern, value):
            return f"{field_name} has invalid format"

        return None

    def validate_numeric_field(
        self,
        payload: Dict[str, Any],
        field_name: str,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> Optional[str]:
        """
        Validate numeric field.

        Args:
            payload: Payload containing field
            field_name: Field name to validate
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            Error message if invalid, None if valid
        """
        value = payload.get(field_name)
        if value is None:
            return None

        if not isinstance(value, (int, float)):
            return f"{field_name} must be a number"

        if min_value is not None and value < min_value:
            return f"{field_name} must be at least {min_value}"

        if max_value is not None and value > max_value:
            return f"{field_name} must not exceed {max_value}"

        return None

    # =========================================================================
    # ESP Device Helpers
    # =========================================================================

    async def _get_esp_device(self, esp_id: str) -> Optional[ESPDevice]:
        """
        Get ESP device with caching.

        Args:
            esp_id: ESP device ID

        Returns:
            ESPDevice or None
        """
        if esp_id in self._esp_cache:
            return self._esp_cache[esp_id]

        device = await self.esp_repo.get_by_device_id(esp_id)
        if device:
            self._esp_cache[esp_id] = device

        return device

    def clear_esp_cache(self) -> None:
        """Clear ESP device cache."""
        self._esp_cache.clear()

    # =========================================================================
    # WebSocket Broadcast Helpers
    # =========================================================================

    async def broadcast_event(
        self,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Broadcast event via WebSocket.

        Args:
            event_type: Event type name
            data: Event data to broadcast
        """
        if self.ws_manager:
            try:
                await self.ws_manager.broadcast(event_type, data)
            except Exception as e:
                logger.warning(f"WebSocket broadcast failed: {e}")

    async def broadcast_to_esp(
        self,
        esp_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> None:
        """
        Broadcast event for specific ESP device.

        Args:
            esp_id: Target ESP device ID
            event_type: Event type name
            data: Event data (esp_id will be added)
        """
        data_with_esp = {"esp_id": esp_id, **data}
        await self.broadcast_event(event_type, data_with_esp)

    # =========================================================================
    # Audit Logging Helpers
    # =========================================================================

    async def _log_validation_error(
        self,
        topic_result: TopicParseResult,
        validation_result: ValidationResult,
    ) -> None:
        """Log validation error to audit log."""
        try:
            await self.audit_repo.log_validation_error(
                source_type="mqtt",
                source_id=topic_result.esp_id or "unknown",
                error_code=str(validation_result.error_code or 0),
                error_description=validation_result.error_message or "Validation failed",
                details={
                    "handler": self.handler_name,
                    "errors": validation_result.errors,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log validation error: {e}")

    async def _log_processing_error(
        self,
        topic_result: TopicParseResult,
        error_message: str,
    ) -> None:
        """Log processing error to audit log."""
        try:
            await self.audit_repo.log_mqtt_error(
                source_id=topic_result.esp_id or "unknown",
                error_code="PROCESSING_ERROR",
                error_description=error_message,
                details={
                    "handler": self.handler_name,
                    "kaiser_id": topic_result.kaiser_id,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log processing error: {e}")

    async def log_device_event(
        self,
        esp_id: str,
        event_type: str,
        status: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log device event to audit log.

        Args:
            esp_id: ESP device ID
            event_type: Type of event
            status: Event status (success, failed, etc.)
            message: Human-readable message
            details: Additional event details
        """
        try:
            await self.audit_repo.log_device_event(
                esp_id=esp_id,
                event_type=event_type,
                status=status,
                message=message,
                details=details,
            )
        except Exception as e:
            logger.warning(f"Failed to log device event: {e}")
