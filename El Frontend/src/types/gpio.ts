/**
 * GPIO Status Types
 *
 * Mirrors server-side schemas from Phase 2 (gpio_validation_service.py, esp.py schemas).
 * Used throughout frontend for GPIO visualization and validation.
 *
 * @author KI-Agent (Claude)
 * @since Phase 3 (GPIO-Status Frontend Integration)
 * @see El Servador/god_kaiser_server/src/schemas/esp.py (GpioStatusItem, GpioStatusResponse)
 */

// =============================================================================
// Base Types
// =============================================================================

/**
 * Owner type for GPIO pins.
 * Matches server regex: ^(sensor|actuator|system)$
 */
export type GpioOwner = 'sensor' | 'actuator' | 'system'

/**
 * Source of GPIO status information.
 * - database: From SensorConfig/ActuatorConfig in PostgreSQL
 * - esp_reported: From ESP32 heartbeat gpio_status array
 * - static: Statically reserved pins (Flash, UART, Boot)
 */
export type GpioSource = 'database' | 'esp_reported' | 'static'

// =============================================================================
// API Response Types (match server schemas)
// =============================================================================

/**
 * Single GPIO usage entry from server.
 * Represents one reserved/used GPIO pin.
 *
 * @see El Servador/god_kaiser_server/src/schemas/esp.py:GpioUsageItem
 */
export interface GpioUsageItem {
  /** GPIO pin number (0-48 for ESP32) */
  gpio: number
  /** Who owns this pin: sensor, actuator, or system */
  owner: GpioOwner
  /** Component type (e.g., "DS18B20", "pump_1", "I2C_SDA") */
  component: string
  /** Human-readable name (null for system pins or unnamed) */
  name: string | null
  /** Database UUID of sensor/actuator (null for system/esp_reported pins) */
  id: string | null
  /** Where this info comes from */
  source: GpioSource
}

/**
 * OneWire bus information (for multi-device support).
 * Multiple DS18B20 sensors can share the same GPIO pin.
 */
export interface OneWireBusInfo {
  /** GPIO pin for this OneWire bus */
  gpio: number
  /** True - OneWire buses can always share GPIOs */
  is_available: boolean
  /** List of devices on this bus */
  devices: Array<{
    onewire_address: string | null
    sensor_type: string
    sensor_name: string | null
  }>
}

/**
 * Complete GPIO status for an ESP device.
 * Response from GET /api/v1/esp/devices/{esp_id}/gpio-status
 *
 * @see El Servador/god_kaiser_server/src/schemas/esp.py:GpioStatusResponse
 */
export interface GpioStatusResponse {
  /** ESP device ID */
  esp_id: string
  /** List of available (free) GPIO pins */
  available: number[]
  /** List of reserved/used GPIO pins with details */
  reserved: GpioUsageItem[]
  /** System-reserved pins (Flash, UART, etc.) - always unavailable */
  system: number[]
  // =========================================================================
  // OneWire Multi-Device Support
  // =========================================================================
  /** Exclusively reserved GPIOs (Analog/Digital sensors only) */
  reserved_gpios?: number[]
  /** OneWire buses with connected devices (shareable GPIOs) */
  onewire_buses?: OneWireBusInfo[]
  /** Hardware type for pin compatibility (e.g., "ESP32_WROOM", "XIAO_ESP32_C3") */
  hardware_type: string
  /** Timestamp of last ESP heartbeat with GPIO info (ISO format) */
  last_esp_report: string | null
}

// =============================================================================
// UI Display Types
// =============================================================================

/**
 * GPIO pin status for UI display.
 * Enriched version combining static config with dynamic status.
 */
export interface GpioPinStatus {
  /** GPIO pin number */
  gpio: number
  /** Whether pin is available for use */
  available: boolean
  /** Owner if reserved, null if available */
  owner: GpioOwner | null
  /** Component type if reserved */
  component: string | null
  /** Human-readable name if configured */
  name: string | null
  /** CSS class for styling: 'available' | 'sensor' | 'actuator' | 'system' */
  statusClass: 'available' | 'sensor' | 'actuator' | 'system'
  /** Tooltip text for UI display */
  tooltip: string
}

/**
 * GPIO validation result (client-side pre-check).
 * Used before submitting sensor/actuator creation.
 */
export interface GpioValidationResult {
  /** Whether GPIO selection is valid */
  valid: boolean
  /** Error/info message (null if valid) */
  message: string | null
}

// =============================================================================
// WebSocket Event Types (from heartbeat)
// =============================================================================

/**
 * GPIO status item from ESP32 heartbeat.
 * Raw format as received in esp_health WebSocket events.
 *
 * @see El Trabajante/docs/Mqtt_Protocoll.md (Heartbeat gpio_status)
 */
export interface HeartbeatGpioItem {
  /** GPIO pin number */
  gpio: number
  /** Owner category */
  owner: string
  /** Component name */
  component: string
  /** Pin mode: 0=INPUT, 1=OUTPUT, 2=INPUT_PULLUP */
  mode: number
  /** True if in safe mode (not actively used) */
  safe: boolean
}
