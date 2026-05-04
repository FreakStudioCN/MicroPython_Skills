---
name: mpremote Live Session
description: Use this skill when maintaining a persistent interactive connection to a MicroPython device for sending commands and capturing output. This is the PREFERRED method for device interaction when multiple commands need to be sent, when monitoring device output over time, or when the device runs an asyncio event loop with aiorepl. Triggers on "send commands to device", "monitor device output", "interactive session", "persistent connection", "stress test device", "capture serial output", "持续监听设备", "长连接设备", "监控串口输出".
---

# Persistent mpremote Session

## CRITICAL: Never use repeated `mpremote resume exec` calls

Each `mpremote resume exec` invocation sends Ctrl+C to enter raw REPL mode. On devices running an asyncio event loop, this raises `KeyboardInterrupt` which is a `BaseException` — not caught by asyncio's `except (CancelledError, Exception)` handler. This kills the event loop, leaving the device in a zombie state where C-level tasks (SPI, GC, timers) continue but no Python asyncio task runs.

**Always use a persistent session instead.**

## Platform support

| Approach | Linux | macOS | Windows |
|---|---|---|---|
| PTY (pty module) | ✅ | ✅ | ❌ not available |
| pexpect | ✅ | ✅ | ⚠️ via wexpect |
| Direct mpremote repl pipe | ✅ | ✅ | ✅ (limited) |

For Windows, see the [Windows alternative](#windows-alternative-direct-pipe) section below.

## The PTY approach (Linux / macOS)

mpremote's REPL mode requires a real terminal (it calls `termios.tcgetattr` on stdin). When driving it from a script, create a PTY pair:

```python
import os, pty, select, signal, sys, time

# macOS: use full /dev/tty.usbmodem* path
# Linux: use /dev/serial/by-id/... path (or mpy-dev tty <name>)
# Example:
DEVICE = "/dev/tty.usbmodem1101"           # macOS
# DEVICE = "/dev/serial/by-id/usb-..."    # Linux stable path
# DEVICE = subprocess.check_output(["mpy-dev", "tty", "my-board"]).decode().strip()  # Linux mpy-dev

# Create PTY pair and fork mpremote
master_fd, slave_fd = pty.openpty()
pid = os.fork()
if pid == 0:
    # Child: mpremote gets the slave PTY as its terminal
    os.close(master_fd)
    os.setsid()
    os.dup2(slave_fd, 0)
    os.dup2(slave_fd, 1)
    os.dup2(slave_fd, 2)
    if slave_fd > 2:
        os.close(slave_fd)
    os.execvp("mpremote", ["mpremote", "connect", DEVICE, "resume"])
    sys.exit(1)

# Parent: communicate via master_fd
os.close(slave_fd)
```

## Sending commands (Linux / macOS PTY)

Write Python code as text lines to the master fd. The aiorepl prompt accepts raw text input:

```python
def send_cmd(cmd):
    """Send a Python command to the aiorepl prompt."""
    os.write(master_fd, (cmd + "\r\n").encode())
    time.sleep(0.3)  # Let aiorepl process
    return read_output(timeout=1.0)
```

## Reading output (Linux / macOS PTY)

Use `select.select()` on the master fd to read device output without blocking:

```python
def read_output(timeout=0.1):
    """Read available output from the device."""
    text = ""
    while True:
        ready, _, _ = select.select([master_fd], [], [], timeout)
        if not ready:
            break
        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        text += chunk.decode("utf-8", errors="replace")
        timeout = 0.01  # Drain quickly once data flows
    return text
```

## Logging output (Linux / macOS PTY)

Tee all device output to both stdout and a log file:

```python
def read_and_log(log_fh, timeout=0.1):
    text = read_output(timeout)
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()
        log_fh.write(text)
        log_fh.flush()
    return text
```

## Cleanup (Linux / macOS PTY)

Always terminate mpremote on exit:

```python
import signal

def cleanup():
    try:
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
    except Exception:
        pass
    os.close(master_fd)
```

## Windows alternative: direct pipe

On Windows, `pty` and `os.fork()` are not available. Use `subprocess` with `mpremote repl` and `pyserial` directly, or run mpremote as a subprocess and communicate via stdin/stdout:

```python
import subprocess, threading, time

# Windows: use COMn port
DEVICE = "COM3"

proc = subprocess.Popen(
    ["mpremote", "connect", DEVICE, "resume", "repl"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=0,
)

def reader():
    for line in iter(proc.stdout.readline, b""):
        print(line.decode("utf-8", errors="replace"), end="")

t = threading.Thread(target=reader, daemon=True)
t.start()

def send_cmd(cmd):
    proc.stdin.write((cmd + "\r\n").encode())
    proc.stdin.flush()
    time.sleep(0.3)

# Usage
send_cmd("import sys; print(sys.version)")
time.sleep(1)

proc.terminate()
```

> **Note:** The subprocess pipe approach on Windows has limitations — it does not provide a real TTY so some mpremote REPL features (escape sequences, Ctrl+C forwarding) may behave differently. For simple command injection and output capture it is sufficient.

## When to use this vs mpremote exec

| Scenario | Approach |
|---|---|
| Single quick query | `mpremote <device> resume exec "print(...)"` |
| Multiple commands over time | Persistent session |
| Monitoring device output | Persistent session |
| Device runs asyncio/aiorepl | Persistent session (REQUIRED) |
| Stress testing | Persistent session |
| File copy operations | Direct `mpremote <device> resume fs cp` |

## The `resume` subcommand

Always use `resume` when connecting to a running device. Without it, mpremote performs a soft reset which restarts the application:

```
mpremote connect <device> resume        # Correct: connects without interrupting
mpremote connect <device>               # WRONG: soft-resets the device
```

## aiorepl vs raw_repl

MicroPython devices with asyncio typically run aiorepl, which provides an interactive REPL integrated with the asyncio event loop. Two modes:

- **aiorepl prompt** (typing text): Commands execute within the running event loop. No Ctrl+C sent. Safe for asyncio devices. The persistent session uses this mode.
- **raw_repl** (Ctrl+A protocol): Used by `mpremote exec`. Sends Ctrl+C first, which can kill the event loop.

## Detecting stalls

Monitor `last_output_time` to detect when the device stops producing output:

```python
STALL_TIMEOUT = 45  # seconds
last_output_time = time.time()

def is_stalled():
    return time.time() - last_output_time > STALL_TIMEOUT
```
