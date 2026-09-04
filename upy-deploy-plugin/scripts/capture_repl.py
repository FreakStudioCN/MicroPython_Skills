#!/usr/bin/env python3
"""Capture MicroPython REPL output through a persistent mpremote session."""

from __future__ import annotations

import argparse
import os
import select
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import configure_stdio, print_json, write_json
from mpremote_runtime import MpremoteUnavailable, popen_mpremote


SOFT_REBOOT_MARKER = "MPY: soft reboot"
# The scaffold prints this after hardware init, so seeing it INSIDE a capture window means the
# firmware started during the window: the board came up fresh, it was not already running.
FRESH_BOOT_MARKER = "MPYHW_READY"


def observed_soft_reboot(output: str) -> bool:
    return SOFT_REBOOT_MARKER in output


def observed_fresh_boot(output: str) -> bool:
    """True when the deployed firmware started up inside this capture.

    Some boards do not show SOFT_REBOOT_MARKER even though the firmware restarted during the
    capture. The scaffold startup marker is separate evidence that the deployed app began inside
    this capture window.

    This does not weaken the check it stands in for. The case that field exists to reject is a
    capture that attached to an app already running mid-loop; such a capture holds task output but
    no startup marker, because the firmware printed it before the capture opened.
    """
    return FRESH_BOOT_MARKER in output


def capture_mock(duration_ms: int, reset_first: bool = False, mock_traceback: bool = False) -> dict[str, Any]:
    if mock_traceback:
        lines = [
            "MPY: soft reboot",
            "Traceback (most recent call last):",
            "  File \"main.py\", line 94, in <module>",
            "ValueError: invalid Timer number",
        ]
    else:
        lines = [
            "MPY: soft reboot" if reset_first else "MPYHW_READY demo",
            "[sensor] value=23.5",
            "starting scheduler",
        ]
    time.sleep(min(duration_ms, 50) / 1000)
    return {
        "status": "success",
        "mode": "mock",
        "output": "\n".join(lines) + "\n",
        "duration_ms": min(duration_ms, 50),
        "stalled": False,
        "matched_stop": "starting scheduler",
        "reset_first": reset_first,
        "observed_soft_reboot": observed_soft_reboot("\n".join(lines)),
        "observed_fresh_boot": observed_fresh_boot("\n".join(lines)),
    }


# A running main.py has to be INTERRUPTED before it can be soft rebooted. Ctrl-D only reboots an
# idle REPL; a board running an app swallows it, which is the state a successful deploy leaves the
# board in. So Ctrl-C first, then Ctrl-D.
#
# And both have to arrive after mpremote is attached. Sent immediately after spawn they can land
# ahead of the "Connected to MicroPython" banner and be echoed into nothing.
_ATTACH_MARKERS = ("Connected to MicroPython", "Use Ctrl-]")
# If the banner never arrives (a board mid-boot, a port that prints nothing), reset anyway rather
# than silently skipping it: no worse than the previous behaviour, and the capture still records
# whether a reboot was observed.
_ATTACH_FALLBACK_S = 3.0
# Long enough for the KeyboardInterrupt traceback and a fresh prompt before the Ctrl-D lands.
_INTERRUPT_SETTLE_S = 0.4


def _attached(text: str) -> bool:
    return any(marker in text for marker in _ATTACH_MARKERS)


def _trigger_soft_reset(proc: subprocess.Popen[bytes]) -> None:
    if proc.stdin is None:
        return
    try:
        proc.stdin.write(b"\x03")
        proc.stdin.flush()
        time.sleep(_INTERRUPT_SETTLE_S)
        proc.stdin.write(b"\x04")
        proc.stdin.flush()
    except Exception:
        return


def _trigger_soft_reset_fd(master_fd: int) -> None:
    try:
        os.write(master_fd, b"\x03")
        time.sleep(_INTERRUPT_SETTLE_S)
        os.write(master_fd, b"\x04")
    except OSError:
        return


def capture_windows(
    port: str,
    duration_ms: int,
    stop_patterns: list[str],
    reset_first: bool = False,
    no_resume: bool = False,
) -> dict[str, Any]:
    mpremote_args = ["repl"] if no_resume else ["resume", "repl"]
    proc = popen_mpremote(
        port,
        mpremote_args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    chunks: list[str] = []
    matched_stop = None
    last_output = time.monotonic()
    done = threading.Event()

    def reader() -> None:
        nonlocal matched_stop, last_output
        assert proc.stdout is not None
        while not done.is_set():
            chunk = proc.stdout.readline()
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            chunks.append(text)
            last_output = time.monotonic()
            for pattern in stop_patterns:
                if pattern and pattern in text:
                    matched_stop = pattern
                    done.set()
                    break

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + duration_ms / 1000
    reset_pending = reset_first
    attach_deadline = time.monotonic() + _ATTACH_FALLBACK_S
    while time.monotonic() < deadline and not done.is_set():
        if reset_pending and (_attached("".join(chunks)) or time.monotonic() >= attach_deadline):
            _trigger_soft_reset(proc)
            reset_pending = False
        time.sleep(0.05)
    done.set()
    try:
        proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
    output = "".join(chunks)
    return {
        "status": "success",
        "mode": "windows_pipe",
        "output": output,
        "duration_ms": duration_ms,
        "stalled": bool(output) and matched_stop is None and (time.monotonic() - last_output) > max(1, duration_ms / 2000),
        "matched_stop": matched_stop,
        "returncode": proc.returncode,
        "reset_first": reset_first,
        "no_resume": no_resume,
        "observed_soft_reboot": observed_soft_reboot(output),
        "observed_fresh_boot": observed_fresh_boot(output),
    }


def capture_pty(
    port: str,
    duration_ms: int,
    stop_patterns: list[str],
    reset_first: bool = False,
    no_resume: bool = False,
) -> dict[str, Any]:
    import pty

    master_fd, slave_fd = pty.openpty()
    mpremote_args = [] if no_resume else ["resume"]
    proc = popen_mpremote(
        port,
        mpremote_args,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)
    chunks: list[str] = []
    matched_stop = None
    last_output = time.monotonic()
    deadline = time.monotonic() + duration_ms / 1000
    reset_pending = reset_first
    attach_deadline = time.monotonic() + _ATTACH_FALLBACK_S
    try:
        while time.monotonic() < deadline:
            if reset_pending and (_attached("".join(chunks)) or time.monotonic() >= attach_deadline):
                _trigger_soft_reset_fd(master_fd)
                reset_pending = False
            ready, _, _ = select.select([master_fd], [], [], 0.1)
            if not ready:
                continue
            try:
                chunk = os.read(master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            chunks.append(text)
            last_output = time.monotonic()
            for pattern in stop_patterns:
                if pattern and pattern in text:
                    matched_stop = pattern
                    output = "".join(chunks)
                    return {
                        "status": "success",
                        "mode": "pty",
                        "output": output,
                        "duration_ms": int(duration_ms - max(0, deadline - time.monotonic()) * 1000),
                        "stalled": False,
                        "matched_stop": matched_stop,
                        "reset_first": reset_first,
                        "no_resume": no_resume,
                        "observed_soft_reboot": observed_soft_reboot(output),
                        "observed_fresh_boot": observed_fresh_boot(output),
                    }
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
        os.close(master_fd)
    output = "".join(chunks)
    return {
        "status": "success",
        "mode": "pty",
        "output": output,
        "duration_ms": duration_ms,
        "stalled": bool(output) and matched_stop is None and (time.monotonic() - last_output) > max(1, duration_ms / 2000),
        "matched_stop": matched_stop,
        "returncode": proc.returncode,
        "reset_first": reset_first,
        "no_resume": no_resume,
        "observed_soft_reboot": observed_soft_reboot(output),
        "observed_fresh_boot": observed_fresh_boot(output),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="")
    parser.add_argument("--duration-ms", type=int, default=60000)
    parser.add_argument("--timeout-ms", type=int, default=None, help="Compatibility alias for --duration-ms")
    parser.add_argument("--stop-pattern", action="append", default=["MPYHW_READY", "starting scheduler"])
    parser.add_argument("--reset-first", action="store_true", help="Enter REPL, send Ctrl-D soft reset, then capture boot output")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help=(
            "Drop the mpremote resume command from the capture invocation. Note this does NOT by "
            "itself restart a running board: resume only suppresses the auto soft reset that "
            "raw-REPL commands perform, and the capture uses the friendly REPL, which never "
            "interrupts either way. The restart comes from the Ctrl-C + Ctrl-D this script sends "
            "once mpremote has attached."
        ),
    )
    parser.add_argument("--mock-traceback", action="store_true", help="Mock mode: emit a startup traceback")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--log-file")
    args = parser.parse_args()
    if args.timeout_ms is not None:
        args.duration_ms = args.timeout_ms
    return args


def main() -> int:
    configure_stdio()
    args = parse_args()
    started = datetime.now(timezone.utc).isoformat()
    try:
        if args.mock:
            result = capture_mock(args.duration_ms, reset_first=args.reset_first, mock_traceback=args.mock_traceback)
        elif not args.port:
            raise ValueError("--port is required unless --mock is used")
        elif os.name == "nt":
            result = capture_windows(
                args.port,
                args.duration_ms,
                args.stop_pattern,
                reset_first=args.reset_first,
                no_resume=args.no_resume,
            )
        else:
            result = capture_pty(
                args.port,
                args.duration_ms,
                args.stop_pattern,
                reset_first=args.reset_first,
                no_resume=args.no_resume,
            )
    except MpremoteUnavailable as exc:
        result = {
            "status": "action_required",
            "mode": "mock" if args.mock else ("windows_pipe" if os.name == "nt" else "pty"),
            "output": "",
            "errors": [exc.to_error()],
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "mode": "mock" if args.mock else ("windows_pipe" if os.name == "nt" else "pty"),
            "output": "",
            "errors": [{"code": "capture_failed", "message": str(exc)}],
        }
    result["observed_soft_reboot"] = observed_soft_reboot(str(result.get("output") or ""))
    result["observed_fresh_boot"] = observed_fresh_boot(str(result.get("output") or ""))
    result["evidence_mode"] = "mock" if args.mock else "live"
    result.setdefault("no_resume", bool(args.no_resume))
    result["started_at"] = started
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(result.get("output", ""), encoding="utf-8")
        result["log_file"] = str(log_path).replace("\\", "/")
    if args.output_json:
        write_json(args.output_json, result)
    printable = dict(result)
    output = printable.get("output")
    if isinstance(output, str) and len(output) > 2000:
        printable["output_excerpt"] = output[:2000]
        printable["output_bytes"] = len(output.encode("utf-8", errors="replace"))
        printable.pop("output", None)
    print_json(printable)
    return 0 if result["status"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
