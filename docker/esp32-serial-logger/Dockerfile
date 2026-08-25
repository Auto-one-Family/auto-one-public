# ESP32 Serial Logger - Docker Image
# ====================================
# Python 3.11-slim based container that connects to a TCP-based
# serial bridge (ser2net/socat) and outputs structured JSON logs.
#
# Build:
#   docker build -t esp32-serial-logger:latest .
#
# Run:
#   docker run --rm \
#     -e SERIAL_HOST=host.docker.internal \
#     -e SERIAL_PORT=3333 \
#     -e DEVICE_ID=esp32-xiao-01 \
#     esp32-serial-logger:latest

FROM python:3.11-slim

LABEL maintainer="AutomationOne"
LABEL description="ESP32 Serial-to-JSON Logger for Docker monitoring stack"

# Set working directory
WORKDIR /app

# Copy requirements (stdlib-only, no external deps)
COPY requirements.txt .

# Copy serial logger script
COPY serial_logger.py .
RUN chmod +x serial_logger.py

# Environment variables (defaults, override in docker-compose.yml)
ENV SERIAL_HOST=host.docker.internal \
    SERIAL_PORT=3333 \
    DEVICE_ID=esp32-unknown \
    LOG_FORMAT=structured \
    RECONNECT_DELAY=5

# Run as non-root user for security
RUN useradd -m -u 1000 logger && chown -R logger:logger /app
USER logger

# Health check: avoid external tools like pgrep in slim image.
# Verify PID 1 still runs the logger entrypoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "from pathlib import Path; import sys; sys.exit(0 if b'serial_logger.py' in Path('/proc/1/cmdline').read_bytes() else 1)"

# Entry point
ENTRYPOINT ["python3", "-u", "serial_logger.py"]
