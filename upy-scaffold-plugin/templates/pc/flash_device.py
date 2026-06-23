#!/usr/bin/env python3
"""MicroPython project deploy tool.

Compile .py → .mpy, flash firmware to device, upload project files.

Usage:
  python tools/flash_device.py --compile          # .py → build/mpy/
  python tools/flash_device.py --flash            # flash firmware to device
  python tools/flash_device.py --upload           # upload build/mpy/ to device
  python tools/flash_device.py --all              # compile + flash + upload
  python tools/flash_device.py --all --port COM3  # specify serial port
"""

import json
import os
import subprocess
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE_DIR = os.path.join(ROOT, "firmware")
BUILD_DIR = os.path.join(ROOT, "build")
MPY_DIR = os.path.join(BUILD_DIR, "mpy")
MANIFEST_PATH = os.path.join(ROOT, "project-manifest.json")
ENTRY_FILES = {"main.py", "boot.py"}

_COM_PORT = ""
_MPY_CROSS_AVAILABLE = None


def load_manifest() -> dict:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def select_com_port() -> str:
    try:
        import serial.tools.list_ports
        ports = [p.device for p in serial.tools.list_ports.comports()]
    except ImportError:
        ports = []

    if not ports:
        port = input("Enter serial port (e.g. COM3, /dev/ttyACM0): ").strip()
        return port

    print("Available serial ports:")
    for i, p in enumerate(ports):
        print("  [{}] {}".format(i, p))
    if len(ports) == 1:
        print("  Auto-select: {}".format(ports[0]))
        return ports[0]
    idx = input("Select port number: ").strip()
    try:
        return ports[int(idx)]
    except (ValueError, IndexError):
        print("[ERROR] invalid selection")
        sys.exit(1)


def _mpremote(cmd, timeout=60, check=True) -> subprocess.CompletedProcess:
    full = ["mpremote"]
    if _COM_PORT:
        full += ["connect", _COM_PORT]
    result = subprocess.run(
        full + cmd, capture_output=True, text=True, encoding="utf-8",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        print("[ERROR] mpremote command failed: {}".format(" ".join(cmd)))
        print(result.stderr)
        sys.exit(1)
    return result


def check_mpy_cross() -> bool:
    global _MPY_CROSS_AVAILABLE
    if _MPY_CROSS_AVAILABLE is None:
        try:
            _MPY_CROSS_AVAILABLE = subprocess.run(
                ["mpy-cross", "--version"], capture_output=True
            ).returncode == 0
        except FileNotFoundError:
            _MPY_CROSS_AVAILABLE = False
    return _MPY_CROSS_AVAILABLE


def compile_py_files():
    """Compile all .py files under firmware/ to build/mpy/, preserving structure."""
    print("[compile] Compiling .py → .mpy ...")
    if not check_mpy_cross():
        print("[WARNING] mpy-cross not found. Install: pip install mpy-cross")
        print("          Skipping compilation (use .py directly).")
        return

    py_files = []
    for root, dirs, files in os.walk(FIRMWARE_DIR):
        for f in files:
            if f.endswith(".py") and f not in ENTRY_FILES:
                py_files.append(os.path.join(root, f))

    if not py_files:
        print("[compile] No .py files found under firmware/")
        return

    os.makedirs(MPY_DIR, exist_ok=True)
    manifest = load_manifest()
    mcu = manifest.get("mcu", {})
    mpy_version = mcu.get("mpy_version", "")

    for src in py_files:
        rel = os.path.relpath(src, FIRMWARE_DIR)
        dest = os.path.join(MPY_DIR, rel).replace(".py", ".mpy")
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        cmd = ["mpy-cross", "-o", dest, src]
        if mpy_version:
            cmd += ["-march", mpy_version]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            print("  OK  {}".format(rel))
        else:
            print("  FAIL  {}: {}".format(rel, result.stderr.decode().strip()))

    print("[compile] Done → build/mpy/")


def flash_firmware():
    """Flash MicroPython firmware to device based on MCU type in manifest."""
    manifest = load_manifest()
    mcu = manifest.get("mcu", {})
    model = mcu.get("model", "")
    board = mcu.get("board", "")
    fw_url = mcu.get("firmware_url", "")

    print("[flash] MCU: {} ({})".format(model, board))

    # Find firmware binary in build/firmware/
    fw_dir = os.path.join(BUILD_DIR, "firmware")
    bins = [f for f in os.listdir(fw_dir) if f.endswith((".bin", ".uf2", ".hex"))] if os.path.exists(fw_dir) else []

    if "ESP" in model:
        # ESP32 series → esptool.py
        if not bins:
            print("[flash] No .bin found in build/firmware/")
            print("        Download from: {}".format(fw_url))
            sys.exit(1)
        bin_path = os.path.join(fw_dir, bins[0])
        print("[flash] Erasing and writing: {}".format(bins[0]))
        chip = "esp32" if model == "ESP32" else model.lower().replace("-", "").replace(" ", "")
        cmd = [
            sys.executable, "-m", "esptool",
            "--chip", chip,
            "--port", _COM_PORT,
            "--baud", "460800",
            "write_flash", "--erase-all", "-z", "0x0", bin_path,
        ]
        subprocess.run(cmd, check=True)
        print("[flash] Done. Press RST on device.")

    elif "Pico" in model:
        # RP2040 → drag .uf2 in bootloader mode
        print("[flash] For Pico series:")
        if bins:
            uf2 = [f for f in bins if f.endswith(".uf2")]
            if uf2:
                print("        1. Hold BOOTSEL button on Pico")
                print("        2. Connect USB → RPI-RP2 drive appears")
                print("        3. Copy {} to RPI-RP2 drive".format(uf2[0]))
            else:
                print("        No .uf2 file in build/firmware/")
        else:
            print("        Download .uf2 from: {}".format(fw_url))
            print("        Hold BOOTSEL → connect USB → drag .uf2 to RPI-RP2")

    else:
        print("[flash] Unknown MCU model. Manual flash required.")
        if fw_url:
            print("        Firmware: {}".format(fw_url))


def _upload_dir(source_dir: str, label: str):
    """Upload all files from source_dir to device."""
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f == ".gitkeep":
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, source_dir).replace("\\", "/")
            remote = ":{}".format(rel)

            remote_dir = ":{}".format(os.path.dirname(rel).replace("\\", "/"))
            if remote_dir not in (":", ":."):
                _mpremote(["fs", "mkdir", remote_dir], check=False)

            try:
                _mpremote(["cp", src, remote])
                size_kb = os.path.getsize(src) / 1024
                print("  OK  {}  ({:.1f} KB)".format(remote, size_kb))
            except SystemExit:
                print("[ERROR] upload failed: {}".format(f))
                sys.exit(1)


def upload_files():
    """Upload .mpy (or .py) files to device, with main.py/boot.py always from firmware/.

    When build/mpy/ exists, uploads .mpy from there plus main.py/boot.py from firmware/.
    Otherwise falls back to uploading all .py from firmware/.
    """
    use_mpy = os.path.exists(MPY_DIR) and os.listdir(MPY_DIR)

    if use_mpy:
        print("[upload] Source: build/mpy/ + firmware/{main,boot}.py → device")
        _upload_dir(MPY_DIR, "mpy")
        # Always upload entry files as .py from firmware/
        for entry in ENTRY_FILES:
            src = os.path.join(FIRMWARE_DIR, entry)
            if os.path.exists(src):
                try:
                    _mpremote(["cp", src, ":{}".format(entry)])
                    print("  OK  :{}  ({:.1f} KB)".format(entry, os.path.getsize(src) / 1024))
                except SystemExit:
                    print("[ERROR] upload failed: {}".format(entry))
                    sys.exit(1)
    else:
        print("[upload] Source: firmware/ → device (no .mpy available)")
        _upload_dir(FIRMWARE_DIR, "py")

    print("[upload] Done")


def reset_device():
    """Soft-reset the device to restart MicroPython interpreter."""
    print("[reset] Soft-resetting device...")
    try:
        _mpremote(["soft-reset"])
    except Exception:
        pass


def main():
    global _COM_PORT

    parser = argparse.ArgumentParser(description="MicroPython project deploy tool")
    parser.add_argument("--port", default="", help="Serial port (auto-detect if empty)")
    parser.add_argument("--compile", action="store_true", help="Compile .py → .mpy")
    parser.add_argument("--flash", action="store_true", help="Flash firmware to device")
    parser.add_argument("--upload", action="store_true", help="Upload project files to device")
    parser.add_argument("--all", action="store_true", help="Compile + flash + upload")
    parser.add_argument("--no-reset", action="store_true", help="Skip device reset after upload")
    args = parser.parse_args()

    if not any([args.compile, args.flash, args.upload, args.all]):
        parser.print_help()
        sys.exit(1)

    do_all = args.all
    do_compile = args.compile or do_all
    do_flash = args.flash or do_all
    do_upload = args.upload or do_all

    _COM_PORT = args.port or select_com_port()
    print("[info] Using port: {}".format(_COM_PORT))

    if do_flash:
        flash_firmware()

    if do_compile:
        compile_py_files()

    if do_upload:
        upload_files()
        if not args.no_reset:
            reset_device()

    if do_all:
        print("\n" + "=" * 50)
        print("  Deploy complete!")
        print("=" * 50)


if __name__ == "__main__":
    main()
