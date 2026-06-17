#!/usr/bin/env python3
"""
Interactive Testing Session - Automated Tests for Sensors and Actuators.

This script tests:
1. MockESP32Client functionality
2. DS18B20 Temperature Sensor
3. SHT31 Humidity/Temperature Sensor
4. Digital Actuators
5. PWM Actuators
6. Server API endpoints
"""

import sys
import time
from pathlib import Path

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tests.esp32.mocks.mock_esp32_client import MockESP32Client


def print_separator(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_mock_esp32_client():
    """Test MockESP32Client functionality."""
    print_separator("TEST 1: MockESP32Client Funktionalitaet")
    
    mock = MockESP32Client(esp_id="test-interactive-001")
    print(f"\n[OK] ESP32 Mock erstellt: {mock.esp_id}")
    
    # Test 1.1: DS18B20 Temperature Sensor
    print("\n--- 1.1 DS18B20 Temperature Sensor (GPIO 34) ---")
    mock.set_sensor_value(gpio=34, raw_value=23.5, sensor_type="DS18B20")
    response = mock.handle_command("sensor_read", {"gpio": 34})
    
    print(f"  Status: {response['status']}")
    print(f"  GPIO: {response.get('gpio', 'N/A')}")
    if "data" in response:
        data = response["data"]
        print(f"  Type: {data['type']}")
        print(f"  Raw Value: {data['raw_value']} C")
        print(f"  Timestamp: {data.get('timestamp', 'N/A')}")
    
    if response["status"] == "ok":
        print("  [PASS] DS18B20 read successful")
    else:
        print("  [FAIL] DS18B20 read failed")
    
    # Test 1.2: SHT31 Humidity Sensor
    print("\n--- 1.2 SHT31 Humidity Sensor (GPIO 35) ---")
    mock.set_sensor_value(gpio=35, raw_value=65.2, sensor_type="SHT31")
    response = mock.handle_command("sensor_read", {"gpio": 35})
    
    print(f"  Status: {response['status']}")
    if "data" in response:
        data = response["data"]
        print(f"  Type: {data['type']}")
        print(f"  Raw Value: {data['raw_value']} %RH")
    
    if response["status"] == "ok":
        print("  [PASS] SHT31 read successful")
    else:
        print("  [FAIL] SHT31 read failed")
    
    # Test 1.3: Digital Actuator (Pump)
    print("\n--- 1.3 Digital Actuator (GPIO 5 - Pump) ---")
    
    # Turn ON
    response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
    print(f"  Status: {response['status']}")
    print(f"  State after ON: {response.get('state', 'N/A')}")
    
    # Turn OFF
    response = mock.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})
    print(f"  State after OFF: {response.get('state', 'N/A')}")
    
    if response["status"] == "ok":
        print("  [PASS] Digital Actuator control successful")
    else:
        print("  [FAIL] Digital Actuator control failed")
    
    # Test 1.4: PWM Actuator (Motor)
    print("\n--- 1.4 PWM Actuator (GPIO 7 - Motor) ---")
    response = mock.handle_command("actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"})
    
    print(f"  Status: {response['status']}")
    print(f"  PWM Value: {response.get('pwm_value', 'N/A')} (75%)")
    print(f"  State: {response.get('state', 'N/A')}")
    
    if response["status"] == "ok" and response.get("pwm_value") == 0.75:
        print("  [PASS] PWM Actuator control successful")
    else:
        print("  [FAIL] PWM Actuator control failed")
    
    # Test 1.5: Check MQTT Messages
    print("\n--- 1.5 Published MQTT Messages ---")
    messages = mock.get_published_messages()
    print(f"  Total Messages: {len(messages)}")
    
    for i, msg in enumerate(messages[:5], 1):
        print(f"  [{i}] Topic: {msg['topic']}")
    
    if len(messages) > 0:
        print("  [PASS] MQTT messages published correctly")
    else:
        print("  [FAIL] No MQTT messages published")
    
    return mock


def test_sensor_processors():
    """Test Sensor Processor Libraries."""
    print_separator("TEST 2: Sensor Processor Libraries")
    
    from src.sensors.sensor_libraries.active.temperature import DS18B20Processor, SHT31TemperatureProcessor
    from src.sensors.sensor_libraries.active.humidity import SHT31HumidityProcessor
    
    # Test 2.1: DS18B20 Processing
    print("\n--- 2.1 DS18B20Processor ---")
    ds18b20 = DS18B20Processor()
    
    # Normal temperature
    result = ds18b20.process(raw_value=23.5)
    print(f"  Input: 23.5 C")
    print(f"  Output: {result.value} {result.unit}")
    print(f"  Quality: {result.quality}")
    
    if result.value == 23.5 and result.unit == "°C" and result.quality == "good":
        print("  [PASS] DS18B20 processing correct")
    else:
        print("  [FAIL] DS18B20 processing incorrect")
    
    # Fahrenheit conversion
    result_f = ds18b20.process(raw_value=0.0, params={"unit": "fahrenheit"})
    print(f"\n  Input: 0.0 C -> Fahrenheit")
    print(f"  Output: {result_f.value} {result_f.unit}")
    
    if result_f.value == 32.0 and result_f.unit == "°F":
        print("  [PASS] Fahrenheit conversion correct")
    else:
        print("  [FAIL] Fahrenheit conversion incorrect")
    
    # Test 2.2: SHT31 Temperature Processing
    print("\n--- 2.2 SHT31TemperatureProcessor ---")
    sht31_temp = SHT31TemperatureProcessor()
    
    result = sht31_temp.process(raw_value=22.3)
    print(f"  Input: 22.3 C")
    print(f"  Output: {result.value} {result.unit}")
    print(f"  Quality: {result.quality}")
    
    if result.unit == "°C" and result.quality == "good":
        print("  [PASS] SHT31 Temperature processing correct")
    else:
        print("  [FAIL] SHT31 Temperature processing incorrect")
    
    # Test 2.3: SHT31 Humidity Processing
    print("\n--- 2.3 SHT31HumidityProcessor ---")
    sht31_humidity = SHT31HumidityProcessor()
    
    result = sht31_humidity.process(raw_value=65.2)
    print(f"  Input: 65.2 %RH")
    print(f"  Output: {result.value} {result.unit}")
    print(f"  Quality: {result.quality}")
    
    if result.unit == "%RH" and result.quality == "good":
        print("  [PASS] SHT31 Humidity processing correct")
    else:
        print("  [FAIL] SHT31 Humidity processing incorrect")
    
    # Test condensation warning
    result_high = sht31_humidity.process(raw_value=96.5)
    print(f"\n  Input: 96.5 %RH (high humidity)")
    print(f"  Quality: {result_high.quality}")
    warnings = result_high.metadata.get("warnings", [])
    if warnings:
        print(f"  Warnings: {len(warnings)} warning(s)")
        print("  [PASS] Condensation warning triggered")
    else:
        print("  [FAIL] No condensation warning")


def test_server_api():
    """Test Server API endpoints."""
    print_separator("TEST 3: Server API Endpoints")
    
    import requests
    
    base_url = "http://localhost:8000"
    
    # Test 3.1: Health endpoint
    print("\n--- 3.1 Health Endpoint ---")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        data = response.json()
        print(f"  Status: {data['status']}")
        print(f"  Database: {data['database']['connected']}")
        print(f"  MQTT: {data['mqtt']['connected']}")
        
        if data["status"] == "healthy":
            print("  [PASS] Server is healthy")
        else:
            print("  [FAIL] Server unhealthy")
    except requests.exceptions.RequestException as e:
        print(f"  [SKIP] Server not running: {e}")
        return
    
    # Test 3.2: Root endpoint
    print("\n--- 3.2 Root Endpoint ---")
    try:
        response = requests.get(f"{base_url}/", timeout=5)
        data = response.json()
        print(f"  Service: {data['service']}")
        print(f"  Version: {data['version']}")
        print(f"  Status: {data['status']}")
        
        if data["status"] == "online":
            print("  [PASS] Server online")
    except requests.exceptions.RequestException as e:
        print(f"  [FAIL] Error: {e}")
    
    # Test 3.3: API Docs
    print("\n--- 3.3 Swagger API Docs ---")
    try:
        response = requests.get(f"{base_url}/docs", timeout=5)
        if response.status_code == 200:
            print(f"  Swagger UI available at: {base_url}/docs")
            print("  [PASS] API docs accessible")
        else:
            print(f"  [FAIL] Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"  [FAIL] Error: {e}")


def run_demo_sequence():
    """Run automated demo sequence like interactive_test_esp32.py."""
    print_separator("TEST 4: Demo Sequence (wie Automated Demo)")
    
    mock = MockESP32Client(esp_id="demo-esp-001")
    
    # Step 1: Add sensors
    print("\n--- Step 1: Adding sensors ---")
    mock.set_sensor_value(gpio=34, raw_value=21.5, sensor_type="DS18B20")
    print("  [OK] DS18B20 auf GPIO 34 (21.5 C)")
    
    mock.set_sensor_value(gpio=35, raw_value=55.0, sensor_type="SHT31")
    print("  [OK] SHT31 auf GPIO 35 (55.0 %RH)")
    
    # Step 2: Read sensors
    print("\n--- Step 2: Reading sensors ---")
    for gpio in [34, 35]:
        response = mock.handle_command("sensor_read", {"gpio": gpio})
        print(f"  GPIO {gpio}: {response['status']} - {response['data']['raw_value']}")
    
    # Step 3: Control actuator (ON/OFF)
    print("\n--- Step 3: Controlling actuator ---")
    response = mock.handle_command("actuator_set", {"gpio": 5, "value": 1, "mode": "digital"})
    print(f"  Pump ON: state={response['state']}")
    
    time.sleep(0.5)
    
    response = mock.handle_command("actuator_set", {"gpio": 5, "value": 0, "mode": "digital"})
    print(f"  Pump OFF: state={response['state']}")
    
    # Step 4: PWM control
    print("\n--- Step 4: PWM control ---")
    response = mock.handle_command("actuator_set", {"gpio": 7, "value": 0.75, "mode": "pwm"})
    print(f"  Motor PWM: {response['pwm_value']} (75%)")
    
    # Step 5: Message summary
    print("\n--- Step 5: Message summary ---")
    messages = mock.get_published_messages()
    print(f"  Total published messages: {len(messages)}")
    
    # Verify topics
    sensor_msgs = [m for m in messages if "/sensor/" in m["topic"]]
    actuator_msgs = [m for m in messages if "/actuator/" in m["topic"]]
    print(f"  - Sensor messages: {len(sensor_msgs)}")
    print(f"  - Actuator messages: {len(actuator_msgs)}")
    
    print("\n  [PASS] Demo sequence completed!")


def main():
    """Main entry point."""
    print("\n" + "#" * 60)
    print("#  INTERACTIVE TESTING SESSION")
    print("#  God-Kaiser Server - ESP32 Sensor/Actuator Testing")
    print("#" * 60)
    
    results = {
        "mock_client": False,
        "sensor_processors": False,
        "server_api": False,
        "demo_sequence": False
    }
    
    # Run all tests
    try:
        test_mock_esp32_client()
        results["mock_client"] = True
    except Exception as e:
        print(f"\n[ERROR] MockESP32Client test failed: {e}")
    
    try:
        test_sensor_processors()
        results["sensor_processors"] = True
    except Exception as e:
        print(f"\n[ERROR] Sensor Processor test failed: {e}")
    
    try:
        test_server_api()
        results["server_api"] = True
    except Exception as e:
        print(f"\n[ERROR] Server API test failed: {e}")
    
    try:
        run_demo_sequence()
        results["demo_sequence"] = True
    except Exception as e:
        print(f"\n[ERROR] Demo sequence failed: {e}")
    
    # Summary
    print_separator("TEST SUMMARY")
    passed = sum(results.values())
    total = len(results)
    
    for test, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {test}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  [SUCCESS] All tests passed!")
        return 0
    else:
        print("\n  [WARNING] Some tests failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

























