# PlatformIO pre-script: Set MinGW toolchain path for native tests
# Required because MinGW is installed but not in system PATH
#
# Usage: Referenced in platformio.ini [env:native] via extra_scripts

Import("env")
import os
import shutil

# MinGW-w64 installation paths to search (ordered by preference)
MINGW_PATHS = [
    r"C:\Program Files\Git\mingw64\bin",
    r"C:\Program Files (x86)\Git\mingw64\bin",
    r"C:\ProgramData\mingw64\mingw64\bin",
    r"C:\msys64\mingw64\bin",
    r"C:\msys64\ucrt64\bin",
    r"C:\MinGW\bin",
    r"C:\mingw64\bin",
]

def find_mingw():
    """Find MinGW bin directory with gcc.exe"""
    for path in MINGW_PATHS:
        gcc_path = os.path.join(path, "gcc.exe")
        if os.path.exists(gcc_path):
            return path
    return None

if shutil.which("gcc") or shutil.which("gcc.exe"):
    print("[native-toolchain] gcc found on PATH — native tests can use this toolchain")

mingw_bin = find_mingw()

if mingw_bin:
    current_path = env['ENV'].get('PATH', '')
    if mingw_bin not in current_path:
        env['ENV']['PATH'] = mingw_bin + os.pathsep + current_path
        print(f"[native-toolchain] Added MinGW to PATH: {mingw_bin}")

    # Static linking: embed MinGW runtime into binary
    # Prevents 0xC0000005 crash when test runner can't find DLLs
    env.Append(LINKFLAGS=["-static"])
    print("[native-toolchain] Static linking enabled (no MinGW DLL dependency)")
else:
    print("[native-toolchain] WARNING: MinGW not found! Native tests will fail.")
    print(f"[native-toolchain] Searched: {MINGW_PATHS}")
