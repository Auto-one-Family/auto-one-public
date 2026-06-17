#!/usr/bin/env python3
"""Run pytest tests in batches with progress reporting"""

import subprocess
import sys
from pathlib import Path

def run_test_file(test_file, desc):
    """Run a single test file and return result"""
    print(f"\n{'='*60}")
    print(f"Testing: {desc}")
    print(f"File: {test_file}")
    print('='*60)
    
    cmd = [
        sys.executable, "-m", "pytest",
        f"tests/esp32/{test_file}",
        "--no-cov", "-q", "--tb=no",
        "-m", "not hardware"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
    
    # Parse output for pass/fail count
    output = result.stdout + result.stderr
    print(output)
    
    if result.returncode == 0:
        print(f"[PASS] {desc}")
        return True
    else:
        print(f"[FAIL] {desc} (see output above)")
        return False

def main():
    print("="*60)
    print("ESP32 Test Suite - Batch Runner")
    print("="*60)
    
    tests = [
        ("test_communication.py", "Communication Tests (MQTT ping/pong)"),
        ("test_actuator.py", "Actuator Control Tests"),
        ("test_sensor.py", "Sensor Reading Tests"),
        ("test_infrastructure.py", "Infrastructure Tests"),
    ]
    
    results = {}
    for test_file, desc in tests:
        results[desc] = run_test_file(test_file, desc)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for desc, success in results.items():
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status}  {desc}")
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {passed}/{total} test files passed")
    print('='*60)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())

























