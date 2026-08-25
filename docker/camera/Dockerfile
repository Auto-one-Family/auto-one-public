FROM debian:trixie-slim

# Raspberry Pi Foundation keyring for libcamera/picamera2 packages (Trixie).
# The .pgp file is copied from the build context (not downloaded at build time)
# to avoid internet dependency and match the exact host keyring version.
COPY raspberrypi-archive-keyring.pgp /usr/share/keyrings/raspberrypi-archive-keyring.pgp

RUN echo "deb [arch=arm64 signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.pgp] http://archive.raspberrypi.com/debian/ trixie main" \
        > /etc/apt/sources.list.d/raspi.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-picamera2 \
        python3-libcamera \
        libcamera-ipa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY camera_service.py .
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["python3", "camera_service.py"]
