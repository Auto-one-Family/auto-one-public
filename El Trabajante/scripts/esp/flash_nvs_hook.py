# PlatformIO pre-script: adds flash_nvs custom target to [env:flash_nvs].
# Usage:
#   pio run -e flash_nvs -t flash_nvs NVS_ENV=dev-local UPLOAD_PORT=COM5
#   pio run -e flash_nvs -t flash_nvs NVS_ENV=dev-local   (generate-only if no port)
#
# NVS_ENV: dev-local | pi-home | pi-elbherb (default: dev-local)
# UPLOAD_PORT: serial port, e.g. COM5 or /dev/ttyUSB0 (optional)

import os
import subprocess
import sys

Import("env")  # noqa: F821 — PlatformIO SCons global


def _flash_nvs_action(target, source, env):
    nvs_env = os.environ.get("NVS_ENV", "dev-local")
    port = os.environ.get("UPLOAD_PORT") or env.subst("$UPLOAD_PORT") or ""
    script = os.path.join(env.subst("$PROJECT_DIR"), "scripts", "esp", "flash_nvs.py")
    cmd = [sys.executable, script, "--env", nvs_env]
    if port:
        cmd += ["--port", port]
    else:
        cmd += ["--generate-only"]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        env.Exit(1)


env.AddCustomTarget(  # noqa: F821
    name="flash_nvs",
    dependencies=None,
    actions=[_flash_nvs_action],
    title="Flash NVS Secrets",
    description=(
        "Generate and flash NVS credential binary. "
        "Set NVS_ENV=dev-local|pi-home|pi-elbherb and optionally UPLOAD_PORT=COM5."
    ),
)
