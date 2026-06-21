# Pin Assignment Log

Sample select-hw pin assignment log for ESP32-C3-DevKitM-1.

Board definition: `upy-analyze-plugin/boards/esp32-c3-devkitm.json`

## GPIO 使用汇总

- 已用 GPIO: GPIO4, GPIO5, GPIO6, GPIO7, GPIO10, GPIO11, GPIO20, GPIO21
- 未用 GPIO: GPIO0, GPIO1, GPIO2, GPIO3, GPIO8, GPIO9, GPIO12, GPIO13, GPIO18, GPIO19
- 条件/保留 GPIO: GPIO2, GPIO8, GPIO9 (strapping boot pins)
- 禁止 GPIO: (none)

## 引脚分配明细

| 器件 | 信号 | GPIO | 类型 | 总线 | 来源 |
|------|------|------|------|------|------|
| AHT20 | SDA | 5 | i2c_data | i2c0 | default_bus |
| AHT20 | SCL | 6 | i2c_clock | i2c0 | default_bus |
| HC-SR501 | OUT | 4 | gpio_in | - | auto_assigned |
| TTP223 | OUT | 7 | gpio_in | - | auto_assigned |
| INMP441 | BCK | 10 | i2s_bck | i2s0 | auto_assigned |
| INMP441 | WS | 11 | i2s_ws | i2s0 | auto_assigned |
| INMP441 | SD | 20 | i2s_data_in | i2s0 | user_wiring |
| MAX98357 | DIN | 21 | i2s_data_out | i2s0 | user_wiring |
| power | 3V3 | 3V3 | power_3v3 | - | power |
| power | GND | GND | gnd | - | power |

## 风险与备注

- GPIO4, GPIO5 属于 ADC2/WiFi 冲突引脚，仅作数字用途（gpio_in/i2c_data），不影响功能
- GPIO20, GPIO21 为 USB 串口脚，已按用户接线保留；后续调试需避免占用 USB CDC
- I2S BCK/WS 由麦克风和功放共享
