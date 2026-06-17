#!/usr/bin/env python3
"""
Hardware Validation Test Suite
Tests all 4 critical fixes: I2C validation, Input-Only protection, I2C pin protection, ESP model awareness
"""

import os
import requests
import json
from typing import Dict, Any

BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

# Test tracking
test_results = []
passed = 0
failed = 0
auth_token = None


def write_test_result(test_name: str, success: bool, expected: str, actual: str, details: str = ""):
    global passed, failed
    status = "[PASS]" if success else "[FAIL]"
    print(f"\n{status} {test_name}")

    if not success:
        print(f"  Expected: {expected}")
        print(f"  Actual: {actual}")
        if details:
            print(f"  Details: {details}")

    test_results.append({
        "test_name": test_name,
        "passed": success,
        "expected": expected,
        "actual": actual,
        "details": details
    })

    if success:
        passed += 1
    else:
        failed += 1


def make_request(method: str, url: str, data: Dict = None, require_auth: bool = True) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}

    if require_auth and auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers)
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        return {
            "status_code": response.status_code,
            "content": response.json() if response.text else {},
            "success": True
        }
    except requests.exceptions.RequestException as e:
        return {
            "status_code": getattr(e.response, 'status_code', 0),
            "content": e.response.json() if hasattr(e.response, 'json') else str(e),
            "success": False
        }


def get_auth_token(username: str = "admin", password: str = os.environ.get("E2E_TEST_PASSWORD", "")) -> bool:
    global auth_token
    print(f"Authenticating as {username}...")

    # Try to login
    login_result = make_request("POST", f"{API_BASE}/auth/login", {
        "username": username,
        "password": password
    }, require_auth=False)

    if login_result["status_code"] == 200 and "access_token" in login_result["content"]:
        auth_token = login_result["content"]["access_token"]
        print("[OK] Authentication successful")
        return True

    # If login fails, try to register
    print("Login failed, attempting to register user...")
    register_result = make_request("POST", f"{API_BASE}/auth/register", {
        "username": username,
        "email": f"{username}@test.local",
        "password": password,
        "full_name": "Test User"
    }, require_auth=False)

    if register_result["status_code"] == 201:
        # Try login again
        login_result = make_request("POST", f"{API_BASE}/auth/login", {
            "username": username,
            "password": password
        }, require_auth=False)

        if login_result["status_code"] == 200 and "access_token" in login_result["content"]:
            auth_token = login_result["content"]["access_token"]
            print("[OK] User registered and authenticated")
            return True

    print(f"[ERROR] Authentication failed. Status: {login_result['status_code']}")
    return False


def main():
    print("=" * 60)
    print("Hardware Validation Test Suite")
    print("17 Test Cases - 4 Critical Fixes")
    print("=" * 60)

    # Step 1: Authenticate
    if not get_auth_token():
        print("\n[ERROR] Cannot proceed without authentication")
        return

    # Step 2: Register a test ESP device
    print("\n--- Registering Test ESP Device ---")
    esp_result = make_request("POST", f"{API_BASE}/esp/register", {
        "esp_id": "TEST_HW_VAL",
        "board_model": "ESP32_DEV"
    })

    if esp_result["status_code"] not in [200, 201]:
        # Try to get existing device
        esp_result = make_request("GET", f"{API_BASE}/esp/devices/TEST_HW_VAL")
        if esp_result["status_code"] != 200:
            print(f"[ERROR] Cannot register/retrieve ESP device: {esp_result['status_code']}")
            return

    print("[OK] Test ESP device ready: TEST_HW_VAL")

    # Test Section 2.1: I2C Address Validation
    print("\n" + "=" * 60)
    print("Section 2.1: I2C Address Validation")
    print("=" * 60)

    # Test 1: Negative I2C address
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "sht31",
        "sensor_name": "Test Invalid I2C Negative",
        "interface_type": "i2c",
        "i2c_address": -1
    })
    write_test_result(
        "2.1.1 - Reject negative I2C address (-1)",
        test_result["status_code"] == 400,
        "400 Bad Request (validation error)",
        f"{test_result['status_code']} - {json.dumps(test_result['content'])[:100]}",
        "I2C address must be positive"
    )

    # Test 2: Reserved I2C address 0x00
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "sht31",
        "sensor_name": "Test Reserved 0x00",
        "interface_type": "i2c",
        "i2c_address": 0
    })
    write_test_result(
        "2.1.2 - Reject reserved I2C address 0x00",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "0x00 is reserved for general call"
    )

    # Test 3: Reserved I2C address 0x78-0x7F
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "sht31",
        "sensor_name": "Test Reserved 0x78",
        "interface_type": "i2c",
        "i2c_address": 0x78
    })
    write_test_result(
        "2.1.3 - Reject reserved I2C address 0x78 (10-bit range)",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "0x78-0x7F reserved for 10-bit addressing"
    )

    # Test 4: Valid I2C address 0x44
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "sht31",
        "sensor_name": "Test Valid I2C",
        "interface_type": "i2c",
        "i2c_address": 0x44
    })
    write_test_result(
        "2.1.4 - Accept valid I2C address 0x44",
        test_result["status_code"] in [200, 201],
        "200/201 (success)",
        f"{test_result['status_code']}",
        "0x44 is valid SHT31 address"
    )

    # Test Section 2.2: Input-Only Pin Protection
    print("\n" + "=" * 60)
    print("Section 2.2: Input-Only Pin Protection (ESP32)")
    print("=" * 60)

    # Test 5: GPIO 34 (input-only) as sensor - should ACCEPT
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 34,
        "sensor_type": "generic_analog",
        "sensor_name": "Test GPIO34 Sensor",
        "interface_type": "analog"
    })
    write_test_result(
        "2.2.1 - Accept GPIO 34 (input-only) as sensor",
        test_result["status_code"] in [200, 201],
        "200/201 (success)",
        f"{test_result['status_code']}",
        "GPIO 34 is input-only, valid for sensors"
    )

    # Test 6: GPIO 34 (input-only) as actuator - should REJECT
    test_result = make_request("POST", f"{API_BASE}/actuators/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 34,
        "actuator_type": "relay",
        "actuator_name": "Test GPIO34 Actuator"
    })
    write_test_result(
        "2.2.2 - Reject GPIO 34 (input-only) as actuator",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "GPIO 34 is input-only, cannot be used for actuators"
    )

    # Test 7: GPIO 27 (bidirectional) as actuator - should ACCEPT
    test_result = make_request("POST", f"{API_BASE}/actuators/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 27,
        "actuator_type": "relay",
        "actuator_name": "Test GPIO27 Actuator"
    })
    write_test_result(
        "2.2.3 - Accept GPIO 27 (bidirectional) as actuator",
        test_result["status_code"] in [200, 201],
        "200/201 (success)",
        f"{test_result['status_code']}",
        "GPIO 27 is bidirectional, valid for actuators"
    )

    # Test Section 2.3: I2C Pin Protection
    print("\n" + "=" * 60)
    print("Section 2.3: I2C Pin Protection")
    print("=" * 60)

    # Test 8: GPIO 21 (SDA) with interface_type=i2c - should ACCEPT
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "sht31",
        "sensor_name": "Test I2C on SDA",
        "interface_type": "i2c",
        "i2c_address": 0x45
    })
    write_test_result(
        "2.3.1 - Accept GPIO 21 (SDA) for I2C sensor",
        test_result["status_code"] in [200, 201],
        "200/201 (success)",
        f"{test_result['status_code']}",
        "GPIO 21 is I2C SDA, valid for I2C sensors"
    )

    # Test 9: GPIO 21 (SDA) with interface_type=digital - should REJECT
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 21,
        "sensor_type": "flow",
        "sensor_name": "Test Digital on SDA",
        "interface_type": "digital"
    })
    write_test_result(
        "2.3.2 - Reject GPIO 21 (SDA) for non-I2C sensor",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "GPIO 21 is I2C SDA, cannot be used for digital sensors"
    )

    # Test 10: GPIO 22 (SCL) with actuator - should REJECT
    test_result = make_request("POST", f"{API_BASE}/actuators/", {
        "esp_id": "TEST_HW_VAL",
        "gpio": 22,
        "actuator_type": "relay",
        "actuator_name": "Test Actuator on SCL"
    })
    write_test_result(
        "2.3.3 - Reject GPIO 22 (SCL) for actuator",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "GPIO 22 is I2C SCL, cannot be used for actuators"
    )

    # Test Section 2.4: ESP Model Awareness
    print("\n" + "=" * 60)
    print("Section 2.4: ESP Model Awareness")
    print("=" * 60)

    # Register XIAO ESP32-C3 device
    xiao_result = make_request("POST", f"{API_BASE}/esp/register", {
        "esp_id": "TEST_XIAO",
        "board_model": "XIAO_ESP32C3"
    })
    if xiao_result["status_code"] not in [200, 201]:
        xiao_result = make_request("GET", f"{API_BASE}/esp/devices/TEST_XIAO")

    # Test 11: GPIO 34 on XIAO (doesn't exist) - should REJECT
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_XIAO",
        "gpio": 34,
        "sensor_type": "generic_analog",
        "sensor_name": "Test XIAO GPIO34"
    })
    write_test_result(
        "2.4.1 - Reject GPIO 34 on XIAO ESP32-C3 (doesn't exist)",
        test_result["status_code"] == 400,
        "400 Bad Request",
        f"{test_result['status_code']}",
        "GPIO 34 doesn't exist on XIAO ESP32-C3"
    )

    # Test 12: GPIO 2 on XIAO (valid) - should ACCEPT
    test_result = make_request("POST", f"{API_BASE}/sensors/", {
        "esp_id": "TEST_XIAO",
        "gpio": 2,
        "sensor_type": "generic_analog",
        "sensor_name": "Test XIAO GPIO2"
    })
    write_test_result(
        "2.4.2 - Accept GPIO 2 on XIAO ESP32-C3 (valid)",
        test_result["status_code"] in [200, 201],
        "200/201 (success)",
        f"{test_result['status_code']}",
        "GPIO 2 is valid on XIAO ESP32-C3"
    )

    # Test 13: Unknown board model - should use default pins
    unknown_result = make_request("POST", f"{API_BASE}/esp/register", {
        "esp_id": "TEST_UNKNOWN",
        "board_model": "UNKNOWN_MODEL"
    })
    if unknown_result["status_code"] in [200, 201]:
        test_result = make_request("POST", f"{API_BASE}/sensors/", {
            "esp_id": "TEST_UNKNOWN",
            "gpio": 34,
            "sensor_type": "generic_analog",
            "sensor_name": "Test Unknown GPIO34"
        })
        write_test_result(
            "2.4.3 - Unknown board model - use default ESP32 pins",
            test_result["status_code"] in [200, 201],
            "200/201 (success, defaults to ESP32)",
            f"{test_result['status_code']}",
            "Unknown board_model defaults to ESP32 pinout"
        )

    # Print Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total: {passed + failed} tests")
    print(f"[PASS] Passed: {passed}")
    print(f"[FAIL] Failed: {failed}")
    print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")

    if failed == 0:
        print("\n[SUCCESS] All tests passed! Hardware validation is working correctly.")
    else:
        print(f"\n[WARNING] {failed} test(s) failed. Review the output above for details.")


if __name__ == "__main__":
    main()
