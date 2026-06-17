"""
Test Runner für Paket D: Maintenance Jobs

Führt alle Unit-Tests für Maintenance Jobs aus und gibt einen Report.

Usage:
    python run_maintenance_tests.py

    # Mit Coverage:
    pytest god_kaiser_server/tests/unit/test_*_cleanup.py --cov=god_kaiser_server.src.services.maintenance --cov-report=html

    # Einzelner Test:
    pytest god_kaiser_server/tests/unit/test_sensor_data_cleanup.py::TestSensorDataCleanup::test_disabled_mode -v
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Führt alle Maintenance-Tests aus"""

    print("=" * 80)
    print("Paket D: Maintenance Jobs - Test Suite")
    print("=" * 80)
    print()

    # Test-Dateien
    test_files = [
        "god_kaiser_server/tests/unit/test_sensor_data_cleanup.py",
        "god_kaiser_server/tests/unit/test_command_history_cleanup.py",
        "god_kaiser_server/tests/unit/test_orphaned_mocks_cleanup.py",
    ]

    # Prüfe ob Dateien existieren
    missing_files = []
    for test_file in test_files:
        if not Path(test_file).exists():
            missing_files.append(test_file)

    if missing_files:
        print("❌ ERROR: Test-Dateien fehlen:")
        for file in missing_files:
            print(f"   - {file}")
        sys.exit(1)

    # Pytest Args
    pytest_args = [
        "pytest",
        *test_files,
        "-v",  # Verbose
        "--tb=short",  # Short traceback
        "--color=yes",  # Color output
        "-x",  # Stop on first failure
    ]

    print("Führe Tests aus:")
    for file in test_files:
        print(f"  ✓ {file}")
    print()

    # Run tests
    result = subprocess.run(pytest_args, capture_output=False)

    print()
    print("=" * 80)
    if result.returncode == 0:
        print("✅ ALLE TESTS PASSED")
        print()
        print("Nächste Schritte:")
        print("1. Manuelle Verifikation: Server starten und Logs prüfen")
        print("2. Optional: Performance-Tests durchführen")
        print("3. Production-Deployment gemäß Rollout-Plan")
    else:
        print("❌ TESTS FAILED")
        print()
        print("Bitte Fehler beheben und erneut ausführen.")
        sys.exit(1)

    print("=" * 80)


if __name__ == "__main__":
    main()
