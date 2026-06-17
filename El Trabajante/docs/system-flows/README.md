# System Flow Documentation

Comprehensive flow documentation for El Trabajante ESP32 firmware.

## Purpose

This documentation enables developers and AI systems to:

- **Understand system behavior** at method level
- **Find exact code locations** for debugging and modification
- **Integrate with God-Kaiser** by understanding MQTT protocols
- **Perform targeted refactoring** with confidence
- **Diagnose issues** by tracing execution flows

## Documentation Approach

Each flow document provides:

- **Real code snippets** from El Trabajante (no pseudocode)
- **Exact file paths and line numbers** for all operations
- **Complete MQTT specifications** (topics, payloads, QoS)
- **NVS operations** (namespaces, keys, data types)
- **Timing and memory analysis**
- **Error handling scenarios**
- **Cross-references** to related flows

## Flow Documents

### Core System Flows

| # | Flow | Description | Priority |
|---|------|-------------|----------|
| [01](01-boot-sequence.md) | **Boot Sequence** | Complete system initialization from power-on to operational state | Critical |
| [06](06-mqtt-message-routing-flow.md) | **MQTT Message Routing** | Central message dispatch and handler coordination | Critical |

### Data Acquisition and Control

| # | Flow | Description | Priority |
|---|------|-------------|----------|
| [02](02-sensor-reading-flow.md) | **Sensor Reading Flow** | Periodic sensor measurement and MQTT publishing | High |
| [03](03-actuator-command-flow.md) | **Actuator Command Flow** | Command reception, validation, and execution | High |

### Runtime Configuration

| # | Flow | Description | Priority |
|---|------|-------------|----------|
| [04](04-runtime-sensor-config-flow.md) | **Runtime Sensor Config** | Dynamic sensor configuration via MQTT | Medium |
| [05](05-runtime-actuator-config-flow.md) | **Runtime Actuator Config** | Dynamic actuator configuration via MQTT | Medium |

### System Management

| # | Flow | Description | Priority |
|---|------|-------------|----------|
| [07](07-error-recovery-flow.md) | **Error Recovery** | Auto-recovery mechanisms and circuit breakers | High |
| [08](08-zone-assignment-flow.md) | **Zone Assignment** | Hierarchical zone management (Phase 7) | Medium |
| [09](09-subzone-management-flow.md) | **Subzone Management** | ⭐ **NEW** Pin-level subzone management with Safe-Mode integration | Medium |

## How to Read These Documents

### File References

File references include exact line ranges:

```
File: main.cpp (lines 54-632)
Method: setup()
```

### Code Snippets

All code snippets are real code from El Trabajante:

```cpp
// From drivers/gpio_manager.cpp (lines 31-88)
void GPIOManager::initializeAllPinsToSafeMode() {
    Serial.println("\n=== GPIO SAFE-MODE INITIALIZATION ===");
    // ... implementation ...
}
```

### MQTT Topics

Topics use placeholders for dynamic values:

```
Topic Pattern: kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data
Example: kaiser/god/esp/ESP_AB12CD/sensor/4/data
```

### NVS Operations

Storage operations specify namespace and keys:

```
Namespace: sensor_config
Keys: 
  - sensor_count (uint8_t)
  - sensor_{i}_gpio (uint8_t)
  - sensor_{i}_type (String)
```

## System Architecture Context

### Phase Structure

El Trabajante follows a phased initialization:

1. **Phase 1**: Core Infrastructure (GPIO, Logger, Storage, Config)
2. **Phase 2**: Communication Layer (WiFi, MQTT)
3. **Phase 3**: Hardware Abstraction (I2C, OneWire, PWM)
4. **Phase 4**: Sensor System
5. **Phase 5**: Actuator System
6. **Phase 6**: Provisioning System
7. **Phase 7**: Zone Management

### Key Components

- **GPIOManager**: Hardware safety and pin management
- **StorageManager**: NVS abstraction layer
- **ConfigManager**: Configuration persistence
- **MQTTClient**: Communication with God-Kaiser
- **SensorManager**: Sensor orchestration
- **ActuatorManager**: Actuator control and safety
- **SafetyController**: Emergency stop and safety interlocks
- **ErrorTracker**: Error history and recovery

## Common Patterns

### Singleton Pattern

Most managers use the singleton pattern:

```cpp
SensorManager& sensorManager = SensorManager::getInstance();
```

### Error Handling

Errors are tracked via ErrorTracker:

```cpp
errorTracker.trackError(ERROR_SENSOR_INIT_FAILED, 
                       ERROR_SEVERITY_CRITICAL,
                       "Sensor initialization failed");
```

### MQTT Publishing

Standard pattern for MQTT publishing:

```cpp
String topic = TopicBuilder::buildSensorDataTopic(gpio);
mqttClient.publish(topic, payload, QoS_1);
```

### NVS Access

Storage operations through StorageManager:

```cpp
storageManager.beginNamespace("sensor_config", false);
storageManager.putString("sensor_0_type", "temp_ds18b20");
storageManager.endNamespace();
```

## Integration with God-Kaiser

These flows document the ESP32 side of the God-Kaiser ↔ ESP32 integration:

- **Heartbeat**: ESP announces presence and capabilities
- **Discovery**: God-Kaiser discovers and registers ESPs
- **Configuration**: God-Kaiser pushes sensor/actuator configs
- **Data Flow**: Sensors publish → God-Kaiser processes
- **Control**: God-Kaiser commands → Actuators execute
- **Zone Management**: Hierarchical zone assignment

## Development Workflow

### Adding New Features

1. Read relevant flow documents to understand current behavior
2. Identify exact code locations to modify
3. Understand MQTT contracts (don't break compatibility!)
4. Check NVS keys (avoid conflicts)
5. Update flow documentation after changes

### Debugging Issues

1. Identify which flow is involved
2. Trace execution through documented steps
3. Check MQTT message format matches documentation
4. Verify NVS operations are correct
5. Review error handling scenarios

### Testing Changes

1. Verify boot sequence completes successfully
2. Test MQTT message routing with real broker
3. Confirm sensor readings are published correctly
4. Validate actuator commands execute safely
5. Test error recovery mechanisms

## Files Analyzed

This documentation is based on analysis of:

### Core System
- `src/main.cpp` - System orchestration and setup
- `src/drivers/gpio_manager.cpp/.h` - GPIO safety system
- `src/utils/logger.cpp/.h` - Logging infrastructure
- `src/utils/topic_builder.cpp/.h` - MQTT topic generation

### Configuration
- `src/services/config/storage_manager.cpp/.h` - NVS abstraction
- `src/services/config/config_manager.cpp/.h` - Configuration management
- `docs/NVS_KEYS.md` - NVS key documentation

### Communication
- `src/services/communication/wifi_manager.cpp/.h` - WiFi management
- `src/services/communication/mqtt_client.cpp/.h` - MQTT client
- `src/error_handling/circuit_breaker.cpp/.h` - Connection resilience

### Sensors
- `src/services/sensor/sensor_manager.cpp/.h` - Sensor orchestration
- `src/services/sensor/sensor_drivers/*` - Sensor implementations

### Actuators
- `src/services/actuator/actuator_manager.cpp/.h` - Actuator control
- `src/services/actuator/safety_controller.cpp/.h` - Safety interlocks
- `src/services/actuator/actuator_drivers/*` - Actuator implementations

### Error Handling
- `src/error_handling/error_tracker.cpp/.h` - Error tracking
- `src/error_handling/circuit_breaker.cpp/.h` - Failure recovery

### Models
- `src/models/sensor_types.h` - Sensor data structures
- `src/models/actuator_types.h` - Actuator data structures
- `src/models/system_types.h` - System-wide types
- `src/models/config_types.h` - Configuration structures
- `src/models/error_codes.h` - Error definitions

## Version Information

- **Firmware Version**: 4.0 (Phase 2)
- **Documentation Date**: November 2025
- **ESP32 Platform**: ESP32 WROOM / XIAO ESP32C3
- **Framework**: Arduino + PlatformIO

## Contributing to Documentation

When updating these flows:

1. Keep code snippets synchronized with actual implementation
2. Update line numbers when code changes
3. Maintain MQTT topic/payload examples
4. Document all NVS operations
5. Add timing/memory metrics when available
6. Update cross-references between flows

## Quick Reference

### Typical Boot Time
- **Minimum**: 2.5s (cached WiFi)
- **Typical**: 3-6s
- **Maximum**: 15s (WiFi reconnect timeout)

### MQTT Topics Overview
- Sensor data: `kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data`
- Actuator command: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/command`
- Actuator status: `kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/status`
- Config: `kaiser/{kaiser_id}/esp/{esp_id}/config`
- Heartbeat: `kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat`
- Emergency: `kaiser/broadcast/emergency`

### NVS Namespaces
- `wifi_config` - WiFi and MQTT connection settings
- `zone_config` - Kaiser and zone assignments
- `system_config` - ESP system configuration
- `sensor_config` - Sensor definitions
- `actuator_config` - Actuator definitions

### Memory Usage (Typical)
- Phase 1 (Core): ~60KB heap used
- Phase 2 (Communication): ~80KB heap used
- Phase 3 (Hardware): ~85KB heap used
- Phase 4+ (Sensors/Actuators): Variable based on configuration

## Support

For questions or issues with this documentation:

1. Check the specific flow document for detailed information
2. Review actual source code for latest implementation
3. Consult NVS_KEYS.md for storage operations
4. See MQTT_CLIENT_API.md for MQTT details
5. Review INTEGRATION_GUIDE.md for God-Kaiser integration

---

**Ready to explore?** Start with [Boot Sequence](01-boot-sequence.md) to understand how the system initializes, then follow the flow documents based on your area of interest.

