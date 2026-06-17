"""
Custom Exception Hierarchie für God-Kaiser Server
"""

from typing import Any, Dict, Optional


class GodKaiserException(Exception):
    """
    Base exception for all God-Kaiser Server errors.

    Paket X: Code Consolidation & Industrial Quality
    Alle Exceptions erben von dieser Basis-Klasse.
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        *,
        numeric_code: Optional[int] = None,
    ) -> None:
        """
        Initialize exception.

        Args:
            message: Error message
            error_code: Optional error code for categorization
            details: Optional additional details dict
            numeric_code: Optional numeric error code (1000-5999) for cross-layer tracing
        """
        self.message = message
        self.error_code = error_code or self.error_code
        self.details = details or {}
        self.numeric_code = numeric_code
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        result = {
            "error": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "numeric_code": self.numeric_code,
            "details": self.details,
        }
        return result


# Database Exceptions
class DatabaseException(GodKaiserException):
    """Base exception for database errors"""

    pass


class RecordNotFoundException(DatabaseException):
    """Raised when a database record is not found"""

    def __init__(self, model: str, identifier: Any) -> None:
        super().__init__(
            message=f"{model} with identifier {identifier} not found",
            error_code="RECORD_NOT_FOUND",
            details={"model": model, "identifier": str(identifier)},
            numeric_code=5307,  # DatabaseErrorCode.RECORD_NOT_FOUND
        )


class DuplicateRecordException(DatabaseException):
    """Raised when attempting to create a duplicate record"""

    def __init__(self, model: str, field: str, value: Any) -> None:
        super().__init__(
            message=f"{model} with {field}={value} already exists",
            error_code="DUPLICATE_RECORD",
            details={"model": model, "field": field, "value": str(value)},
            numeric_code=5308,  # DatabaseErrorCode.RECORD_DUPLICATE
        )


class DatabaseConnectionException(DatabaseException):
    """Raised when database connection fails"""

    def __init__(self, details: Optional[str] = None) -> None:
        super().__init__(
            message="Database connection failed",
            error_code="DB_CONNECTION_FAILED",
            details={"details": details} if details else {},
            numeric_code=5304,
        )


# MQTT Exceptions
class MQTTException(GodKaiserException):
    """Base exception for MQTT errors"""

    pass


class MQTTConnectionException(MQTTException):
    """Raised when MQTT connection fails"""

    def __init__(self, broker_host: str, broker_port: int, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Failed to connect to MQTT broker at {broker_host}:{broker_port}",
            error_code="MQTT_CONNECTION_FAILED",
            details={"broker_host": broker_host, "broker_port": broker_port, "details": details},
            numeric_code=5104,
        )


class MQTTPublishException(MQTTException):
    """Raised when MQTT publish fails"""

    def __init__(self, topic: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Failed to publish to topic: {topic}",
            error_code="MQTT_PUBLISH_FAILED",
            details={"topic": topic, "details": details},
            numeric_code=5101,
        )


class MQTTSubscribeException(MQTTException):
    """Raised when MQTT subscribe fails"""

    def __init__(self, topic: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Failed to subscribe to topic: {topic}",
            error_code="MQTT_SUBSCRIBE_FAILED",
            details={"topic": topic, "details": details},
            numeric_code=5108,  # MQTTErrorCode.SUBSCRIBE_FAILED
        )


# Authentication & Authorization Exceptions
class AuthenticationException(GodKaiserException):
    """Base exception for authentication errors"""

    status_code = 401


class InvalidCredentialsException(AuthenticationException):
    """Raised when credentials are invalid"""

    def __init__(self) -> None:
        super().__init__(
            message="Invalid username or password",
            error_code="INVALID_CREDENTIALS",
            numeric_code=5406,  # ServiceErrorCode.AUTHENTICATION_FAILED
        )


class TokenExpiredException(AuthenticationException):
    """Raised when JWT token is expired"""

    def __init__(self) -> None:
        super().__init__(
            message="Access token has expired",
            error_code="TOKEN_EXPIRED",
            numeric_code=5407,  # ServiceErrorCode.TOKEN_EXPIRED
        )


class InvalidTokenException(AuthenticationException):
    """Raised when JWT token is invalid"""

    def __init__(self, details: Optional[str] = None) -> None:
        super().__init__(
            message="Invalid or malformed token",
            error_code="INVALID_TOKEN",
            details={"details": details} if details else {},
            numeric_code=5408,  # ServiceErrorCode.TOKEN_INVALID
        )


class InsufficientPermissionsException(GodKaiserException):
    """Raised when user lacks required permissions"""

    def __init__(self, required_permission: str) -> None:
        super().__init__(
            message=f"Insufficient permissions. Required: {required_permission}",
            error_code="INSUFFICIENT_PERMISSIONS",
            details={"required_permission": required_permission},
            numeric_code=5409,  # ServiceErrorCode.AUTHORIZATION_FAILED
        )


# Generic Resource Exceptions (must be defined early for inheritance)
class NotFoundError(GodKaiserException):
    """Raised when a resource is not found"""

    status_code = 404
    error_code = "NOT_FOUND"

    def __init__(self, resource_type: str, identifier: Any) -> None:
        super().__init__(
            message=f"{resource_type} with identifier {identifier} not found",
            error_code="NOT_FOUND",
            details={"resource_type": resource_type, "identifier": str(identifier)},
        )


# ESP32 Device Exceptions
class ESP32Exception(GodKaiserException):
    """Base exception for ESP32 device errors"""

    pass


class ESP32NotFoundException(ESP32Exception, NotFoundError):
    """Raised when ESP32 device is not found"""

    status_code = 404
    error_code = "ESP_NOT_FOUND"

    def __init__(self, esp_id: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"ESP32 device {esp_id} not found",
            error_code="ESP_NOT_FOUND",
            details={"esp_id": esp_id},
            numeric_code=5001,
        )


class ESPNotFoundError(NotFoundError):
    """Alias for ESP32NotFoundException - Paket X compatibility"""

    error_code = "ESP_NOT_FOUND"

    def __init__(self, esp_id: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"ESP32 device {esp_id} not found",
            error_code="ESP_NOT_FOUND",
            details={"resource_type": "ESP32", "identifier": esp_id, "esp_id": esp_id},
            numeric_code=5001,
        )


class ESP32OfflineException(ESP32Exception):
    """Raised when ESP32 device is offline"""

    def __init__(self, esp_id: str) -> None:
        super().__init__(
            message=f"ESP32 device {esp_id} is offline",
            error_code="ESP32_OFFLINE",
            details={"esp_id": esp_id},
            numeric_code=5007,
        )


class ESP32CommandFailedException(ESP32Exception):
    """Raised when ESP32 command fails"""

    def __init__(self, esp_id: str, command: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Command '{command}' failed for ESP32 {esp_id}",
            error_code="ESP32_COMMAND_FAILED",
            details={"esp_id": esp_id, "command": command, "details": details},
            numeric_code=5008,  # ConfigErrorCode.ESP_COMMAND_FAILED
        )


# Sensor & Actuator Exceptions
class SensorException(GodKaiserException):
    """Base exception for sensor errors"""

    pass


class SensorNotFoundException(SensorException, NotFoundError):
    """Raised when sensor is not found"""

    status_code = 404
    error_code = "SENSOR_NOT_FOUND"

    def __init__(self, esp_id: str, gpio: int) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Sensor not found: ESP {esp_id}, GPIO {gpio}",
            error_code="SENSOR_NOT_FOUND",
            details={
                "resource_type": "Sensor",
                "identifier": f"{esp_id}:{gpio}",
                "esp_id": esp_id,
                "gpio": gpio,
            },
            numeric_code=5210,  # ValidationErrorCode.SENSOR_NOT_FOUND
        )


class SensorNotFoundError(NotFoundError):
    """Alias for SensorNotFoundException - Paket X compatibility"""

    error_code = "SENSOR_NOT_FOUND"

    def __init__(self, esp_id: str, gpio: int) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Sensor not found: ESP {esp_id}, GPIO {gpio}",
            error_code="SENSOR_NOT_FOUND",
            details={
                "resource_type": "Sensor",
                "identifier": f"{esp_id}:{gpio}",
                "esp_id": esp_id,
                "gpio": gpio,
            },
            numeric_code=5210,  # ValidationErrorCode.SENSOR_NOT_FOUND
        )


class SensorProcessingException(SensorException):
    """Raised when sensor processing fails"""

    def __init__(self, esp_id: str, gpio: int, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Sensor processing failed: ESP {esp_id}, GPIO {gpio}",
            error_code="SENSOR_PROCESSING_FAILED",
            details={"esp_id": esp_id, "gpio": gpio, "details": details},
            numeric_code=5411,  # ServiceErrorCode.SENSOR_PROCESSING_FAILED
        )


class ActuatorException(GodKaiserException):
    """Base exception for actuator errors"""

    pass


class ActuatorNotFoundException(ActuatorException, NotFoundError):
    """Raised when actuator is not found"""

    status_code = 404
    error_code = "ACTUATOR_NOT_FOUND"

    def __init__(self, esp_id: str, gpio: int) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Actuator not found: ESP {esp_id}, GPIO {gpio}",
            error_code="ACTUATOR_NOT_FOUND",
            details={
                "resource_type": "Actuator",
                "identifier": f"{esp_id}:{gpio}",
                "esp_id": esp_id,
                "gpio": gpio,
            },
            numeric_code=5211,  # ValidationErrorCode.ACTUATOR_NOT_FOUND
        )


class ActuatorNotFoundError(NotFoundError):
    """Alias for ActuatorNotFoundException - Paket X compatibility"""

    error_code = "ACTUATOR_NOT_FOUND"

    def __init__(self, esp_id: str, gpio: int) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Actuator not found: ESP {esp_id}, GPIO {gpio}",
            error_code="ACTUATOR_NOT_FOUND",
            details={
                "resource_type": "Actuator",
                "identifier": f"{esp_id}:{gpio}",
                "esp_id": esp_id,
                "gpio": gpio,
            },
            numeric_code=5211,  # ValidationErrorCode.ACTUATOR_NOT_FOUND
        )


class ActuatorCommandFailedException(ActuatorException):
    """Raised when actuator command fails"""

    def __init__(self, esp_id: str, gpio: int, command: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Actuator command '{command}' failed: ESP {esp_id}, GPIO {gpio}",
            error_code="ACTUATOR_COMMAND_FAILED",
            details={"esp_id": esp_id, "gpio": gpio, "command": command, "details": details},
            numeric_code=5412,  # ServiceErrorCode.ACTUATOR_COMMAND_FAILED
        )


class SafetyConstraintViolationException(ActuatorException):
    """Raised when safety constraint is violated"""

    def __init__(self, esp_id: str, gpio: int, constraint: str) -> None:
        super().__init__(
            message=f"Safety constraint violated: {constraint}",
            error_code="SAFETY_CONSTRAINT_VIOLATION",
            details={"esp_id": esp_id, "gpio": gpio, "constraint": constraint},
            numeric_code=5413,  # ServiceErrorCode.SAFETY_CONSTRAINT_VIOLATED
        )


class DeviceOfflineError(GodKaiserException):
    """Raised when a command targets an offline ESP device (V1-22)"""

    status_code = 409
    error_code = "DEVICE_OFFLINE"

    def __init__(self, esp_id: str, status: str) -> None:
        super().__init__(
            message=f"Cannot send command: ESP {esp_id} is offline (status={status})",
            error_code="DEVICE_OFFLINE",
            details={"esp_id": esp_id, "status": status},
            numeric_code=5414,
        )


# Validation Exceptions
class ValidationException(GodKaiserException):
    """Raised when input validation fails"""

    status_code = 400
    error_code = "VALIDATION_ERROR"

    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            message=f"Validation failed for field '{field}': {message}",
            error_code="VALIDATION_ERROR",
            details={"field": field, "validation_message": message},
            numeric_code=5205,  # ValidationErrorCode.MISSING_REQUIRED_FIELD (generic validation)
        )


class DuplicateError(GodKaiserException):
    """Raised when attempting to create a duplicate resource"""

    status_code = 409
    error_code = "DUPLICATE"

    def __init__(self, resource_type: str, field: str, value: Any) -> None:
        super().__init__(
            message=f"{resource_type} with {field}={value} already exists",
            error_code="DUPLICATE",
            details={"resource_type": resource_type, "field": field, "value": str(value)},
            numeric_code=5208,
        )


class AuthenticationError(GodKaiserException):
    """Raised when authentication fails"""

    status_code = 401
    error_code = "AUTHENTICATION_FAILED"

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_FAILED",
            numeric_code=5406,  # ServiceErrorCode.AUTHENTICATION_FAILED
        )


class AuthorizationError(GodKaiserException):
    """Raised when authorization fails"""

    status_code = 403
    error_code = "FORBIDDEN"

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(
            message=message,
            error_code="FORBIDDEN",
            numeric_code=5409,  # ServiceErrorCode.AUTHORIZATION_FAILED
        )


class MeasurementBusyError(GodKaiserException):
    """Raised when a measurement is already in progress for a sensor.

    HTTP 429 — prevents rapid-fire MQTT bursts that cause ESP-side
    publish-queue overflow and circuit-breaker trips (AUT-302).
    """

    status_code = 429
    error_code = "MEASUREMENT_BUSY"

    def __init__(
        self,
        esp_id: str,
        gpio: int,
        retry_after_seconds: int | None = None,
    ) -> None:
        details = {"esp_id": esp_id, "gpio": gpio}
        if retry_after_seconds is not None:
            details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message=f"Measurement already in progress for {esp_id}/GPIO {gpio}",
            error_code="MEASUREMENT_BUSY",
            details=details,
            numeric_code=5404,  # ServiceErrorCode.RATE_LIMIT_EXCEEDED
        )


class ServiceUnavailableError(GodKaiserException):
    """Raised when a service is unavailable"""

    status_code = 503
    error_code = "SERVICE_UNAVAILABLE"

    def __init__(self, service_name: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Service {service_name} is unavailable",
            error_code="SERVICE_UNAVAILABLE",
            details=(
                {"service_name": service_name, "details": details}
                if details
                else {"service_name": service_name}
            ),
            numeric_code=5410,  # ServiceErrorCode.EXTERNAL_SERVICE_FAILED
        )


# Configuration Exceptions
class ConfigurationException(GodKaiserException):
    """Raised when configuration is invalid"""

    def __init__(self, config_key: str, message: str) -> None:
        super().__init__(
            message=f"Invalid configuration for '{config_key}': {message}",
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key, "config_message": message},
            numeric_code=5002,
        )


# External Service Exceptions
class ExternalServiceException(GodKaiserException):
    """Base exception for external service errors"""

    pass


class GodLayerException(ExternalServiceException):
    """Raised when God Layer (AI) service fails"""

    def __init__(self, details: Optional[str] = None) -> None:
        super().__init__(
            message="God Layer service unavailable or failed",
            error_code="GOD_LAYER_FAILED",
            details={"details": details} if details else {},
            numeric_code=5410,  # ServiceErrorCode.EXTERNAL_SERVICE_FAILED
        )


class KaiserCommunicationException(ExternalServiceException):
    """Raised when Kaiser-to-Kaiser communication fails"""

    def __init__(self, kaiser_id: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Communication with Kaiser {kaiser_id} failed",
            error_code="KAISER_COMMUNICATION_FAILED",
            details={"kaiser_id": kaiser_id, "details": details},
            numeric_code=5410,  # ServiceErrorCode.EXTERNAL_SERVICE_FAILED
        )


# Simulation Exceptions (Paket X)
class SimulationException(GodKaiserException):
    """Base exception for simulation errors"""

    status_code = 500
    error_code = "SIMULATION_ERROR"


class SimulationNotRunningError(SimulationException, ValidationException):
    """Raised when simulation is not running"""

    status_code = 400
    error_code = "SIMULATION_NOT_RUNNING"

    def __init__(self, esp_id: str) -> None:
        super().__init__(
            field="simulation_state",
            message=f"Simulation for ESP {esp_id} is not running",
        )
        self.details["esp_id"] = esp_id


class EmergencyStopActiveError(SimulationException, ValidationException):
    """Raised when emergency stop is active"""

    status_code = 400
    error_code = "EMERGENCY_STOP_ACTIVE"

    def __init__(self, esp_id: str) -> None:
        super().__init__(
            field="emergency_stop",
            message=f"Emergency stop is active for ESP {esp_id}",
        )
        self.details["esp_id"] = esp_id


# Duplicate ESP Error (Paket X compatibility)
class DuplicateESPError(DuplicateError):
    """Raised when attempting to create a duplicate ESP"""

    error_code = "DUPLICATE_ESP"

    def __init__(self, esp_id: str) -> None:
        super().__init__("ESP32", "device_id", esp_id)
        self.details["esp_id"] = esp_id


# Device Configuration Exceptions
class DeviceNotApprovedError(GodKaiserException):
    """Raised when attempting to configure a device that is not approved"""

    status_code = 403
    error_code = "DEVICE_NOT_APPROVED"

    def __init__(self, esp_id: str, current_status: str) -> None:
        super().__init__(
            message=f"Device '{esp_id}' must be approved before configuration (current status: {current_status})",
            error_code="DEVICE_NOT_APPROVED",
            details={
                "device_id": esp_id,
                "current_status": current_status,
            },
            numeric_code=5405,  # ServiceErrorCode.PERMISSION_DENIED
        )


class GpioConflictError(GodKaiserException):
    """Raised when a GPIO pin conflict is detected"""

    status_code = 409
    error_code = "GPIO_CONFLICT"

    def __init__(
        self,
        gpio: int,
        conflict_type: str,
        conflict_component: Optional[str] = None,
        conflict_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        details: Dict[str, Any] = {
            "gpio": gpio,
            "conflict_type": conflict_type,
            "conflict_component": conflict_component,
            "conflict_id": conflict_id,
        }
        super().__init__(
            message=message or f"GPIO {gpio} conflict: {conflict_type}",
            error_code="GPIO_CONFLICT",
            details=details,
            numeric_code=5208,  # ValidationErrorCode.DUPLICATE_ENTRY - GPIO already in use
        )


class GatewayTimeoutError(GodKaiserException):
    """Raised when an ESP32 device does not respond within the expected timeout"""

    status_code = 504
    error_code = "GATEWAY_TIMEOUT"

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            error_code="GATEWAY_TIMEOUT",
            details=details or {},
            numeric_code=5403,  # ServiceErrorCode.OPERATION_TIMEOUT
        )


# Logic Engine Exceptions
class LogicException(GodKaiserException):
    """Base exception for logic engine errors"""

    pass


class RuleNotFoundException(LogicException, NotFoundError):
    """Raised when a logic rule is not found"""

    status_code = 404
    error_code = "RULE_NOT_FOUND"

    def __init__(self, rule_id: Any) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Logic rule '{rule_id}' not found",
            error_code="RULE_NOT_FOUND",
            details={
                "resource_type": "LogicRule",
                "identifier": str(rule_id),
                "rule_id": str(rule_id),
            },
            numeric_code=5700,
        )


class RuleValidationException(LogicException):
    """Raised when logic rule validation fails"""

    status_code = 400
    error_code = "RULE_VALIDATION_FAILED"

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            error_code="RULE_VALIDATION_FAILED",
            details=details,
            numeric_code=5701,
        )


# Subzone Exceptions (Server-side)
class SubzoneException(GodKaiserException):
    """Base exception for subzone errors"""

    pass


class SubzoneNotFoundException(SubzoneException, NotFoundError):
    """Raised when a subzone is not found on the server"""

    status_code = 404
    error_code = "SUBZONE_NOT_FOUND"

    def __init__(self, subzone_id: str, esp_id: Optional[str] = None) -> None:
        details: Dict[str, Any] = {
            "resource_type": "Subzone",
            "identifier": subzone_id,
            "subzone_id": subzone_id,
        }
        if esp_id:
            details["esp_id"] = esp_id
        GodKaiserException.__init__(
            self,
            message=f"Subzone '{subzone_id}' not found",
            error_code="SUBZONE_NOT_FOUND",
            details=details,
            numeric_code=5780,
        )


# Sequence Exceptions
class SequenceNotFoundException(NotFoundError):
    """Raised when a sequence is not found"""

    error_code = "SEQUENCE_NOT_FOUND"

    def __init__(self, sequence_id: str) -> None:
        super().__init__("Sequence", sequence_id)
        self.details["sequence_id"] = sequence_id
        self.numeric_code = 5611


# User Exceptions
class UserNotFoundException(NotFoundError):
    """Raised when a user is not found"""

    error_code = "USER_NOT_FOUND"

    def __init__(self, user_id: Any) -> None:
        super().__init__("User", user_id)
        self.numeric_code = 5414  # ServiceErrorCode.USER_NOT_FOUND


# Dashboard Exceptions
class DashboardNotFoundException(NotFoundError):
    """Raised when a dashboard is not found or not accessible"""

    error_code = "DASHBOARD_NOT_FOUND"

    def __init__(self, dashboard_id: Any) -> None:
        super().__init__("Dashboard", dashboard_id)
        self.numeric_code = 5750


# Notification Exceptions (Phase 4A)
class NotificationException(GodKaiserException):
    """Base exception for notification errors"""

    pass


class NotificationNotFoundException(NotificationException, NotFoundError):
    """Raised when a notification is not found"""

    status_code = 404
    error_code = "NOTIFICATION_NOT_FOUND"

    def __init__(self, notification_id: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Notification '{notification_id}' not found",
            error_code="NOTIFICATION_NOT_FOUND",
            details={"resource_type": "Notification", "identifier": str(notification_id)},
            numeric_code=5850,  # NotificationErrorCode.NOTIFICATION_NOT_FOUND
        )


class NotificationSendFailedException(NotificationException):
    """Raised when notification send fails"""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Notification send failed: {reason}",
            error_code="NOTIFICATION_SEND_FAILED",
            details={"reason": reason},
            numeric_code=5851,  # NotificationErrorCode.NOTIFICATION_SEND_FAILED
        )


class EmailProviderUnavailableException(NotificationException):
    """Raised when email provider is unavailable"""

    status_code = 503
    error_code = "EMAIL_PROVIDER_UNAVAILABLE"

    def __init__(self, provider: Optional[str] = None) -> None:
        super().__init__(
            message="Email service not available. Check EMAIL_ENABLED and provider configuration.",
            error_code="EMAIL_PROVIDER_UNAVAILABLE",
            details={"provider": provider} if provider else {},
            numeric_code=5852,  # NotificationErrorCode.EMAIL_PROVIDER_UNAVAILABLE
        )


class EmailSendException(NotificationException):
    """Raised when email delivery fails"""

    status_code = 502
    error_code = "EMAIL_SEND_FAILED"

    def __init__(self, provider: str, reason: str = "delivery failed") -> None:
        super().__init__(
            message=f"Email delivery failed via {provider}: {reason}",
            error_code="EMAIL_SEND_FAILED",
            details={"provider": provider, "reason": reason},
            numeric_code=5851,  # NotificationErrorCode.NOTIFICATION_SEND_FAILED
        )


class WebhookValidationException(ValidationException):
    """Raised when webhook payload validation fails"""

    error_code = "WEBHOOK_INVALID_PAYLOAD"

    def __init__(self, reason: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Webhook payload invalid: {reason}",
            error_code="WEBHOOK_INVALID_PAYLOAD",
            details={"reason": reason},
            numeric_code=5857,  # NotificationErrorCode.WEBHOOK_INVALID_PAYLOAD
        )


class AlertPreferenceNotFoundException(NotificationException, NotFoundError):
    """Raised when alert preference is not found"""

    status_code = 404
    error_code = "ALERT_PREFERENCE_NOT_FOUND"

    def __init__(self, identifier: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Alert preference for '{identifier}' not found",
            error_code="ALERT_PREFERENCE_NOT_FOUND",
            details={"resource_type": "AlertPreference", "identifier": identifier},
            numeric_code=5859,  # NotificationErrorCode.ALERT_PREFERENCE_NOT_FOUND
        )


class NoEmailRecipientException(NotificationException):
    """Raised when no email address is available for sending"""

    status_code = 422
    error_code = "NO_EMAIL_RECIPIENT"

    def __init__(
        self,
        message: str = "No email address found. Provide one in the request or set it in preferences.",
    ) -> None:
        super().__init__(
            message=message,
            error_code="NO_EMAIL_RECIPIENT",
            numeric_code=5853,
        )


class AlertInvalidStateTransition(NotificationException):
    """Raised when an invalid alert lifecycle state transition is attempted"""

    status_code = 409
    error_code = "ALERT_INVALID_STATE_TRANSITION"

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Cannot transition alert from '{current_status}' to '{target_status}'",
            error_code="ALERT_INVALID_STATE_TRANSITION",
            details={
                "current_status": current_status,
                "target_status": target_status,
            },
            numeric_code=5860,
        )


# Kaiser Exceptions (AUT-228 E3)
# Strukturierte Exceptions fuer Kaiser-Router; loesen direkte HTTPException-Aufrufe
# in src/api/v1/kaiser.py ab und mappen ueber den globalen Exception-Handler auf
# numeric_code (5xxx) im API-Response.
class KaiserException(GodKaiserException):
    """Base exception for Kaiser relay node errors"""

    pass


class KaiserNotFoundException(KaiserException, NotFoundError):
    """Raised when a Kaiser relay node is not found"""

    status_code = 404
    error_code = "KAISER_NOT_FOUND"

    def __init__(self, kaiser_id: str) -> None:
        GodKaiserException.__init__(
            self,
            message=f"Kaiser '{kaiser_id}' not found",
            error_code="KAISER_NOT_FOUND",
            details={
                "resource_type": "Kaiser",
                "identifier": kaiser_id,
                "kaiser_id": kaiser_id,
            },
            numeric_code=5307,  # DatabaseErrorCode.RECORD_NOT_FOUND (kein dedizierter Kaiser-Range)
        )


class KaiserAlreadyExistsError(KaiserException):
    """Raised when attempting to register a Kaiser that already exists"""

    status_code = 409
    error_code = "KAISER_ALREADY_EXISTS"

    def __init__(self, kaiser_id: str, details: Optional[str] = None) -> None:
        super().__init__(
            message=f"Kaiser '{kaiser_id}' already exists" + (f": {details}" if details else ""),
            error_code="KAISER_ALREADY_EXISTS",
            details={"kaiser_id": kaiser_id, "details": details},
            numeric_code=5308,  # DatabaseErrorCode.RECORD_DUPLICATE
        )


class KaiserIdRequiredError(ValidationException):
    """Raised when kaiser_id is missing in a register request"""

    error_code = "KAISER_ID_REQUIRED"

    def __init__(self) -> None:
        GodKaiserException.__init__(
            self,
            message="Validation failed for field 'kaiser_id': kaiser_id is required",
            error_code="KAISER_ID_REQUIRED",
            details={"field": "kaiser_id", "validation_message": "kaiser_id is required"},
            numeric_code=5205,  # ValidationErrorCode.MISSING_REQUIRED_FIELD
        )


class SensorConfigInvalidUuidError(ValidationException):
    """Raised when sensor_config_id is not a valid UUID"""

    error_code = "INVALID_SENSOR_CONFIG_UUID"

    def __init__(self, value: str) -> None:
        GodKaiserException.__init__(
            self,
            message=(
                f"Validation failed for field 'sensor_config_id': "
                f"'{value}' is not a valid UUID"
            ),
            error_code="INVALID_SENSOR_CONFIG_UUID",
            details={
                "field": "sensor_config_id",
                "validation_message": "must be a valid UUID",
                "value": value,
            },
            numeric_code=5209,  # ValidationErrorCode.INVALID_PAYLOAD_FORMAT
        )

