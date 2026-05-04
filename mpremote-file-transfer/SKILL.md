---
name: mpremote File Transfer
description: Use this skill when copying files to or from a MicroPython device using mpremote. Covers file copy syntax, directory operations, and best practices for device filesystem management. Triggers on "copy file to device", "upload to device", "download from device", "mpremote fs", "device filesystem", "copy firmware files", "上传文件到设备", "从设备下载文件", "同步文件".
---

# File Transfer with mpremote

## Basic copy operations

Copy a local file to the device:
```bash
mpremote <device> resume fs cp local_file.py :remote_file.py
```

Copy from device to host:
```bash
mpremote <device> resume fs cp :remote_file.py local_file.py
```

The colon prefix `:` denotes a device path. Without it, the path is local.

## Always use `resume`

```bash
mpremote <device> resume fs cp file.py :file.py     # Correct: no soft reset
mpremote <device> fs cp file.py :file.py             # WRONG: resets device first
```

Without `resume`, mpremote performs a soft reset before the filesystem operation, restarting the application and potentially losing state.

## Device path by platform

### Windows

```bash
# Discover port
mpremote connect list

# Copy using shortcut or explicit COM port
mpremote c3 resume fs cp main.py :main.py
mpremote connect COM3 resume fs cp main.py :main.py
```

### macOS

```bash
# Discover port
mpremote connect list
# or: ls /dev/tty.usb*

# Copy using full path (stable for a given USB slot)
mpremote connect /dev/tty.usbmodem1101 resume fs cp main.py :main.py
```

### Linux (with mpy-dev, preferred)

```bash
# Install mpy-dev if needed:
# uv tool install git+https://gitlab.com/alelec/mpy-dev.git

mpremote connect $(mpy-dev tty my-board) resume fs cp file.py :file.py
```

### Linux (without mpy-dev)

```bash
mpremote connect /dev/serial/by-id/usb-FTDI_...-port0 resume fs cp file.py :file.py
```

Never use `/dev/ttyUSB0` — it changes on reconnection.

## Device path syntax

- `:filename.py` - file in the device's current directory (root)
- `:/path/to/file` - absolute path on device
- `:data/1.data` - relative path on device

## Directory operations

List files:
```bash
mpremote <device> resume fs ls :
mpremote <device> resume fs ls :data/
```

Create directory:
```bash
mpremote <device> resume fs mkdir :data
```

Remove file:
```bash
mpremote <device> resume fs rm :device_override.py
```

Remove directory (must be empty):
```bash
mpremote <device> resume fs rmdir :old_dir
```

Recursive file tree:
```bash
mpremote <device> resume fs tree
```

## Copying multiple files

mpremote processes one operation per invocation. For multiple files, use a shell loop:

```bash
# Linux/macOS
for f in *.py; do
    mpremote <device> resume fs cp "$f" ":$f"
    sleep 0.5
done

# Windows PowerShell
foreach ($f in Get-ChildItem *.py) {
    mpremote connect COM3 resume fs cp $f.Name ":$($f.Name)"
    Start-Sleep -Milliseconds 500
}
```

The brief pause is important — mpremote holds the serial port during the copy and the next invocation needs it released.

## Large file transfers

For files >50KB, the transfer takes several seconds. mpremote uses the raw REPL protocol for `fs cp`, which sends Ctrl+C on entry. On asyncio/aiorepl devices, this can crash the event loop.

For large transfers to asyncio devices, consider:
1. Transfer while the device is in a safe state (e.g. on dock, not collecting data)
2. Accept that the transfer may restart the application
3. Use the persistent session approach for very large batch transfers (see mpremote-live-session skill)

## Filesystem capacity

Check available space:
```bash
mpremote <device> resume exec "import os; print(os.statvfs('/'))"
```

The result tuple fields: `(bsize, frsize, blocks, bfree, ...)`. Available bytes = `bsize * bfree`.

## Common patterns

### Driver development workflow: update + restart + monitor

```bash
# Linux/macOS
mpremote <device> resume fs cp utils/driver.py :utils/driver.py + soft-reset repl

# Windows PowerShell
mpremote connect COM3 resume fs cp utils/driver.py :utils/driver.py + soft-reset repl
```

### Deploy a Python module and reboot

```bash
mpremote <device> resume fs cp device_override.py :device_override.py
mpremote <device> resume fs ls :
mpremote <device> resume exec "import machine; machine.reset()"
```

### Recursive directory sync

```bash
mpremote <device> resume fs cp -r utils/ :utils/ + soft-reset repl
```

### Back up device data (Linux/macOS)

```bash
mkdir -p backup/data
for f in $(mpremote <device> resume fs ls :data/ | awk '{print $NF}'); do
    mpremote <device> resume fs cp ":data/$f" "backup/data/$f"
    sleep 0.5
done
```

### Clean device filesystem

```bash
mpremote <device> resume exec "
import os
for f in os.listdir('data'):
    os.remove('data/' + f)
    print('removed', f)
"
```

## Troubleshooting

**"failed to access" / port in use (Linux/macOS)**: Check with `fuser /dev/serial/by-id/<id>` or `lsof /dev/tty.usbmodem*` and kill stale processes.

**Port in use (Windows)**: Close Thonny, PuTTY, Arduino IDE, or any other serial terminal that may hold the COM port.

**Transfer seems to hang**: Large files take time. A 70KB file takes ~3 seconds. Don't interrupt — partial writes corrupt the filesystem.

**File appears but content is wrong**: After writing, either reboot or call `os.sync()` from the REPL.
