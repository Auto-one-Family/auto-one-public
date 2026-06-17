# MQTT Test Protocol for ESP32 Orchestration

> **Purpose:** Define MQTT topics and message formats for server-orchestrated ESP32 testing

**Version:** 1.0
**Date:** 2025-11-26

---

## Overview

Server-orchestrated tests allow God-Kaiser to test ESP32 devices remotely via MQTT commands.
This enables:
- ✅ Testing without physical access to devices
- ✅ Automated test suites (pytest) for ESP32 functionality
- ✅ CI/CD integration without hardware dependencies (using MockESP32Client)
- ✅ Real hardware verification for integration tests

---

## Design-Prinzip: Production-Identical Topics

Die Test-Orchestrierung verwendet **bewusst** die echten MQTT-Topics aus der Production-Spec 
([`El Trabajante/docs/Mqtt_Protocoll.md`](../../El Trabajante/docs/Mqtt_Protocoll.md)).

**Rationale:**
- Tests müssen gegen Mock-Clients UND echte Hardware laufen
- Pre-Production-Validation erfordert identische Topic-Struktur
- Cross-ESP-Tests benötigen authentisches Message-Routing
- Nahtloser Übergang: CI/CD → Staging → Production

Dies ermöglicht:
- Nahtlosen Übergang von Mock-Tests → Real-Hardware-Tests
- Validierung der echten MQTT-Message-Routing-Logik
- Cross-ESP-Tests mit authentischer Broker-Kommunikation

**Keine separaten Test-Topics:** Kein `kaiser/test/...` - nur Production-Topics!

---

## Topic Schema

### Test Commands (Server → ESP32)

```
kaiser/god/esp/{esp_id}/test/command
```

**Purpose:** Server sends test commands to ESP32 devices

**Payload Format (JSON):**
```json
{
  "test_id": "unique-test-identifier",
  "command": "ping|actuator_set|actuator_get|sensor_read|config_get|config_set|emergency_stop|reset",
  "params": {
    ... command-specific parameters ...
  },
  "timestamp": 1700000000.0
}
```

### Test Responses (ESP32 → Server)

```
kaiser/god/esp/{esp_id}/test/response
```

**Purpose:** ESP32 responds to test commands

**Payload Format (JSON):**
```json
{
  "test_id": "unique-test-identifier",
  "status": "ok|error",
  "command": "command_name",
  "data": {
    ... response data ...
  },
  "error": "error message (if status=error)",
  "timestamp": 1700000000.0
}
```

---

## Command Specifications

### 1. Ping Command

**Purpose:** Test basic MQTT connectivity and response time

**Command Payload:**
```json
{
  "test_id": "ping-001",
  "command": "ping",
  "params": {},
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "ping-001",
  "status": "ok",
  "command": "pong",
  "data": {
    "esp_id": "esp32-001",
    "uptime": 123456.78
  },
  "timestamp": 1700000000.1
}
```

**Test Criteria:**
- Response time < 500ms
- Status == "ok"
- Uptime > 0

---

### 2. Actuator Set Command

**Purpose:** Control actuator (pump, valve, PWM motor)

**Command Payload:**
```json
{
  "test_id": "actuator-set-001",
  "command": "actuator_set",
  "params": {
    "gpio": 5,
    "value": 1,          // 0|1 for digital, 0.0-1.0 for PWM
    "mode": "digital"    // "digital"|"pwm"
  },
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "actuator-set-001",
  "status": "ok",
  "command": "actuator_set",
  "data": {
    "gpio": 5,
    "state": true,
    "pwm_value": 1.0,
    "timestamp": 1700000000.1
  },
  "timestamp": 1700000000.1
}
```

**Side Effect:** ESP32 publishes actuator status to standard topic:
```
kaiser/god/esp/{esp_id}/actuator/{gpio}/status
```

**Test Criteria:**
- Response status == "ok"
- Actuator state matches commanded value
- Status message published to standard topic

---

### 3. Actuator Get Command

**Purpose:** Query current actuator state

**Command Payload:**
```json
{
  "test_id": "actuator-get-001",
  "command": "actuator_get",
  "params": {
    "gpio": 5    // Optional: omit to get all actuators
  },
  "timestamp": 1700000000.0
}
```

**Response Payload (single actuator):**
```json
{
  "test_id": "actuator-get-001",
  "status": "ok",
  "command": "actuator_get",
  "data": {
    "gpio": 5,
    "type": "pump",
    "state": true,
    "pwm_value": 1.0,
    "last_command": "set_digital"
  },
  "timestamp": 1700000000.1
}
```

**Response Payload (all actuators):**
```json
{
  "test_id": "actuator-get-002",
  "status": "ok",
  "command": "actuator_get",
  "data": {
    "actuators": {
      "5": { "type": "pump", "state": true, "pwm_value": 1.0 },
      "6": { "type": "valve", "state": false, "pwm_value": 0.0 }
    }
  },
  "timestamp": 1700000000.1
}
```

---

### 4. Sensor Read Command

**Purpose:** Read sensor value (RAW or processed)

**Command Payload:**
```json
{
  "test_id": "sensor-read-001",
  "command": "sensor_read",
  "params": {
    "gpio": 34
  },
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "sensor-read-001",
  "status": "ok",
  "command": "sensor_read",
  "data": {
    "gpio": 34,
    "type": "analog",
    "raw_value": 2048.0,
    "processed_value": 45.2,    // Optional: null if not processed
    "timestamp": 1700000000.1
  },
  "timestamp": 1700000000.1
}
```

**Side Effect:** ESP32 publishes sensor data to standard topic:
```
kaiser/god/esp/{esp_id}/sensor/{gpio}/data
```

**Test Criteria:**
- Response status == "ok"
- Raw value in valid range (0-4095 for ADC)
- Sensor data published to standard topic

---

### 5. Config Get Command

**Purpose:** Query ESP32 configuration

**Command Payload:**
```json
{
  "test_id": "config-get-001",
  "command": "config_get",
  "params": {
    "key": "wifi"    // Optional: omit to get all config
  },
  "timestamp": 1700000000.0
}
```

**Response Payload (specific key):**
```json
{
  "test_id": "config-get-001",
  "status": "ok",
  "command": "config_get",
  "data": {
    "key": "wifi",
    "value": {
      "ssid": "MyNetwork",
      "connected": true,
      "rssi": -45
    }
  },
  "timestamp": 1700000000.1
}
```

**Response Payload (all config):**
```json
{
  "test_id": "config-get-002",
  "status": "ok",
  "command": "config_get",
  "data": {
    "config": {
      "wifi": { "ssid": "MyNetwork", "connected": true },
      "zone": { "id": "zone-001", "name": "Greenhouse 1" },
      "system": { "version": "1.0.0", "uptime": 123456 }
    }
  },
  "timestamp": 1700000000.1
}
```

---

### 6. Config Set Command

**Purpose:** Update ESP32 configuration (MOCK ONLY!)

**⚠️ WARNING:** This command should ONLY be used with MockESP32Client!
**DO NOT** send to real devices during tests (read-only tests only!)

**Command Payload:**
```json
{
  "test_id": "config-set-001",
  "command": "config_set",
  "params": {
    "key": "zone",
    "value": {
      "id": "test-zone-001",
      "name": "Test Zone"
    }
  },
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "config-set-001",
  "status": "ok",
  "command": "config_set",
  "data": {
    "key": "zone",
    "value": {
      "id": "test-zone-001",
      "name": "Test Zone"
    }
  },
  "timestamp": 1700000000.1
}
```

---

### 7. Emergency Stop Command

**Purpose:** Stop all actuators immediately

**Command Payload:**
```json
{
  "test_id": "emergency-stop-001",
  "command": "emergency_stop",
  "params": {},
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "emergency-stop-001",
  "status": "ok",
  "command": "emergency_stop",
  "data": {
    "stopped_actuators": [5, 6, 7]
  },
  "timestamp": 1700000000.1
}
```

**Side Effect:** ESP32 publishes emergency stop to standard topic:
```
kaiser/god/esp/{esp_id}/actuator/emergency
```

**Test Criteria:**
- All actuators set to OFF
- Emergency status published

---

### 8. Reset Command

**Purpose:** Reset test state (MOCK ONLY!)

**⚠️ WARNING:** This command is ONLY for MockESP32Client!
Real devices should NOT implement this command.

**Command Payload:**
```json
{
  "test_id": "reset-001",
  "command": "reset",
  "params": {},
  "timestamp": 1700000000.0
}
```

**Response Payload:**
```json
{
  "test_id": "reset-001",
  "status": "ok",
  "command": "reset",
  "timestamp": 1700000000.1
}
```

---

## QoS Levels

| Topic | QoS | Reason |
|-------|-----|--------|
| `test/command` | QoS 1 | At least once delivery (commands must arrive) |
| `test/response` | QoS 1 | At least once delivery (responses must arrive) |

---

## Error Handling

**Error Response Format:**
```json
{
  "test_id": "test-001",
  "status": "error",
  "command": "actuator_set",
  "error": "GPIO 99 not available",
  "timestamp": 1700000000.1
}
```

**Common Error Codes:**
- `"Unknown command"` - Command type not recognized
- `"Missing parameter: <param>"` - Required parameter missing
- `"GPIO not available"` - GPIO already in use or invalid
- `"Actuator not found"` - No actuator configured on specified GPIO
- `"Sensor not found"` - No sensor configured on specified GPIO
- `"Timeout"` - Command execution timed out

---

## Test Example (Pytest)

```python
def test_actuator_control(mock_esp32):
    """Test actuator control via MQTT commands."""
    # Send command
    response = mock_esp32.handle_command("actuator_set", {
        "gpio": 5,
        "value": 1,
        "mode": "digital"
    })

    # Verify response
    assert response["status"] == "ok"
    assert response["data"]["gpio"] == 5
    assert response["data"]["state"] is True

    # Verify published message
    messages = mock_esp32.get_published_messages()
    assert len(messages) == 1
    assert messages[0]["topic"] == "kaiser/god/esp/test-esp-001/actuator/5/status"

    # Verify actuator state
    actuator = mock_esp32.get_actuator_state(5)
    assert actuator.state is True
    assert actuator.pwm_value == 1.0
```

---

## Implementation Checklist

**Server-side (God-Kaiser):**
- ✅ MockESP32Client implements all commands
- ✅ Pytest fixtures provide mock_esp32
- ⏳ Real MQTT client for real_esp32 (TODO)
- ⏳ Test orchestration helpers (TODO)

**ESP32-side (El Trabajante):**
- ⏳ MQTT handler for `test/command` topic (OPTIONAL)
- ⏳ Test command dispatcher (OPTIONAL)
- ⏳ Response publisher to `test/response` (OPTIONAL)

**Note:** ESP32-side implementation is OPTIONAL if using existing topics:
- Actuator commands can use existing `actuator/{gpio}/command` topic
- Sensor reads can trigger existing sensor reading loop
- Config can use existing config MQTT handlers

---

**Last Updated:** 2025-11-26
**Version:** 1.0
