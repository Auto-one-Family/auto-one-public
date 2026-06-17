#!/usr/bin/env python3
"""
Wokwi Test Runner for AutomationOne
Runs Wokwi simulation scenarios and collects results.

Features:
- Scenario discovery via glob patterns
- Sequential or parallel execution
- Result parsing (PASS/FAIL/TIMEOUT)
- JSON output for CI integration
- Log output to logs/wokwi/

Usage:
  python scripts/run-wokwi-tests.py                    # Run local baseline scenarios
  python scripts/run-wokwi-tests.py --category 01-boot # Run specific category
  python scripts/run-wokwi-tests.py --scenario boot_full # Run single scenario
  python scripts/run-wokwi-tests.py --parallel 2 --allow-unsafe-parallel
  python scripts/run-wokwi-tests.py --list             # List available scenarios

Requirements:
- WOKWI_CLI_TOKEN environment variable set
- wokwi-cli installed and in PATH
- Firmware built: pio run -e wokwi_simulation

Note:
- This script is the local runner entrypoint.
- CI workflow has its own orchestrated execution path.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

# Load .env for local development (WOKWI_CLI_TOKEN etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# Optional: PyYAML for parsing mqtt_injections from scenario files
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Configuration
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
TRABAJANTE_DIR = PROJECT_DIR / "El Trabajante"
SCENARIOS_DIR = TRABAJANTE_DIR / "tests" / "wokwi" / "scenarios"
LOG_DIR = PROJECT_DIR / "logs" / "wokwi"
MQTT_LOG_DIR = LOG_DIR / "mqtt"
SERIAL_LOG_DIR = LOG_DIR / "serial"

# MQTT Container name for traffic capture
MQTT_CONTAINER_NAME = "automationone-mqtt"

# Active CI scenario categories (others are blocked by Wokwi limitations)
# Stufe 1+2 Expansion: Added 08-onewire, 09-hardware, 09-pwm, 10-nvs, gpio
ACTIVE_CATEGORIES = [
    "01-boot",
    "02-sensor",
    "03-actuator",
    "04-zone",
    "05-emergency",
    "06-config",
    "07-combined",
    # Stufe 1: Quick Wins (passive tests, no hardware changes needed)
    "08-onewire",    # 29 scenarios - DS18B20 already in diagram.json
    "09-hardware",   # 9 scenarios - all passive Serial-Monitor tests
    # Stufe 2: Extended Tests
    "09-pwm",        # 18 scenarios (15 passive, 3 MQTT-injection handled separately)
    "10-nvs",        # 40 scenarios (35 CI-fähig, 5 persistence require reboot)
    "gpio",          # 24 scenarios - all passive
    # Note: 08-i2c excluded - requires BMP280 Custom-Chip (Stufe 4)
]

# Scenarios to skip - Wokwi limitations prevent testing these
# Key: category, Value: list of scenario stems to skip (without .yaml)
SKIP_SCENARIOS = {
    # NVS persistence tests require ESP32 reboot - not supported in Wokwi
    "10-nvs": [
        "nvs_pers_bootcount",
        "nvs_pers_reboot",
        "nvs_pers_sensor",
        "nvs_pers_wifi",
        "nvs_pers_zone",
    ],
    # PWM MQTT-Injection tests - now enabled via set-control steps (Phase 3.1)
    # Previously required external MQTT injection, now use Wokwi MQTT part injection
    "09-pwm": [],
}

# Timeout mapping by category (milliseconds)
# Optimized per Verbesserungsvorschlag 5.7 - differentiated timeouts
CATEGORY_TIMEOUTS = {
    "01-boot": {"default": 90000, "boot_safe_mode": 45000},
    "02-sensor": {"default": 90000},
    "03-actuator": {"default": 90000, "actuator_binary_full_flow": 120000,
                   "actuator_pwm_full_flow": 120000, "actuator_timeout_e2e": 120000},
    "04-zone": {"default": 90000},
    "05-emergency": {"default": 90000, "emergency_stop_full_flow": 120000},
    "06-config": {"default": 90000},
    "07-combined": {"default": 120000, "multi_device_parallel": 180000},
    # Stufe 1: New categories
    "08-onewire": {
        "default": 60000,
        "onewire_full_flow_ds18b20": 120000,
        "onewire_temperature_flow": 90000,
        "onewire_sensor_config_ds18b20": 90000,
    },
    "09-hardware": {"default": 45000},  # Pure Serial-Monitor tests are fast
    # Stufe 2: Extended categories
    "09-pwm": {
        "default": 60000,
        "pwm_integration_full_flow": 120000,
        "pwm_duty_percent_50": 120000,
        "pwm_e2e_dimmer": 150000,
        "pwm_e2e_fan_control": 150000,
    },
    "10-nvs": {
        "default": 60000,
        "nvs_cap_many_keys": 90000,
        "nvs_int_configmanager": 90000,
    },
    "gpio": {
        "default": 60000,
        "gpio_integration_actuator": 90000,
        "gpio_integration_sensor": 90000,
        "gpio_integration_emergency": 90000,
    },
}

# Retry configuration for flaky tests
MAX_RETRIES = 2  # 3 attempts total (1 initial + 2 retries)
RETRY_DELAY_SECONDS = 5
RETRY_ON_EXIT_CODES = {42, 1, -1}  # 42=Wokwi timeout, 1=general error, -1=system timeout

# Reports directory
REPORTS_DIR = LOG_DIR / "reports"
SAFE_PARALLEL_DEFAULT = 1


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class TestResult:
    scenario_name: str
    category: str
    status: TestStatus
    duration_ms: int
    exit_code: int
    output_lines: int
    error_message: Optional[str] = None
    log_file: Optional[str] = None
    serial_log_file: Optional[str] = None
    mqtt_log_file: Optional[str] = None
    attempts: int = 1
    retried: bool = False

    def to_dict(self) -> dict:
        result = asdict(self)
        result["status"] = self.status.value
        return result


async def check_mqtt_container_running() -> bool:
    """Check if MQTT container is running."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", "inspect", "-f", "{{.State.Running}}", MQTT_CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        return stdout.decode().strip() == "true"
    except Exception:
        return False


async def start_mqtt_capture(category: str, scenario_name: str) -> Optional[tuple[asyncio.subprocess.Process, Path]]:
    """Start MQTT traffic capture for a scenario.

    Args:
        category: Test category (e.g., '01-boot')
        scenario_name: Scenario name (e.g., 'boot_full')

    Returns:
        Tuple of (process, log_file_path) or None if container not running
    """
    # Check if MQTT container is running
    if not await check_mqtt_container_running():
        return None

    # Create log directory
    mqtt_cat_dir = MQTT_LOG_DIR / category
    mqtt_cat_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = mqtt_cat_dir / f"{scenario_name}_{timestamp}.log"

    try:
        # Open log file for writing
        log_handle = open(log_file, "w", encoding="utf-8")
        log_handle.write(f"# MQTT Traffic Capture - {scenario_name}\n")
        log_handle.write(f"# Category: {category}\n")
        log_handle.write(f"# Started: {datetime.now().isoformat()}\n")
        log_handle.write("# " + "=" * 57 + "\n")
        log_handle.flush()

        # Start mosquitto_sub via docker exec
        process = await asyncio.create_subprocess_exec(
            "docker", "exec", MQTT_CONTAINER_NAME,
            "mosquitto_sub", "-v", "#",
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT
        )

        # Store file handle on process for cleanup
        process._log_handle = log_handle  # type: ignore
        process._log_file = log_file  # type: ignore

        return process, log_file

    except Exception as e:
        print(f"  [WARN] MQTT capture failed: {e}")
        return None


async def stop_mqtt_capture(mqtt_data: Optional[tuple[asyncio.subprocess.Process, Path]]) -> Optional[str]:
    """Stop MQTT traffic capture.

    Args:
        mqtt_data: Tuple from start_mqtt_capture or None

    Returns:
        Relative path to log file or None
    """
    if mqtt_data is None:
        return None

    process, log_file = mqtt_data

    try:
        # Terminate the process
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

        # Close file handle
        if hasattr(process, "_log_handle"):
            log_handle = process._log_handle  # type: ignore
            log_handle.write(f"\n# Stopped: {datetime.now().isoformat()}\n")
            log_handle.close()

        return str(log_file.relative_to(PROJECT_DIR))

    except Exception as e:
        print(f"  [WARN] MQTT capture stop failed: {e}")
        return None


class WokwiTestRunner:
    def __init__(self, parallel: int = 1, verbose: bool = False,
                 build_first: bool = False, mqtt_capture: bool = True,
                 retries: int = MAX_RETRIES, no_retry: bool = False,
                 allow_unsafe_parallel: bool = False):
        self.parallel = parallel
        self.verbose = verbose
        self.build_first = build_first
        self.mqtt_capture = mqtt_capture
        self.retries = 0 if no_retry else retries
        self.allow_unsafe_parallel = allow_unsafe_parallel
        self.results: list[TestResult] = []
        self.start_time: Optional[datetime] = None
        self.retry_count = 0  # Track total retries for summary

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met."""
        errors = []

        # G09 hardening: avoid unsafe topic collisions by default.
        if self.parallel > SAFE_PARALLEL_DEFAULT and not self.allow_unsafe_parallel:
            errors.append(
                f"Parallel={self.parallel} blocked (default safety mode is parallel={SAFE_PARALLEL_DEFAULT})"
            )
            errors.append("  Use --allow-unsafe-parallel only with isolated ESP IDs/topics")

        # Check WOKWI_CLI_TOKEN
        if not os.environ.get("WOKWI_CLI_TOKEN"):
            errors.append("WOKWI_CLI_TOKEN environment variable not set")
            errors.append("  Get token from: https://wokwi.com/dashboard/ci")
            errors.append("  Set with: setx WOKWI_CLI_TOKEN \"your_token\"")

        # Check wokwi-cli
        try:
            subprocess.run(["wokwi-cli", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            errors.append("wokwi-cli not found in PATH")
            errors.append("  Install with: curl -L wokwi.com/ci/install.sh | sh")

        # Check scenarios directory
        if not SCENARIOS_DIR.exists():
            errors.append(f"Scenarios directory not found: {SCENARIOS_DIR}")

        # Check firmware
        firmware_path = TRABAJANTE_DIR / ".pio" / "build" / "wokwi_simulation" / "firmware.bin"
        if not firmware_path.exists() and not self.build_first:
            errors.append(f"Firmware not built: {firmware_path}")
            errors.append("  Build with: make wokwi-build")
            errors.append("  Or run with --build flag")

        if errors:
            print("[ERROR] Prerequisites not met:")
            for error in errors:
                print(f"  {error}")
            return False

        return True

    def build_firmware(self) -> bool:
        """Build the Wokwi firmware."""
        print("\n[BUILD] Building Wokwi firmware...")
        try:
            result = subprocess.run(
                ["pio", "run", "-e", "wokwi_simulation"],
                cwd=TRABAJANTE_DIR,
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                print(f"[ERROR] Build failed: {result.stderr[:500]}")
                return False
            print("[BUILD] Firmware built successfully")
            return True
        except subprocess.TimeoutExpired:
            print("[ERROR] Build timeout (>5 minutes)")
            return False
        except Exception as e:
            print(f"[ERROR] Build error: {e}")
            return False

    def discover_scenarios(self, category: Optional[str] = None,
                          scenario_name: Optional[str] = None,
                          include_skipped: bool = False) -> list[Path]:
        """Discover available test scenarios.

        Args:
            category: Filter by specific category
            scenario_name: Filter by scenario name (partial match)
            include_skipped: If True, include scenarios from SKIP_SCENARIOS

        Returns:
            List of scenario file paths
        """
        scenarios = []

        if scenario_name:
            # Find specific scenario
            for cat_dir in SCENARIOS_DIR.iterdir():
                if cat_dir.is_dir():
                    for yaml_file in cat_dir.glob("*.yaml"):
                        if scenario_name in yaml_file.stem:
                            scenarios.append(yaml_file)
            return scenarios

        categories = [category] if category else ACTIVE_CATEGORIES

        for cat in categories:
            cat_dir = SCENARIOS_DIR / cat
            if cat_dir.exists():
                # Get skip list for this category
                skip_list = SKIP_SCENARIOS.get(cat, []) if not include_skipped else []

                for yaml_file in sorted(cat_dir.glob("*.yaml")):
                    # Check if scenario should be skipped
                    if yaml_file.stem in skip_list:
                        if self.verbose:
                            print(f"  [SKIP] {yaml_file.stem} (in SKIP_SCENARIOS)")
                        continue
                    scenarios.append(yaml_file)

        return scenarios

    def get_timeout(self, scenario_path: Path) -> int:
        """Get timeout for a scenario in milliseconds."""
        category = scenario_path.parent.name
        scenario_name = scenario_path.stem

        cat_timeouts = CATEGORY_TIMEOUTS.get(category, {"default": 90000})
        return cat_timeouts.get(scenario_name, cat_timeouts.get("default", 90000))

    async def run_scenario(self, scenario_path: Path) -> TestResult:
        """Run a single Wokwi scenario with MQTT capture and structured logging."""
        category = scenario_path.parent.name
        scenario_name = scenario_path.stem
        timeout_ms = self.get_timeout(scenario_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Prepare serial log file (structured per category/scenario)
        serial_cat_dir = SERIAL_LOG_DIR / category
        serial_cat_dir.mkdir(parents=True, exist_ok=True)
        serial_log_file = serial_cat_dir / f"{scenario_name}_{timestamp}.log"

        # Legacy flat log file (for backwards compatibility)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        legacy_log_file = LOG_DIR / f"{scenario_name}_{timestamp}.log"

        # Build relative scenario path for wokwi-cli
        rel_scenario = scenario_path.relative_to(TRABAJANTE_DIR)

        if self.verbose:
            print(f"  Running: {scenario_name} (timeout: {timeout_ms}ms)")

        # Start MQTT capture before running scenario (if enabled)
        mqtt_data = None
        if self.mqtt_capture:
            mqtt_data = await start_mqtt_capture(category, scenario_name)
            if mqtt_data and self.verbose:
                print(f"    MQTT capture started")

        start = datetime.now()

        try:
            # Run wokwi-cli (use POSIX paths for cross-platform compatibility)
            process = await asyncio.create_subprocess_exec(
                "wokwi-cli", ".",
                "--timeout", str(timeout_ms),
                "--scenario", rel_scenario.as_posix(),
                cwd=TRABAJANTE_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )

            # Wait with system timeout (add 30s buffer)
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=(timeout_ms / 1000) + 30
                )
                output = stdout.decode("utf-8", errors="replace")
                exit_code = process.returncode or 0
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                output = "System timeout - wokwi-cli did not respond"
                exit_code = -1

        except Exception as e:
            output = f"Error running wokwi-cli: {e}"
            exit_code = -2

        duration_ms = int((datetime.now() - start).total_seconds() * 1000)

        # Stop MQTT capture after scenario completes
        mqtt_log_rel = await stop_mqtt_capture(mqtt_data)

        # Write structured serial log file
        with open(serial_log_file, "w", encoding="utf-8") as f:
            f.write(f"# Serial Log - {scenario_name}\n")
            f.write(f"# Category: {category}\n")
            f.write(f"# Timeout: {timeout_ms}ms\n")
            f.write(f"# Duration: {duration_ms}ms\n")
            f.write(f"# Exit Code: {exit_code}\n")
            f.write(f"# Started: {start.isoformat()}\n")
            f.write("# " + "=" * 57 + "\n")
            f.write(output)

        # Write legacy flat log (for backwards compatibility)
        with open(legacy_log_file, "w", encoding="utf-8") as f:
            f.write(f"Scenario: {scenario_name}\n")
            f.write(f"Category: {category}\n")
            f.write(f"Timeout: {timeout_ms}ms\n")
            f.write(f"Duration: {duration_ms}ms\n")
            f.write(f"Exit Code: {exit_code}\n")
            f.write("=" * 60 + "\n")
            f.write(output)

        # Determine status
        if exit_code == 0:
            status = TestStatus.PASS
            error_message = None
        elif exit_code == -1:
            status = TestStatus.TIMEOUT
            error_message = "System timeout"
        elif "timeout" in output.lower():
            status = TestStatus.TIMEOUT
            error_message = "Wokwi timeout"
        else:
            status = TestStatus.FAIL
            # Extract error from output
            lines = output.strip().split("\n")
            error_message = lines[-1][:100] if lines else "Unknown error"

        result = TestResult(
            scenario_name=scenario_name,
            category=category,
            status=status,
            duration_ms=duration_ms,
            exit_code=exit_code,
            output_lines=len(output.split("\n")),
            error_message=error_message,
            log_file=str(legacy_log_file.relative_to(PROJECT_DIR)),
            serial_log_file=str(serial_log_file.relative_to(PROJECT_DIR)),
            mqtt_log_file=mqtt_log_rel
        )

        # Print result immediately
        status_symbol = {
            TestStatus.PASS: "[PASS]",
            TestStatus.FAIL: "[FAIL]",
            TestStatus.TIMEOUT: "[TIME]",
            TestStatus.SKIP: "[SKIP]",
            TestStatus.ERROR: "[ERR!]",
        }
        mqtt_indicator = " +MQTT" if mqtt_log_rel else ""
        print(f"  {status_symbol[status]} {scenario_name} ({duration_ms}ms){mqtt_indicator}")

        if status != TestStatus.PASS and error_message and self.verbose:
            print(f"         {error_message[:80]}")

        return result

    async def run_scenario_with_retry(self, scenario_path: Path) -> TestResult:
        """Run a scenario with retry logic for flaky tests."""
        attempts = 0
        result = None

        while attempts <= self.retries:
            attempts += 1
            result = await self.run_scenario(scenario_path)

            # Success - return immediately
            if result.status == TestStatus.PASS:
                if attempts > 1:
                    result.retried = True
                    self.retry_count += 1
                    if self.verbose:
                        print(f"         ↳ Passed on attempt {attempts}")
                result.attempts = attempts
                return result

            # Check if we should retry
            if attempts <= self.retries and result.exit_code in RETRY_ON_EXIT_CODES:
                if self.verbose:
                    print(f"         ↳ Retrying ({attempts}/{self.retries + 1})...")
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                break

        # All retries exhausted
        if result:
            result.attempts = attempts
            result.retried = attempts > 1
        return result  # type: ignore

    async def run_scenarios_parallel(self, scenarios: list[Path]) -> list[TestResult]:
        """Run scenarios with limited parallelism."""
        semaphore = asyncio.Semaphore(self.parallel)

        async def run_with_semaphore(scenario: Path) -> TestResult:
            async with semaphore:
                return await self.run_scenario_with_retry(scenario)

        tasks = [run_with_semaphore(s) for s in scenarios]
        return await asyncio.gather(*tasks)

    async def run_scenarios_sequential(self, scenarios: list[Path]) -> list[TestResult]:
        """Run scenarios one by one."""
        results = []
        for scenario in scenarios:
            result = await self.run_scenario_with_retry(scenario)
            results.append(result)
        return results

    def print_summary(self):
        """Print test summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == TestStatus.PASS)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        timeout = sum(1 for r in self.results if r.status == TestStatus.TIMEOUT)
        retried = sum(1 for r in self.results if r.retried)

        total_duration = sum(r.duration_ms for r in self.results)

        print("\n" + "=" * 60)
        print("WOKWI TEST SUMMARY")
        print("=" * 60)
        print(f"Total:    {total} scenarios")
        print(f"[PASS]    {passed}" + (f" ({retried} on retry)" if retried > 0 else ""))
        print(f"[FAIL]    {failed}")
        print(f"[TIMEOUT] {timeout}")
        print(f"Duration: {total_duration / 1000:.1f}s")
        if self.retries > 0:
            print(f"Retries:  {self.retries} max, {self.retry_count} used")

        if total > 0:
            rate = (passed / total) * 100
            print(f"Success:  {rate:.1f}%")

        if failed > 0 or timeout > 0:
            print("\nFailed/Timeout scenarios:")
            for r in self.results:
                if r.status in (TestStatus.FAIL, TestStatus.TIMEOUT):
                    attempts_info = f" (after {r.attempts} attempts)" if r.attempts > 1 else ""
                    print(f"  - {r.category}/{r.scenario_name}: {r.error_message or 'No details'}{attempts_info}")

        print("=" * 60)

    def save_json_report(self) -> Path:
        """Save results as JSON report."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = REPORTS_DIR / f"test_report_{timestamp}.json"

        retried_count = sum(1 for r in self.results if r.retried)
        report = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.status == TestStatus.PASS),
            "failed": sum(1 for r in self.results if r.status == TestStatus.FAIL),
            "timeout": sum(1 for r in self.results if r.status == TestStatus.TIMEOUT),
            "retried": retried_count,
            "max_retries": self.retries,
            "duration_ms": sum(r.duration_ms for r in self.results),
            "results": [r.to_dict() for r in self.results]
        }

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        print(f"\nJSON report: {report_file.relative_to(PROJECT_DIR)}")
        return report_file

    def generate_junit_xml(self) -> Path:
        """Generate JUnit XML report for GitHub Actions test-reporter."""
        import xml.etree.ElementTree as ET

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        junit_file = REPORTS_DIR / f"junit_{timestamp}.xml"

        # Group results by category
        categories: dict[str, list[TestResult]] = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = []
            categories[r.category].append(r)

        # Create XML structure
        testsuites = ET.Element("testsuites")
        testsuites.set("name", "Wokwi ESP32 Tests")
        testsuites.set("tests", str(len(self.results)))
        testsuites.set("failures", str(sum(1 for r in self.results if r.status == TestStatus.FAIL)))
        testsuites.set("errors", str(sum(1 for r in self.results if r.status == TestStatus.TIMEOUT)))
        testsuites.set("time", str(sum(r.duration_ms for r in self.results) / 1000))

        for category, results in categories.items():
            testsuite = ET.SubElement(testsuites, "testsuite")
            testsuite.set("name", category)
            testsuite.set("tests", str(len(results)))
            testsuite.set("failures", str(sum(1 for r in results if r.status == TestStatus.FAIL)))
            testsuite.set("errors", str(sum(1 for r in results if r.status == TestStatus.TIMEOUT)))
            testsuite.set("time", str(sum(r.duration_ms for r in results) / 1000))

            for result in results:
                testcase = ET.SubElement(testsuite, "testcase")
                testcase.set("name", result.scenario_name)
                testcase.set("classname", f"wokwi.{category}")
                testcase.set("time", str(result.duration_ms / 1000))

                if result.status == TestStatus.FAIL:
                    failure = ET.SubElement(testcase, "failure")
                    failure.set("message", result.error_message or "Test failed")
                    failure.set("type", "AssertionError")
                    failure.text = f"Exit code: {result.exit_code}\nAttempts: {result.attempts}"
                    if result.serial_log_file:
                        failure.text += f"\nLog: {result.serial_log_file}"

                elif result.status == TestStatus.TIMEOUT:
                    error = ET.SubElement(testcase, "error")
                    error.set("message", result.error_message or "Timeout")
                    error.set("type", "TimeoutError")
                    error.text = f"Exit code: {result.exit_code}\nAttempts: {result.attempts}"

                elif result.status == TestStatus.SKIP:
                    skipped = ET.SubElement(testcase, "skipped")
                    skipped.set("message", result.error_message or "Skipped")

                # Add retry info as property if retried
                if result.retried:
                    properties = ET.SubElement(testcase, "properties")
                    prop = ET.SubElement(properties, "property")
                    prop.set("name", "retried")
                    prop.set("value", str(result.attempts))

        # Write XML file
        tree = ET.ElementTree(testsuites)
        ET.indent(tree, space="  ")
        tree.write(junit_file, encoding="unicode", xml_declaration=True)

        print(f"JUnit report: {junit_file.relative_to(PROJECT_DIR)}")
        return junit_file

    async def run(self, category: Optional[str] = None,
                  scenario_name: Optional[str] = None,
                  list_only: bool = False,
                  include_skipped: bool = False) -> int:
        """Main entry point."""
        self.start_time = datetime.now()

        # Skip prerequisite checks for list-only mode
        if not list_only:
            # Check prerequisites
            if not self.check_prerequisites():
                return 1

        # Build firmware if requested
        if self.build_first:
            if not self.build_firmware():
                return 1

        # Discover scenarios
        scenarios = self.discover_scenarios(category, scenario_name, include_skipped)

        if not scenarios:
            print("[ERROR] No scenarios found")
            return 1

        if list_only:
            print(f"\nAvailable scenarios ({len(scenarios)}):")
            current_cat = None
            for s in scenarios:
                cat = s.parent.name
                if cat != current_cat:
                    # Show skip count for this category
                    skip_count = len(SKIP_SCENARIOS.get(cat, []))
                    skip_info = f" ({skip_count} skipped)" if skip_count > 0 and not include_skipped else ""
                    print(f"\n  {cat}/{skip_info}")
                    current_cat = cat
                timeout = self.get_timeout(s)
                print(f"    {s.stem} ({timeout}ms)")

            # Show total skip count if not including skipped
            if not include_skipped:
                total_skipped = sum(len(v) for v in SKIP_SCENARIOS.values())
                if total_skipped > 0:
                    print(f"\n  Note: {total_skipped} scenarios skipped (use --include-skipped to show)")
            return 0

        print(f"\n{'=' * 60}")
        print(f"WOKWI TEST RUNNER")
        print(f"{'=' * 60}")
        print(f"Scenarios:    {len(scenarios)}")
        print(f"Parallel:     {self.parallel}")
        print(f"MQTT Capture: {'enabled' if self.mqtt_capture else 'disabled'}")
        print(f"Retries:      {self.retries} max")
        print(f"{'=' * 60}\n")

        # Run scenarios
        if self.parallel > 1:
            self.results = await self.run_scenarios_parallel(scenarios)
        else:
            self.results = await self.run_scenarios_sequential(scenarios)

        # Print summary
        self.print_summary()

        # Save reports
        self.save_json_report()
        self.generate_junit_xml()

        # Return exit code
        failed = sum(1 for r in self.results if r.status != TestStatus.PASS)
        return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Wokwi Test Runner for AutomationOne",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                        Run all active CI scenarios
  %(prog)s --category 01-boot     Run boot tests only
  %(prog)s --scenario boot_full   Run specific scenario
  %(prog)s --parallel 4           Run 4 tests in parallel
  %(prog)s --list                 List available scenarios
  %(prog)s --build                Build firmware before testing
        """
    )

    parser.add_argument(
        "--category", "-c",
        help="Run scenarios from specific category (e.g., 01-boot, 02-sensor)"
    )
    parser.add_argument(
        "--scenario", "-s",
        help="Run specific scenario by name (partial match)"
    )
    parser.add_argument(
        "--parallel", "-p",
        type=int,
        default=1,
        help=f"Number of parallel test executions (default: {SAFE_PARALLEL_DEFAULT})"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output"
    )
    parser.add_argument(
        "--build", "-b",
        action="store_true",
        help="Build firmware before running tests"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available scenarios without running"
    )
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="Include scenarios that are normally skipped (SKIP_SCENARIOS)"
    )
    parser.add_argument(
        "--mqtt-capture",
        action="store_true",
        default=True,
        help="Enable MQTT traffic capture (default: enabled)"
    )
    parser.add_argument(
        "--no-mqtt-capture",
        action="store_true",
        help="Disable MQTT traffic capture"
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=MAX_RETRIES,
        help=f"Number of retries for failed tests (default: {MAX_RETRIES})"
    )
    parser.add_argument(
        "--no-retry",
        action="store_true",
        help="Disable retry logic (useful for debugging)"
    )
    parser.add_argument(
        "--allow-unsafe-parallel",
        action="store_true",
        help="Allow parallel>1 execution (unsafe without ESP-ID/topic isolation)"
    )

    args = parser.parse_args()

    # Handle mqtt capture flag
    mqtt_capture = args.mqtt_capture and not args.no_mqtt_capture

    runner = WokwiTestRunner(
        parallel=args.parallel,
        verbose=args.verbose,
        build_first=args.build,
        mqtt_capture=mqtt_capture,
        retries=args.retries,
        no_retry=args.no_retry,
        allow_unsafe_parallel=args.allow_unsafe_parallel
    )

    exit_code = asyncio.run(runner.run(
        category=args.category,
        scenario_name=args.scenario,
        list_only=args.list,
        include_skipped=args.include_skipped
    ))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
