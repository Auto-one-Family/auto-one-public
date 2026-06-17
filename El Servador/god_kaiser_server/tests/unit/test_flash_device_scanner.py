"""
Unit Tests for Flash Device Scanner — AUT-765

All tests mock pyserial and OS/platform state; no real hardware required.
Covers: all VID/PID cases (incl. CH9102), unknown device, empty list, scan exception,
port without VID/PID, platform detection (Windows, macOS, Linux env override, auto-detect).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.services.flash.device_scanner import (
    _PID_CH340,
    _PID_CH9102,
    _PID_CP2102,
    _PID_ESP32C3_CDC_JTAG,
    _PID_ESP32S3_BUILTIN_USB,
    _PID_ESP32S3_JTAG,
    _USB_CHIP_MAP,
    _VID_CH340,
    _VID_ESPRESSIF,
    _VID_SILABS,
    is_usb_scanning_supported,
    scan_usb_devices,
)


def _make_port(
    device: str,
    vid: int,
    pid: int,
    description: str = "Test Device",
    hwid: str = "USB VID:PID=1234:5678",
) -> MagicMock:
    port = MagicMock()
    port.device = device
    port.vid = vid
    port.pid = pid
    port.description = description
    port.hwid = hwid
    return port


# =============================================================================
# VID/PID Mapping
# =============================================================================


class TestVidPidMapping:
    """Verify that all expected VID/PID pairs are present in the map."""

    @pytest.mark.parametrize(
        "vid, pid, expected_family, expected_board",
        [
            (_VID_CH340, _PID_CH340, "ESP32", "WROOM-32"),
            (_VID_CH340, _PID_CH9102, "ESP32", "WROOM-32-CH9102"),
            (_VID_SILABS, _PID_CP2102, "ESP32", "WROOM-32-CP"),
            (_VID_ESPRESSIF, _PID_ESP32S3_BUILTIN_USB, "ESP32-S3", "S3-XIAO"),
            (_VID_ESPRESSIF, _PID_ESP32S3_JTAG, "ESP32-S3", "S3-DevKit"),
            (_VID_ESPRESSIF, _PID_ESP32C3_CDC_JTAG, "ESP32-C3", "C3-DevKit"),
        ],
    )
    def test_known_vid_pid(
        self, vid: int, pid: int, expected_family: str, expected_board: str
    ) -> None:
        assert _USB_CHIP_MAP[(vid, pid)] == (expected_family, expected_board)

    def test_unknown_vid_pid_not_in_map(self) -> None:
        assert (0xDEAD, 0xBEEF) not in _USB_CHIP_MAP


# =============================================================================
# scan_usb_devices
# =============================================================================


class TestScanUsbDevices:
    """Test device scanning with mocked pyserial list_ports."""

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_ch340_wroom32_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM3", _VID_CH340, _PID_CH340, "USB-SERIAL CH340")
        ]
        devices = scan_usb_devices()

        assert len(devices) == 1
        assert devices[0].port == "COM3"
        assert devices[0].chip_family == "ESP32"
        assert devices[0].board_type == "WROOM-32"
        assert devices[0].vid == _VID_CH340
        assert devices[0].pid == _PID_CH340

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_cp2102_wroom32_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM5", _VID_SILABS, _PID_CP2102, "CP2102 USB to UART Bridge")
        ]
        devices = scan_usb_devices()

        assert devices[0].chip_family == "ESP32"
        assert devices[0].board_type == "WROOM-32-CP"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_esp32s3_xiao_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("/dev/ttyACM0", _VID_ESPRESSIF, _PID_ESP32S3_BUILTIN_USB)
        ]
        devices = scan_usb_devices()

        assert devices[0].chip_family == "ESP32-S3"
        assert devices[0].board_type == "S3-XIAO"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_esp32s3_devkit_jtag_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("/dev/ttyACM1", _VID_ESPRESSIF, _PID_ESP32S3_JTAG)
        ]
        devices = scan_usb_devices()

        assert devices[0].chip_family == "ESP32-S3"
        assert devices[0].board_type == "S3-DevKit"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_esp32c3_cdc_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM7", _VID_ESPRESSIF, _PID_ESP32C3_CDC_JTAG)
        ]
        devices = scan_usb_devices()

        assert devices[0].chip_family == "ESP32-C3"
        assert devices[0].board_type == "C3-DevKit"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_unknown_device_included_not_filtered(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM9", 0x1234, 0x5678, "Unknown USB Serial")
        ]
        devices = scan_usb_devices()

        assert len(devices) == 1
        assert devices[0].chip_family == "unknown"
        assert devices[0].board_type == "unknown"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_empty_port_list_returns_empty(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = []
        devices = scan_usb_devices()
        assert devices == []

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_scan_exception_raises_runtime_error(self, mock_comports: MagicMock) -> None:
        mock_comports.side_effect = OSError("Access denied")
        with pytest.raises(RuntimeError, match="USB port scan failed"):
            scan_usb_devices()

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_port_without_vid_pid_classified_unknown(self, mock_comports: MagicMock) -> None:
        port = _make_port("COM99", 0, 0)
        port.vid = None
        port.pid = None
        mock_comports.return_value = [port]
        devices = scan_usb_devices()

        assert len(devices) == 1
        assert devices[0].chip_family == "unknown"
        assert devices[0].vid == 0
        assert devices[0].pid == 0

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_ch9102_wroom32_detected(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM6", _VID_CH340, _PID_CH9102, "USB Serial CH9102")
        ]
        devices = scan_usb_devices()

        assert devices[0].chip_family == "ESP32"
        assert devices[0].board_type == "WROOM-32-CH9102"

    @patch("src.services.flash.device_scanner.list_ports.comports")
    def test_multiple_devices_all_returned(self, mock_comports: MagicMock) -> None:
        mock_comports.return_value = [
            _make_port("COM3", _VID_CH340, _PID_CH340),
            _make_port("COM8", _VID_ESPRESSIF, _PID_ESP32S3_BUILTIN_USB),
        ]
        devices = scan_usb_devices()

        assert len(devices) == 2
        assert devices[0].chip_family == "ESP32"
        assert devices[1].chip_family == "ESP32-S3"


# =============================================================================
# is_usb_scanning_supported
# =============================================================================


class TestIsUsbScanningSupported:
    """Test platform detection logic for USB scanning availability."""

    @patch("src.services.flash.device_scanner.sys")
    def test_windows_native_always_supported(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "win32"
        assert is_usb_scanning_supported() is True

    @patch("src.services.flash.device_scanner.sys")
    def test_macos_native_always_supported(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "darwin"
        assert is_usb_scanning_supported() is True

    @patch("src.services.flash.device_scanner.sys")
    @patch.dict("os.environ", {"USB_SCANNING_AVAILABLE": "true"})
    def test_linux_env_true_override(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "linux"
        assert is_usb_scanning_supported() is True

    @patch("src.services.flash.device_scanner.sys")
    @patch.dict("os.environ", {"USB_SCANNING_AVAILABLE": "false"})
    def test_linux_env_false_override(self, mock_sys: MagicMock) -> None:
        mock_sys.platform = "linux"
        assert is_usb_scanning_supported() is False

    @patch("src.services.flash.device_scanner.Path")
    @patch("src.services.flash.device_scanner.sys")
    @patch.dict("os.environ", {}, clear=False)
    def test_linux_serial_devices_present(
        self, mock_sys: MagicMock, mock_path: MagicMock
    ) -> None:
        mock_sys.platform = "linux"
        import os

        os.environ.pop("USB_SCANNING_AVAILABLE", None)
        mock_dev = MagicMock()
        mock_dev.glob.side_effect = lambda p: [MagicMock()] if p == "ttyUSB*" else []
        mock_path.return_value = mock_dev
        assert is_usb_scanning_supported() is True

    @patch("src.services.flash.device_scanner.Path")
    @patch("src.services.flash.device_scanner.sys")
    @patch.dict("os.environ", {}, clear=False)
    def test_linux_no_devices_degraded(
        self, mock_sys: MagicMock, mock_path: MagicMock
    ) -> None:
        mock_sys.platform = "linux"
        import os

        os.environ.pop("USB_SCANNING_AVAILABLE", None)
        mock_dev = MagicMock()
        mock_dev.glob.return_value = []
        mock_path.return_value = mock_dev
        assert is_usb_scanning_supported() is False
