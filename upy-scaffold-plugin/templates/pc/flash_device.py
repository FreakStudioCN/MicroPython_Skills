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
import fnmatch
import shutil
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE_DIR = os.path.join(ROOT, "firmware")
BUILD_DIR = os.path.join(ROOT, "build")
MPY_DIR = os.path.join(BUILD_DIR, "mpy")
MANIFEST_PATH = os.path.join(ROOT, "project-manifest.json")
SOURCE_ONLY_FILES = {"main.py", "boot.py", "conf.py"}
SOURCE_ONLY_MPY_FILES = {"main.mpy", "boot.mpy", "conf.mpy"}
COMPILE_EXCLUDE_PATTERNS = {"drivers/*/mock.py"}
UPLOAD_EXCLUDE_PATTERNS = {"drivers/*/mock.py", "drivers/*/mock.mpy"}

_COM_PORT = ""
_MPY_CROSS_AVAILABLE = None
_SUMMARY = {
    "status": "success",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "port": "",
    "steps": [],
    "errors": [],
    "compiled_files": [],
    "uploaded_files": [],
    "skipped_files": [],
}


def _mark_failed(code: str, message: str, **extra):
    _SUMMARY["status"] = "failed"
    error = {"code": code, "message": message}
    error.update(extra)
    _SUMMARY["errors"].append(error)


def _emit_summary(args, exit_code: int):
    _SUMMARY["exit_code"] = exit_code
    _SUMMARY["finished_at"] = datetime.now(timezone.utc).isoformat()
    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as f:
            json.dump(_SUMMARY, f, ensure_ascii=False, indent=2)
            f.write("\n")
    if args.json_summary:
        print(json.dumps(_SUMMARY, ensure_ascii=False, separators=(",", ":")))


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
        errors="replace",
        timeout=timeout,
    )
    _SUMMARY["steps"].append({
        "type": "mpremote",
        "command": full + cmd,
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    })
    if check and result.returncode != 0:
        _mark_failed("mpremote_failed", "mpremote command failed", command=full + cmd, stderr=result.stderr)
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


def _posix_rel(path: str) -> str:
    return path.replace("\\", "/").strip("/")


def _matches_any(rel: str, patterns) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def compile_skip_reason(rel: str):
    rel = _posix_rel(rel)
    if rel in SOURCE_ONLY_FILES:
        return "source_only"
    if _matches_any(rel, COMPILE_EXCLUDE_PATTERNS):
        return "test_mock_not_runtime"
    return None


def upload_skip_reason(rel: str):
    rel = _posix_rel(rel)
    if _matches_any(rel, UPLOAD_EXCLUDE_PATTERNS):
        return "test_mock_not_runtime"
    return None


def forbidden_upload_reason(rel: str, src=None):
    rel = _posix_rel(rel)
    src_rel = _posix_rel(os.path.relpath(src, ROOT)) if src else ""
    if rel in SOURCE_ONLY_MPY_FILES:
        return "source_only_compiled"
    if rel.startswith("firmware/") or src_rel.startswith("build/mpy/firmware/"):
        return "wrong_firmware_root"
    if "__pycache__/" in rel or rel.endswith(".pyc") or "__pycache__/" in src_rel or src_rel.endswith(".pyc"):
        return "python_cache_not_runtime"
    return None


def _record_skip(path: str, reason: str, stage: str):
    item = {"path": _posix_rel(path), "reason": reason, "stage": stage}
    _SUMMARY["skipped_files"].append(item)
    return item


def _stale_mpy_for_source(rel: str) -> str:
    return os.path.join(MPY_DIR, rel).replace(".py", ".mpy")


def _clear_mpy_dir():
    if os.path.exists(MPY_DIR):
        shutil.rmtree(MPY_DIR)
    os.makedirs(MPY_DIR, exist_ok=True)


def compile_py_files() -> bool:
    """Compile all .py files under firmware/ to build/mpy/, preserving structure."""
    print("[compile] Compiling .py → .mpy ...")
    step = {"type": "compile", "status": "running", "files": [], "skipped": []}
    _SUMMARY["steps"].append(step)
    _clear_mpy_dir()
    if not check_mpy_cross():
        print("[WARNING] mpy-cross not found. Install: pip install mpy-cross")
        print("          Skipping compilation (use .py directly).")
        step["status"] = "skipped"
        step["reason"] = "mpy-cross not found"
        return True

    py_files = []
    for root, dirs, files in os.walk(FIRMWARE_DIR):
        for f in files:
            if not f.endswith(".py"):
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, FIRMWARE_DIR).replace("\\", "/")
            reason = compile_skip_reason(rel)
            if reason:
                stale = _stale_mpy_for_source(rel)
                if os.path.exists(stale):
                    os.remove(stale)
                step["skipped"].append(_record_skip(rel, reason, "compile"))
                continue
            py_files.append(src)

    if not py_files:
        print("[compile] No .py files found under firmware/")
        step["status"] = "skipped"
        step["reason"] = "no python files"
        return True

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
        item = {
            "source": os.path.relpath(src, FIRMWARE_DIR).replace("\\", "/"),
            "target": os.path.relpath(dest, ROOT).replace("\\", "/"),
            "returncode": result.returncode,
            "stderr": result.stderr.decode(errors="replace")[-1000:],
        }
        step["files"].append(item)
        if result.returncode == 0:
            _SUMMARY["compiled_files"].append(item["target"])
            print("  OK  {}".format(rel))
        else:
            _mark_failed("mpy_cross_failed", "mpy-cross failed", **item)
            print("  FAIL  {}: {}".format(rel, result.stderr.decode().strip()))

    print("[compile] Done → build/mpy/")
    if step["status"] == "running":
        step["status"] = "success" if _SUMMARY["status"] == "success" else "failed"
    return step["status"] != "failed"


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


def _remote_parent_dirs(rel_path: str) -> list[str]:
    rel_dir = os.path.dirname(rel_path.replace("\\", "/")).strip("/")
    if not rel_dir:
        return []
    parts = [part for part in rel_dir.split("/") if part]
    return [":{}".format("/".join(parts[:index])) for index in range(1, len(parts) + 1)]


def _ensure_remote_dirs(rel_path: str):
    for remote_dir in _remote_parent_dirs(rel_path):
        _mpremote(["resume", "fs", "mkdir", remote_dir], check=False)


def _upload_file(src: str, rel: str):
    remote = ":{}".format(_posix_rel(rel))
    _ensure_remote_dirs(rel)
    _mpremote(["resume", "fs", "cp", src, remote])
    size_kb = os.path.getsize(src) / 1024
    _SUMMARY["uploaded_files"].append(
        {"source": os.path.relpath(src, ROOT).replace("\\", "/"), "target": remote}
    )
    print("  OK  {}  ({:.1f} KB)".format(remote, size_kb))


def _upload_dir(source_dir: str, label: str):
    """Upload all files from source_dir to device."""
    for root, dirs, files in os.walk(source_dir):
        for f in files:
            if f == ".gitkeep":
                continue
            src = os.path.join(root, f)
            rel = os.path.relpath(src, source_dir).replace("\\", "/")
            forbidden = forbidden_upload_reason(rel, src)
            if forbidden:
                _mark_failed(
                    "forbidden_upload_artifact",
                    "refusing to upload non-runtime or wrong-root artifact",
                    source=os.path.relpath(src, ROOT).replace("\\", "/"),
                    target=":{}".format(_posix_rel(rel)),
                    reason=forbidden,
                )
                print("[ERROR] refusing to upload {}: {}".format(rel, forbidden))
                sys.exit(1)
            reason = upload_skip_reason(rel)
            if reason:
                _record_skip(rel, reason, "upload")
                continue

            try:
                _upload_file(src, rel)
            except SystemExit:
                print("[ERROR] upload failed: {}".format(f))
                sys.exit(1)


def upload_files():
    """Upload .mpy (or .py) files to device, with source-only files always from firmware/.

    When build/mpy/ exists, uploads .mpy from there plus source-only files from firmware/.
    Otherwise falls back to uploading all .py from firmware/.
    """
    use_mpy = os.path.exists(MPY_DIR) and os.listdir(MPY_DIR)

    if use_mpy:
        print("[upload] Source: build/mpy/ + firmware/{main,boot,conf}.py → device")
        _SUMMARY["steps"].append({"type": "upload_source", "source": "build/mpy + source-only py"})
        _upload_dir(MPY_DIR, "mpy")
        # Always upload source-only files as .py from firmware.
        for entry in sorted(SOURCE_ONLY_FILES):
            src = os.path.join(FIRMWARE_DIR, entry)
            if os.path.exists(src):
                try:
                    _upload_file(src, entry)
                except SystemExit:
                    print("[ERROR] upload failed: {}".format(entry))
                    sys.exit(1)
    else:
        print("[upload] Source: firmware/ → device (no .mpy available)")
        _SUMMARY["steps"].append({"type": "upload_source", "source": "firmware"})
        _upload_dir(FIRMWARE_DIR, "py")

    print("[upload] Done")
    _SUMMARY["steps"].append({"type": "upload", "status": "success"})


def reset_device():
    """Soft-reset the device to restart MicroPython interpreter."""
    print("[reset] Soft-resetting device...")
    try:
        _mpremote(["soft-reset"])
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="MicroPython project deploy tool")
    parser.add_argument("--port", default="", help="Serial port (auto-detect if empty)")
    parser.add_argument("--compile", action="store_true", help="Compile .py → .mpy")
    parser.add_argument("--flash", action="store_true", help="Flash firmware to device")
    parser.add_argument("--upload", action="store_true", help="Upload project files to device")
    parser.add_argument("--all", action="store_true", help="Compile + flash + upload")
    parser.add_argument("--no-reset", action="store_true", help="Skip device reset after upload")
    parser.add_argument("--json-summary", action="store_true", help="Print structured JSON summary as the final line")
    parser.add_argument("--summary-file", help="Write structured JSON summary to a file")
    return parser.parse_args()


def run(args) -> int:
    global _COM_PORT

    if not any([args.compile, args.flash, args.upload, args.all]):
        _mark_failed("no_action", "choose at least one of --compile, --flash, --upload, or --all")
        return 1

    do_all = args.all
    do_compile = args.compile or do_all
    do_flash = args.flash or do_all
    do_upload = args.upload or do_all

    _COM_PORT = args.port or select_com_port()
    _SUMMARY["port"] = _COM_PORT
    print("[info] Using port: {}".format(_COM_PORT))

    if do_flash:
        flash_firmware()

    if do_compile:
        if not compile_py_files():
            return 2

    if do_upload:
        upload_files()
        if not args.no_reset:
            reset_device()

    if do_all:
        print("\n" + "=" * 50)
        print("  Deploy complete!")
        print("=" * 50)
    return 0 if _SUMMARY["status"] == "success" else 2


def main() -> int:
    args = parse_args()
    exit_code = 0
    try:
        exit_code = run(args)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
        if exit_code and _SUMMARY["status"] == "success":
            _mark_failed("script_exit", "script exited before deploy completed", detail=str(exc))
    except Exception as exc:
        exit_code = 1
        _mark_failed("unhandled_exception", str(exc))
        print("[ERROR] {}".format(exc))
    _emit_summary(args, exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
