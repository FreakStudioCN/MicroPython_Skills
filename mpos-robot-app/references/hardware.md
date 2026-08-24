# Hardware profile

## Target identity

- Product: Waveshare ESP32-S3-Touch-LCD-2
- MPOS board ID: `waveshare_esp32_s3_touch_lcd_2`
- MCU/build family: ESP32-S3, `ESP32_GENERIC_S3-SPIRAM_OCT`
- Display: ST7789, 240×320, rotated by MPOS to landscape
- Touch: CST816S
- IMU: QMI8658
- Camera: optional OV5640 interface; this Skill requires it to be physically absent

Do not confuse this target with Waveshare ESP32-S3-Touch-LCD-2.1, 2.8, 2.8B, or 2.8C.

## MPOS-reserved pins

| Function | GPIO |
| --- | --- |
| LCD backlight | 1 |
| LCD SPI MOSI/MISO/SCLK | 38, 40, 39 |
| LCD DC/CS | 42, 45 |
| Touch and IMU I2C | 47, 48 |
| Battery ADC | 5 |
| Native USB | 19, 20 |
| Boot | 0 |
| UART/serial | 43, 44 |
| Octal flash/PSRAM | 26–37 |

Never assign reserved pins to servos or external audio. GPIO 47 and 48 must remain on the shared touch/IMU bus.

## Camera-reclaimed default pins

The robot defaults reuse the optional camera interface. Require no camera module to be connected.

| Robot function | GPIO |
| --- | --- |
| left_arm | 8 |
| right_arm | 9 |
| left_leg_upper | 7 |
| right_leg_upper | 14 |
| left_leg_lower | 10 |
| right_leg_lower | 15 |
| Speaker BCLK/WS/DATA | 2, 4, 6 |
| Speaker GAIN/SD | 16, 17 |
| Microphone BCLK/WS/DATA | 12, 11, 13 |

GPIO 21 remains connected to the camera control bus and is not part of the default robot profile.

## Profile rules

- Require exactly six unique `servo_id` and six expected logical joints.
- Require unique GPIO assignments across servos and audio signals.
- Reject every assignment that intersects the reserved-pin set.
- Use 50 Hz PWM and validate `min_us < center_us < max_us`.
- Clamp logical angles to the configured range and enforce `max_speed_deg_s`.
- Initialize one servo at a time during calibration; initialize all servos to their safe angle during activation.
- Save, validate, activate, and roll back as separate operations.
- Use `DisplayMetrics` for generated UI sizing; do not hardcode a portrait or landscape resolution.

## Source of truth

Recheck `internal_filesystem/lib/mpos/board/waveshare_esp32_s3_touch_lcd_2.py` if the MicroPythonOS checkout changes. Treat the repository board file as authoritative over copied documentation.
