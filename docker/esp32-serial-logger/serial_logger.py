#!/usr/bin/env python3
"""
ESP32 Serial Logger - TCP-to-JSON Bridge
=========================================

Connects to a ser2net/socat TCP bridge (host.docker.internal:3333),
reads ESP32 serial output, parses it, and outputs structured JSON to stdout.

Promtail automatically captures the JSON output via Docker socket service discovery.

Supports 4 ESP32 log formats:
1. Custom Logger: [millis] [LEVEL] message
2. Boot Banner: Plaintext with box-drawing characters
3. MQTT Debug JSON: [DEBUG]{...json...}
4. ESP-IDF SDK: <level> (<millis>) <tag>: <message>

Environment Variables:
- SERIAL_HOST: TCP host (default: host.docker.internal)
- SERIAL_PORT: TCP port (default: 3333)
- DEVICE_ID: ESP32 device identifier (default: esp32-unknown)
- LOG_FORMAT: "structured" or "passthrough" (default: structured)
- RECONNECT_DELAY: Seconds between reconnect attempts (default: 5)
"""

import json
import os
import re
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from typing import Optional


class SerialLogger:
    """
    TCP Serial Logger with structured JSON output.

    Connects to a TCP-based serial bridge (ser2net/socat) and parses
    ESP32 serial output into structured JSON logs for Promtail/Loki.
    """

    # Regex patterns for ESP32 log formats
    PATTERN_CUSTOM_LOGGER = re.compile(
        r'^\[\s*(?P<millis>\d+)\]\s+\[(?P<level>\w+)\s*\]\s+(?P<message>.*)'
    )
    PATTERN_ESP_IDF = re.compile(
        r'^(?P<level>[EWID])\s+\((?P<millis>\d+)\)\s+(?P<tag>[\w\.]+):\s+(?P<message>.*)'
    )
    PATTERN_MQTT_DEBUG = re.compile(
        r'^\[DEBUG\](?P<json>\{.*\})'
    )

    # ESP-IDF log level mapping
    ESP_IDF_LEVELS = {
        'E': 'ERROR',
        'W': 'WARNING',
        'I': 'INFO',
        'D': 'DEBUG'
    }

    # Exponential backoff constants
    BACKOFF_MAX_DELAY: int = 60  # Cap at 60 seconds

    def __init__(
        self,
        host: str,
        port: int,
        device_id: str,
        log_format: str = "structured",
        reconnect_delay: int = 5
    ):
        """
        Initialize SerialLogger.

        Args:
            host: TCP host to connect to
            port: TCP port
            device_id: ESP32 device identifier
            log_format: "structured" or "passthrough"
            reconnect_delay: Base seconds between reconnect attempts
        """
        self.host = host
        self.port = port
        self.device_id = device_id
        self.log_format = log_format
        self.reconnect_delay = reconnect_delay
        self._current_delay = reconnect_delay
        self.running = True
        self.sock: Optional[socket.socket] = None

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _connect(self) -> bool:
        """
        Connect to TCP serial bridge.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(10.0)
            self.sock.connect((self.host, self.port))
            self._log_info(f"Connected to {self.host}:{self.port}")
            self._current_delay = self.reconnect_delay  # Reset backoff on success
            return True
        except Exception as e:
            self._log_error(f"Connection failed (retry in {self._current_delay}s): {e}")
            self.sock = None
            return False

    def _backoff(self) -> None:
        """Increase reconnect delay with exponential backoff (capped)."""
        self._current_delay = min(self._current_delay * 2, self.BACKOFF_MAX_DELAY)

    def _parse_line(self, line: str) -> dict:
        """
        Parse a single log line into structured JSON.

        Args:
            line: Raw serial line

        Returns:
            Structured log entry as dict
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Format 1: Custom Logger [millis] [LEVEL] message
        match = self.PATTERN_CUSTOM_LOGGER.match(line)
        if match:
            level = match.group('level').strip().lower()
            message = match.group('message').strip()
            component = self._extract_component(message)
            return {
                "timestamp": timestamp,
                "level": level,
                "device_id": self.device_id,
                "component": component,
                "message": message,
                "format": "custom_logger",
                "millis": int(match.group('millis'))
            }

        # Format 3: MQTT Debug JSON [DEBUG]{...}
        match = self.PATTERN_MQTT_DEBUG.match(line)
        if match:
            try:
                debug_json = json.loads(match.group('json'))
                return {
                    "timestamp": timestamp,
                    "level": "debug",
                    "device_id": self.device_id,
                    "component": "mqtt",
                    "message": debug_json.get("message", ""),
                    "format": "mqtt_debug_json",
                    "debug_data": debug_json
                }
            except json.JSONDecodeError:
                pass  # Fall through to plaintext

        # Format 4: ESP-IDF SDK <level> (<millis>) <tag>: <message>
        match = self.PATTERN_ESP_IDF.match(line)
        if match:
            level_char = match.group('level')
            level = self.ESP_IDF_LEVELS.get(level_char, 'info').lower()
            tag = match.group('tag')
            message = match.group('message').strip()
            return {
                "timestamp": timestamp,
                "level": level,
                "device_id": self.device_id,
                "component": tag,
                "message": message,
                "format": "esp_idf",
                "millis": int(match.group('millis'))
            }

        # Format 2: Boot Banner / Plaintext (no parsing)
        component = "serial" if line.startswith(('+', '|', 'Chip', 'CPU', 'Free')) else "unknown"
        return {
            "timestamp": timestamp,
            "level": "info",
            "device_id": self.device_id,
            "component": component,
            "message": line.strip(),
            "format": "plaintext"
        }

    def _extract_component(self, message: str) -> str:
        """
        Extract component name from message prefix.

        Args:
            message: Log message

        Returns:
            Component name (e.g., "mqtt", "sensor", "logger")
        """
        # Common patterns: "ComponentName: message" or "ComponentName - message"
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]+)[\:\-\s]', message)
        if match:
            component = match.group(1).lower()
            # Map known components
            if component in ('mqtt', 'sensor', 'logger', 'wifi', 'storage', 'config'):
                return component
        return "app"

    def _log_info(self, message: str) -> None:
        """Log info message to stdout as structured JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "info",
            "device_id": self.device_id,
            "component": "logger",
            "message": message,
            "format": "internal"
        }
        print(json.dumps(log_entry), flush=True)

    def _log_error(self, message: str) -> None:
        """Log error message to stdout as structured JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "error",
            "device_id": self.device_id,
            "component": "logger",
            "message": message,
            "format": "internal"
        }
        print(json.dumps(log_entry), flush=True)

    def run(self) -> None:
        """Main run loop with auto-reconnect."""
        self._log_info(f"ESP32 Serial Logger starting for device: {self.device_id}")
        self._log_info(f"Target: {self.host}:{self.port}, Format: {self.log_format}")

        buffer = ""

        while self.running:
            # Connect or reconnect
            if not self.sock:
                if not self._connect():
                    time.sleep(self._current_delay)
                    self._backoff()
                    continue

            try:
                # Read data from socket
                data = self.sock.recv(4096)
                if not data:
                    # Connection closed by remote
                    self._log_info("Connection closed by remote, reconnecting...")
                    self.sock.close()
                    self.sock = None
                    time.sleep(self._current_delay)
                    self._backoff()
                    continue

                # Decode and buffer
                try:
                    text = data.decode('utf-8')
                except UnicodeDecodeError:
                    text = data.decode('utf-8', errors='replace')

                buffer += text

                # Process complete lines
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.rstrip('\r')

                    if not line:
                        continue

                    # Output based on format mode
                    if self.log_format == "passthrough":
                        print(line, flush=True)
                    else:
                        log_entry = self._parse_line(line)
                        print(json.dumps(log_entry), flush=True)

            except socket.timeout:
                # No data received, continue
                continue

            except Exception as e:
                self._log_error(f"Error reading from socket: {e}")
                if self.sock:
                    self.sock.close()
                    self.sock = None
                time.sleep(self._current_delay)
                self._backoff()

        # Shutdown
        self._log_info("Serial logger shutting down")
        if self.sock:
            self.sock.close()


def main():
    """Entry point."""
    # Read environment variables
    host = os.getenv('SERIAL_HOST', 'host.docker.internal')
    port = int(os.getenv('SERIAL_PORT', '3333'))
    device_id = os.getenv('DEVICE_ID', 'esp32-unknown')
    log_format = os.getenv('LOG_FORMAT', 'structured')
    reconnect_delay = int(os.getenv('RECONNECT_DELAY', '5'))

    # Validate log_format
    if log_format not in ('structured', 'passthrough'):
        print(f"ERROR: Invalid LOG_FORMAT '{log_format}', must be 'structured' or 'passthrough'", file=sys.stderr)
        sys.exit(1)

    # Create and run logger
    logger = SerialLogger(
        host=host,
        port=port,
        device_id=device_id,
        log_format=log_format,
        reconnect_delay=reconnect_delay
    )

    try:
        logger.run()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
