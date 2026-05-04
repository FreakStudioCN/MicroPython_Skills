---
name: mpremote Device Interaction
description: Use this skill for general MicroPython device interaction via mpremote, including connecting, running code, checking device state, and managing the device. Triggers on "connect to micropython", "run code on device", "check device state", "mpremote", "micropython device", "repl", "device version", "device reset", "连接设备", "在设备上运行代码", "查看设备状态".
---

# MicroPython Device Interaction with mpremote

## Connection basics

mpremote is the standard tool for interacting with MicroPython devices over USB serial.

### Device identification — Windows (COMn)

On Windows, devices appear as `COMn` ports. Use `mpremote connect list` to discover them:

```bash
# List all available devices
mpremote connect list
# Example output:
# COM3  USB VID:PID=2E8A:0005 SER=... LOCATION=...

# Connect using shortcut (c0=COM0, c1=COM1, ...)
mpremote c3
mpremote c3 resume exec "import sys; print(sys.version)"

# Or explicit
mpremote connect COM3 resume
mpremote connect COM3 resume exec "..."
```

Never use device index shortcuts (`a0`, `u0`) on Windows — those are Linux paths.

### Device identification — macOS (without mpy-dev)

On macOS, devices appear as `/dev/tty.usbmodem*` or `/dev/tty.usbserial*`:

```bash
# List available devices
mpremote connect list
# or inspect directly
ls /dev/tty.usb*

# Connect using the full path
mpremote connect /dev/tty.usbmodem1101 resume
mpremote connect /dev/tty.usbmodem1101 resume exec "..."

# mpremote shorthand if it resolves (ACM-style devices)
mpremote a0 resume
```

Use the full `/dev/tty.usbmodem*` path in scripts — it is stable for a given USB slot on macOS.

### Device identification — Linux with mpy-dev (preferred)

The preferred way to identify devices on Linux is via `mpy-dev`, a USB serial device registry.

**Install:**
```bash
uv tool install mpy-dev          # preferred
# or: pip install mpy-dev
# or from source: uv tool install git+https://gitlab.com/alelec/mpy-dev.git
```

**Usage:**
```bash
# List all registered devices with connection status
mpy-dev list

# Get the serial path for a named device
mpy-dev tty pico-w
# Output: /dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_e6614c311b7e6f35-if00

# Use with mpremote (compose via subshell)
mpremote connect $(mpy-dev tty pico-w) resume

# Register a new device
mpy-dev register my-board         # interactive: scans and lets you pick
mpy-dev register my-board --device <serial>  # by USB serial number
```

### Manual device identification — Linux (without mpy-dev)

If mpy-dev is not available, use `/dev/serial/by-id/` paths directly:
```bash
# List available serial devices
ls /dev/serial/by-id/

# Connect using stable path
mpremote connect /dev/serial/by-id/usb-FTDI_TTL232RG-VREG1V8_FT55TKQB-if00-port0 resume
```

Never use `/dev/ttyUSB0` etc. on Linux — these change on reconnection.

### The `resume` subcommand

`resume` connects to the device without interrupting the running application. This is critical for devices running asyncio event loops:

```bash
# Linux (mpy-dev)
mpremote connect $(mpy-dev tty my-board) resume

# macOS
mpremote connect /dev/tty.usbmodem1101 resume

# Windows
mpremote connect COM3 resume
```

Without `resume`, mpremote sends a soft reset (Ctrl+D) which restarts the application.

## Running code on the device

### Single expression

```bash
mpremote <device> resume exec "import machine; print(machine.freq())"
```

Replace `<device>` with `connect COM3` (Windows), `connect /dev/tty.usbmodem1101` (macOS), or `connect $(mpy-dev tty my-board)` (Linux).

### Multi-line code

```bash
mpremote <device> resume exec "
import os
for f in os.listdir('/'):
    print(f)
"
```

### Running a local script

```bash
mpremote <device> resume run my_script.py
```

The script runs on the device but is NOT saved to the filesystem.

## Checking device state

### Firmware version
```bash
mpremote <device> resume exec "import sys; print(sys.version)"
# Or for detailed build info:
mpremote <device> resume exec "import os; print(os.uname())"
```

### CPU frequency
```bash
mpremote <device> resume exec "import machine; print(machine.freq())"
```

### Reset cause
```bash
mpremote <device> resume exec "import machine; print(machine.reset_cause())"
```

### Free memory
```bash
mpremote <device> resume exec "import gc; gc.collect(); print(gc.mem_free())"
```

### Filesystem contents
```bash
mpremote <device> resume fs ls :
mpremote <device> resume fs ls :data/
mpremote <device> resume fs tree
```

### Available flash space
```bash
mpremote <device> resume exec "import os; s=os.statvfs('/'); print(f'{s[0]*s[3]} bytes free')"
```

## Device management

### Soft reset (restart application)
```bash
mpremote <device> soft-reset
```
Note: no `resume` here since we want the reset.

### Enter interactive REPL
```bash
mpremote <device> resume
```

Exit with Ctrl-] or Ctrl-x.

### Check for stale processes (Linux/macOS only)

If mpremote fails with "failed to access", check for processes holding the port:
```bash
# Linux
fuser /dev/serial/by-id/<device-id>
fuser -k /dev/serial/by-id/<device-id>

# macOS
lsof /dev/tty.usbmodem1101
kill <pid>
```

On Windows, close any other serial terminal (PuTTY, Thonny, Arduino IDE) that may hold the port.

## Important caveats

### Ctrl+C and asyncio

`mpremote resume exec` sends Ctrl+C to enter raw REPL mode. On devices with a running application, this will raise `KeyboardInterrupt` and kill the application. For repeated command execution, use a persistent PTY session instead (see the mpremote-live-session skill).

### Filesystem module shadows

Python files on the device filesystem override frozen modules of the same name. If the device behaves unexpectedly after flashing new firmware, check for stale `.py` files:

```bash
mpremote <device> resume fs ls :
# Remove stale files if needed:
mpremote <device> resume fs rm :device_override.py
```

## Patterns for common tasks

### Query and display device info

```bash
mpremote <device> resume exec "
import machine, gc, os
gc.collect()
print('Freq:', machine.freq())
print('Free mem:', gc.mem_free())
s = os.statvfs('/')
print('Free flash:', s[0]*s[3], 'bytes')
print('Files:', len(os.listdir('/')))
"
```

### Batch operations

When running multiple mpremote commands in sequence, add a brief sleep between them:

```bash
# Linux/macOS
mpremote <device> resume exec "print('step 1')"
sleep 1
mpremote <device> resume exec "print('step 2')"

# Windows (PowerShell)
mpremote connect COM3 resume exec "print('step 1')"
Start-Sleep -Seconds 1
mpremote connect COM3 resume exec "print('step 2')"

# Windows (cmd)
mpremote connect COM3 resume exec "print('step 1')"
timeout /t 1 /nobreak >nul
mpremote connect COM3 resume exec "print('step 2')"
```
