#!/usr/bin/env python3
"""Read rotating log files from a MicroPython device via mpremote.

Usage:
    python read_device_log.py                              # cat all logs to stdout
    python read_device_log.py --tail 50                    # last N lines only
    python read_device_log.py --download ./deploy_logs/    # download .log files to local dir
    python read_device_log.py --clear                      # delete all log files
    python read_device_log.py --log-dir /data/logs         # custom log directory on device
"""

import subprocess
import sys
import os
import argparse

_PORT: str = ""


def _mpremote(cmd, **kwargs):
    full = ["mpremote"]
    if _PORT:
        full += ["connect", _PORT, "resume"]
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    return subprocess.run(full + cmd, **kwargs)


def list_log_files(log_dir):
    """List run_*.log files in log_dir via fs ls, returning sorted (index, filename) pairs."""
    result = _mpremote(
        ["fs", "ls", ":{}".format(log_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    files = []
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        fname = parts[-1]
        if fname.startswith("run_") and fname.endswith(".log"):
            try:
                idx = int(fname.replace("run_", "").replace(".log", ""))
                files.append((idx, fname))
            except ValueError:
                pass
    return sorted(files)


def cat_log_content(log_dir, filename):
    """Read log file content via fs cat, return string."""
    result = _mpremote(
        ["fs", "cat", ":{}/{}".format(log_dir, filename)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout
    return ""


def download_log_file(log_dir, filename, local_dir):
    """Download a log file via fs cp, return True on success."""
    remote = ":{}/{}".format(log_dir, filename)
    local = os.path.join(local_dir, filename)
    result = _mpremote(
        ["fs", "cp", remote, local],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def delete_log_file(log_dir, filename):
    result = _mpremote(
        ["fs", "rm", ":{}/{}".format(log_dir, filename)],
        capture_output=True, text=True,
    )
    return result.returncode == 0


def clear_all_logs(log_dir):
    files = list_log_files(log_dir)
    if not files:
        print("[info] no log files to delete")
        return
    for idx, fname in files:
        if delete_log_file(log_dir, fname):
            print("[info] deleted {}/{}".format(log_dir, fname))
        else:
            print("[error] failed to delete {}/{}".format(log_dir, fname), file=sys.stderr)


def read_logs(port="", log_dir="/log", tail=None):
    global _PORT
    _PORT = port

    files = list_log_files(log_dir)
    if not files:
        return "[error] no log files found in {}".format(log_dir)

    all_lines = []
    for idx, fname in files:
        content = cat_log_content(log_dir, fname)
        if content:
            all_lines.extend(content.splitlines())

    if tail:
        all_lines = all_lines[-tail:]

    return "\n".join(all_lines)


def download_logs(port="", log_dir="/log", output_dir=""):
    global _PORT
    _PORT = port

    files = list_log_files(log_dir)
    if not files:
        print("[error] no log files found in {}".format(log_dir), file=sys.stderr)
        return False

    os.makedirs(output_dir, exist_ok=True)
    ok = 0
    for idx, fname in files:
        if download_log_file(log_dir, fname, output_dir):
            local = os.path.join(output_dir, fname)
            size = os.path.getsize(local)
            print("  OK  {}  ({} bytes)".format(fname, size))
            ok += 1
        else:
            print("  FAIL  {}".format(fname), file=sys.stderr)
    print("[info] downloaded {}/{} log files to {}".format(ok, len(files), output_dir))
    return ok > 0


def main():
    parser = argparse.ArgumentParser(description="Read rotating logs from MPY device")
    parser.add_argument("--port", default="", help="Serial port (e.g. COM3)")
    parser.add_argument("--log-dir", default="/log", help="Device log directory (default: /log)")
    parser.add_argument("--tail", type=int, help="Show last N lines only")
    parser.add_argument("--download", metavar="DIR", help="Download log files to local directory")
    parser.add_argument("--clear", action="store_true", help="Delete all device log files")
    args = parser.parse_args()

    if args.clear:
        clear_all_logs(args.log_dir)
        return

    if args.download:
        ok = download_logs(args.port, args.log_dir, args.download)
        if not ok:
            sys.exit(1)
        return

    output = read_logs(args.port, args.log_dir, args.tail)
    print(output)


if __name__ == "__main__":
    main()
