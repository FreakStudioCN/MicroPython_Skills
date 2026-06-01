---
name: upy-select-hw
description: 第二步——MCU 选型 + 固件核验 + 引脚分配 + BOM 生成。输入 upy-analyze 的 project-manifest.json，输出完整的硬件方案。触发：upy-analyze 完成后自动进入。
---

# 硬件选型与引脚分配 Skill

## 角色定位

给定 `project-manifest.json`（devices + requirements + mcu_specified），完成 MCU 选型、固件核验、引脚分配、BOM 生成。**不写代码，不管驱动。**

## 前置检查

```bash
python --version
```

---

## 执行步骤

### Step 1: MCU 选型 + 固件核验

#### 情况 A：用户已指定 MCU（`mcu_specified` 有值）

```
1. 核验 MicroPython 固件是否支持：

   已知支持型号 → 直接通过（见下表）
   非常见型号 → WebSearch: site:micropython.org/download {型号}
   
   无固件 → 停止！告知用户并建议替代：
     ESP32 (最通用) / Pico (性价比) / ESP32-S3 (AI 能力)

2. 输出固件下载链接：
   URL: https://micropython.org/download/{BOARD_NAME}/
```

#### 情况 B：用户未指定 MCU → LLM 推荐

**推荐策略：优先 Pico 系列和 ESP32 系列（MPY 适配最好）。**

```
打分逻辑：

  需要 WiFi/BLE     → +1 ESP32 系列, +1 Pico W
  需要 AI/语音/摄像头 → +1 ESP32-S3
  低功耗 + 电池供电   → +1 ESP32-C3
  纯 GPIO 控制       → +1 Pico 系列
  极致低价           → +1 ESP8266 / Pico
  新手入门           → +1 Pico (USB 拖拽烧录) / ESP32

  最终推荐 Top 1，附简短理由。

  备选：Top 2（用户可切换）
```

**推荐输出示例：**

```
推荐主控：Raspberry Pi Pico W
  理由：需要 WiFi（requirements.network=wifi），RP2040 性价比高，
        MPY 适配极好，USB 拖拽烧录对新手友好。

备选：ESP32（WiFi + BLE，生态最全，接口更多）

确认使用哪个？或者指定其他型号。
```

#### 固件下载链接映射（已知型号）

| MCU | BOARD_NAME | 烧录方式 |
|-----|-----------|---------|
| ESP32 | ESP32_GENERIC | esptool.py |
| ESP32-S3 | ESP32_GENERIC_S3 | esptool.py |
| ESP32-C3 | ESP32_GENERIC_C3 | esptool.py |
| ESP32-S2 | ESP32_GENERIC_S2 | esptool.py |
| ESP32-C6 | ESP32_GENERIC_C6 | esptool.py |
| Pico | RPI_PICO | 按住 BOOTSEL 拖拽 .uf2 |
| Pico W | RPI_PICO_W | 同上 |
| Pico 2 | RPI_PICO2 | 同上 |
| Pico 2 W | RPI_PICO2_W | 同上 |
| ESP8266 | ESP8266_GENERIC | esptool.py |
| STM32F4DISC | STM32F4DISC | dfu-util |
| STM32F7DISC | STM32F7DISC | dfu-util |
| Pyboard | PYBV11 | dfu-util |
| Teensy 4.0 | TEENSY40 | Teensy Loader |
| Teensy 4.1 | TEENSY41 | Teensy Loader |

---

### Step 2: 引脚分配

#### Step 2A: 获取引脚图

```
请上传你的开发板引脚图（照片/截图/PDF 均可）。
搜索 "{MCU型号} pinout" 或 "{MCU型号} 引脚图" 即可找到。
```

若用户说"找不到" → 用 `WebSearch` 搜 `{MCU型号} pinout diagram`，取第一张图给用户确认。

#### Step 2B: LLM 多模态识别

从引脚图中提取：
- 可用 GPIO 编号列表
- 硬件 I2C 默认引脚（如 ESP32: I2C0 SCL=22 SDA=21）
- 硬件 SPI 默认引脚
- 硬件 UART 默认引脚（标注 UART0 被 REPL 占用）
- 电源引脚（3.3V, 5V, GND）位置
- 启动/烧录敏感引脚（如 ESP32: GPIO0/2/5/12/15）
- 只读引脚（如 ESP32: GPIO34-39）
- Flash/PSRAM 占用引脚（如 ESP32: GPIO6-11）

#### Step 2C: 分配引脚

**LLM 按以下规则推理分配：**

```
规则 1 — I2C 器件：
  ├─ 所有 I2C 器件挂同一条 I2C 总线（默认 I2C0）
  ├─ 地址冲突 → 用第二组 I2C（如有） 或 Software I2C（任意 GPIO）
  └─ 每条 I2C 总线占 2 个 GPIO（SCL + SDA）

规则 2 — SPI 器件：
  ├─ 共享 MOSI/MISO/SCK，每个器件独立 CS
  ├─ 用硬件 SPI 默认引脚
  └─ N 个 SPI 器件占 3 + N 个 GPIO

规则 3 — UART 器件：
  ├─ 优先 UART1/UART2（UART0 被 REPL 占用）
  └─ 每个 UART 器件占 2 个 GPIO（TX + RX）

规则 4 — GPIO 简单器件（LED/蜂鸣器/按键/继电器）：
  ├─ 优先用远离 I2C/SPI 总线的引脚
  ├─ 避开启动敏感引脚
  ├─ 避开只读引脚
  └─ 每个器件占 1 个 GPIO

规则 5 — ADC 器件：
  ├─ 只能用 ADC 引脚（如 ESP32: GPIO32-39 中的 ADC1）
  └─ 注意 ESP32 ADC2 与 WiFi 冲突

规则 6 — 冲突检测：
  ├─ 同一 GPIO 不能被分配两次
  ├─ 打印分配后引脚占用表
  └─ 标注共享引脚（如 I2C 总线上的多个器件）
```

**分配输出格式：**

```
引脚分配方案：

  I2C 总线 (I2C0):
    SCL = GPIO22, SDA = GPIO21
    器件：SHT30 (0x44), SSD1306 (0x3C), BMP280 (0x76)
    地址无冲突 ✓

  GPIO 独立：
    蜂鸣器 = GPIO4
    LED    = GPIO13

  未使用默认引脚：SPI（无 SPI 器件）

  引脚占用：6/26 GPIO
  冲突检查：通过 ✓
```

**引脚电气类型 (type) 枚举映射：**

| 引脚用途 | type 值 |
|---------|---------|
| 3.3V 电源输出 | `power_3v3` |
| 5V 电源输出 | `power_5v` |
| GND | `gnd` |
| I2C SDA | `i2c_data` |
| I2C SCL | `i2c_clock` |
| SPI MOSI | `spi_mosi` |
| SPI MISO | `spi_miso` |
| SPI SCK | `spi_sck` |
| SPI CS | `spi_cs` |
| UART TX | `uart_tx` |
| UART RX | `uart_rx` |
| GPIO 输出 (LED/蜂鸣器/继电器) | `gpio_out` |
| GPIO 输入 (按键) | `gpio_in` |
| GPIO 输入+上拉 | `gpio_in_pullup` |
| ADC 输入 | `adc` |
| PWM 输出 | `pwm` |
| I2S | `i2s` |

**物理引脚编号 (physical_pin) 获取规则：**
- Pico 系列：GP0=Pin1, GP1=Pin2, ..., GP28=Pin34；3V3(OUT)=Pin36；GND=Pin3/8/13/18/23/28/33/38
- ESP32 系列：查阅引脚图，标注 GPIO 编号对应的物理引脚编号
- 其他 MCU：从引脚图/数据手册获取

#### Step 2D: 电源引脚分配

**LLM 必须把电源引脚也写入 pinout：**

```
电源引脚分配：
  3V3(OUT) → 所有 I2C/SPI 器件的 VCC（传感器、屏幕等）
  5V(VBUS) → 需要 5V 的大功率器件（舵机、电机等）
  GND      → 所有器件的 GND（每个器件一根）

pinout 增加条目：
  {device: "电源", pin_name: "3V3(OUT)", gpio: "3V3", physical_pin: 36, type: "power_3v3", side: "right", pos: 16}
  {device: "电源", pin_name: "GND", gpio: "GND", physical_pin: 38, type: "gnd", side: "right", pos: 18}
```

---

### Step 3: BOM 生成

```
物料清单：

  #  名称          型号              数量  单价    备注
  1  主控          {MCU型号}         1    ¥{xx}   含 USB 线
  2  {器件1}       {型号}           1    ¥{xx}   {接口}
  3  {器件2}       {型号}           1    ¥{xx}   {接口}
  -  面包板        830 孔            1    ¥8      可选
  -  杜邦线        公母各 20 根       1    ¥5
  -  USB 数据线    Micro-USB         1    ¥5      （若主控不含）

  预估总价：¥{total}

  vs 用户预算：{budget_yuan}
  {超预算/预算内}
```

价格来源：LLM 知识 + 常识估算。

---

### Step 4: 更新 manifest

调用脚本写入 `project-manifest.json`：

```bash
python G:/MicroPython_Skills/upy-select-hw/scripts/update_manifest.py \
  --project-dir {project_dir} \
  --input {llm_output_json}
```

--- 写入字段：
- `phase`: "select-hw"
- `mcu`: {model, board, firmware_url, flash_tool}
- `pinout`: [{device, pin_name, gpio, physical_pin, type, side, pos, notes}]
  - `physical_pin`: 物理引脚编号（如 Pico 的 GP4 = Pin 6）
  - `type`: 引脚电气类型枚举（见下方映射表）
  - `side`: 引脚在 MCU 哪一侧（left/right/top/bottom）
  - `pos`: 在 side 上的顺序位置（0-based）
- `bom`: [{name, model, quantity, unit_price_yuan, notes}]

---

## 与其他 skill 的关系

- ← `upy-analyze`：输入 manifest
- → `upy-scaffold`：传入完整硬件方案（mcu + pinout + bom）

## 强约束

- **MCU 只推荐 Pico 系列和 ESP32 系列**（除非用户指定其他型号）
- **固件核验是必须的**——确认有 MPY 固件再继续
- **引脚分配前必须先看到引脚图**——不依赖内置数据库
- **I2C 地址冲突必须检测**——不能把两个同地址器件放同一总线
- **启动敏感引脚必须避开**
