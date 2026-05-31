#!/usr/bin/env python3
"""Read rotating log files from a MicroPython device via mpremote.

Usage:
    python read_device_log.py                      # read all logs
    python read_device_log.py --tail 50            # last 50 lines only
    python read_device_log.py --clear              # delete all log files
"""

import subprocess
import sys
import argparse

_PORT: str = ""


def _mpremote(cmd, **kwargs):
    full = ["mpremote"]
    if _PORT:
        full += ["connect", _PORT]
    return subprocess.run(full + cmd, **kwargs)


def get_file_mtime(index):
    result = _mpremote(
        ["exec", "import os; print(os.stat('/log/run_{}.log')[8])".format(index)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        try:
            return int(result.stdout.strip().split("\n")[-1])
        except ValueError:
            return None
    return None


def read_file_content(index):
    result = _mpremote(
        ["fs", "cat", ":/log/run_{}.log".format(index)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout
    return ""


def delete_log_file(index):
    result = _mpremote(
        ["exec",
         "try:\n import os; os.remove('/log/run_{}.log'); print('ok')\n"
         "except Exception as e: print('err', e)".format(index)],
        capture_output=True, text=True,
    )
    return result.returncode == 0 and "ok" in result.stdout


def clear_all_logs():
    found = False
    for i in range(8):
        mtime = get_file_mtime(i)
        if mtime is not None:
            found = True
            if delete_log_file(i):
                print("[info] deleted /log/run_{}.log".format(i))
            else:
                print("[error] failed to delete /log/run_{}.log".format(i), file=sys.stderr)
    if not found:
        print("[info] no log files to delete")


def read_logs(port="", tail=None):
    global _PORT
    _PORT = port

    files = []
    for i in range(8):
        mtime = get_file_mtime(i)
        if mtime is not None:
            files.append((i, mtime))

    if not files:
        return "[error] no log files found"

    files.sort(key=lambda x: x[1])
    all_lines = []
    for i, mtime in files:
        content = read_file_content(i)
        if content:
            all_lines.extend(content.splitlines())

    if tail:
        all_lines = all_lines[-tail:]

    return "\n".join(all_lines)


def clear_device_logs(port=""):
    global _PORT
    _PORT = port
    clear_all_logs()


def main():
    parser = argparse.ArgumentParser(description="Read rotating logs from MPY device")
    parser.add_argument("--port", default="", help="Serial port (e.g. COM81), auto-detect if empty")
    parser.add_argument("--tail", type=int, help="Show last N lines only")
    parser.add_argument("--clear", action="store_true", help="Delete all device log files")
    args = parser.parse_args()

    if args.clear:
        clear_device_logs(args.port)
        return

    output = read_logs(args.port, args.tail)
    print(output)


if __name__ == "__main__":
    main()
