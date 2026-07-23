# Current MicroPythonOS Board Facts

Source of truth: `/home/leeqingshui/MicroPythonOS/internal_filesystem/lib/mpos/board/*.py`, `internal_filesystem/lib/mpos/main.py`, and `MAINTAINERS.md`.

As of the current local source read, MPOS runtime board initialization exists for these physical boards:

1. Freenove ESP32-S3 Display
2. Fri3d Camp 2024 Badge
3. Fri3d Camp 2026 Badge
4. LilyGO T-Display S3
5. LilyGO T-HMI
6. LilyGO T-Watch S3 Plus
7. LilyGo T4
8. M5Stack Core2
9. M5Stack Fire
10. Makerfabs MaTouch ESP32-S3 SPI IPS 2.8" with Camera OV3660
11. Hardkernel ODROID-GO
12. unPhone / unPhone 9
13. SQUiXL
14. DFRobot UniHiker K10
15. Waveshare ESP32-S3-Touch-LCD-2

Non-physical or helper targets:

- `linux.py`: Linux / macOS SDL desktop target.
- `web`: WebAssembly browser target from build scripts, not a board.
- `pinstates.py`: GPIO state helper, not a board.
- `qemu.py`: listed in `MAINTAINERS.md` but not present in current board directory and not returned by `detect_board()`.
- `lvgl_micropython/display_configs/LilyGo-TDeck`: upstream/custom display config exists, but no matching `mpos.board.lilygo_tdeck.py` runtime module in current MPOS source.

Build targets are not one-to-one with boards. Current hardware build targets include:

```text
esp32
esp32-small
esp32s3
unphone
lilygo_t4
```

Most ESP32-S3 boards use the generic `esp32s3` build and are detected at runtime.
