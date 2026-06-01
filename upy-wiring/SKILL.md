---
name: upy-wiring
description: 第七步——接线图生成。读取 project-manifest.json 的 pinout/mcu/devices/bom，LLM 生成中间 JSON + CLI 文本接线图，可选 SVG 渲染。触发：upy-scaffold 或 upy-generate 完成后。
---

# 接线图生成 Skill

## 角色定位

给定 `project-manifest.json`（phase: scaffold 或 generate），LLM 理解 `wiring.schema.json` 后从 manifest 提取引脚、总线、器件、供电信息，生成中间 JSON 并直接输出 **CLI 文本接线图**（Unicode box-drawing 字符）。脚本负责 JSON 校验 + 可选 SVG 渲染。**LLM 生成 JSON + 文本图，脚本只做校验和可选的图像渲染。**

---

## 前置检查

```bash
python --version
python -c "import jsonschema; print('jsonschema OK')"
```

必需：`pip install jsonschema`

可选（SVG 渲染）：`pip install matplotlib Pillow`

---

## 执行步骤

### Step 1: LLM 阅读 Schema → 理解结构

读取中间 JSON schema：

```
G:/MicroPython_Skills/upy-project-gen-toolchain-spec/wiring.schema.json
```

理解 6 个必需字段：`meta`, `mcu`, `buses`, `standalone`, `power`, `alerts`，以及可选字段 `canvas`。

### Step 2: LLM 阅读 manifest → 提取 + 推断硬件数据

读取 `{project_dir}/project-manifest.json`，提取 `mcu`, `pinout`, `devices`, `bom`。

**关键：manifest 中的 pinout 数据可能不完整。LLM 必须主动推断和补全缺失字段。**

#### 2A: 字段推断规则（当 manifest.pinout 缺少字段时）

**物理引脚编号 (physical_pin) 推断：**

| MCU | 规则 |
|-----|------|
| Raspberry Pi Pico | GP0=Pin1, GP1=Pin2, ..., GP28=Pin34。3V3(OUT)=Pin36。GND=Pin3/8/13/18/23/28/33/38 |
| ESP32 | 查阅引脚图（WebSearch `ESP32 pinout diagram`） |
| ESP32-S3 | 查阅引脚图（WebSearch `ESP32-S3 pinout diagram`） |

**引脚电气类型 (type) 推断：**

| manifest pin_name 含有关键词 | type 值 |
|---|---|
| `3V3` / `3.3V` | `power_3v3` |
| `5V` / `VBUS` | `power_5v` |
| `GND` | `gnd` |
| `I2C` + `SDA` / `Data` | `i2c_data` |
| `I2C` + `SCL` / `Clock` | `i2c_clock` |
| `SPI` + `MOSI` / `TX` | `spi_mosi` |
| `SPI` + `MISO` / `RX` | `spi_miso` |
| `SPI` + `SCK` / `CLK` | `spi_sck` |
| `SPI` + `CS` / `SS` | `spi_cs` |
| `UART` + `TX` | `uart_tx` |
| `UART` + `RX` | `uart_rx` |
| GPIO 输出器件（LED/蜂鸣器/继电器） | `gpio_out` |
| GPIO 输入器件（按键） | `gpio_in` |
| GPIO 输入+上拉 | `gpio_in_pullup` |
| ADC | `adc` |
| PWM | `pwm` |
| I2S | `i2s` |

**引脚侧边 (side) 推断：**

| MCU | 规则 |
|-----|------|
| Pico (40-pin DIP) | 左侧=Pin1~20（GP0~GP15），右侧=Pin21~40（GP16~GP28 + 电源） |
| ESP32 (38-pin) | 左侧=Pin1~19，右侧=Pin20~38 |

**引脚序位 (pos) 推断：** 从 0 开始，在 side 内部按 physical_pin 递增编号。

#### 2B: 电源引脚补充

**manifest 中通常缺少电源引脚，LLM 必须主动补充：**

- 3V3(OUT) 引脚：所有 I2C/SPI 传感器、屏幕的 VCC
- GND 引脚：所有器件的共地
- 如果有大功率器件（舵机/电机），补充 5V/VBUS 引脚

#### 2C: 总线归类

- I2C 器件 → `buses[]` type=`i2c`，信号线 SDA/SCL
- SPI 器件 → `buses[]` type=`spi`，信号线 MOSI/MISO/SCK/CS
- UART 器件 → `buses[]` type=`uart`，信号线 TX/RX
- GPIO 器件（无总线） → `standalone[]`

#### 2D: 告警自动生成

| 条件 | level | category | msg |
|------|-------|----------|-----|
| I2C 地址冲突（多个器件同地址） | `danger` | `conflict` | "I2C address conflict: {device1} and {device2} both at {addr}" |
| I2C 无上拉电阻说明 | `warning` | `pullup` | "Verify I2C pull-up resistors on SDA/SCL (typically 4.7kΩ to 3.3V)" |
| 5V 器件接 3.3V 引脚 | `danger` | `level_shift` | "{device} requires 5V but connected to 3.3V pin" |
| 3.3V 器件接 5V 引脚 | `danger` | `level_shift` | "{device} is 3.3V but connected to 5V pin — level shifter required" |
| 使用 GP0/GP1（Pico 启动敏感） | `warning` | `startup` | "GP0/GP1 are used during boot on some boards; verify compatibility" |
| 蜂鸣器无限流电阻 | `info` | `current_limit` | "Add a 220Ω current-limiting resistor in series with buzzer" |
| LED 无电阻 | `warning` | `current_limit` | "Add a 220Ω current-limiting resistor in series with LED" |
| SPI 器件缺 CS 引脚 | `warning` | `general` | "SPI device {name} missing CS pin assignment" |

### Step 3: LLM 生成 wiring.json

根据 schema 和提取/推断的数据，生成 `{project_dir}/docs/wiring.json`。

**LLM 自主决定：** `canvas` 布局坐标（可为空对象）、`mcu.orientation`、`mcu.pins[].pos` 排列顺序、告警补充。

### Step 4: 校验 wiring.json

```bash
python G:/MicroPython_Skills/upy-project-gen-toolchain-spec/scripts/validate_json.py \
  --schema G:/MicroPython_Skills/upy-project-gen-toolchain-spec/wiring.schema.json \
  --json {project_dir}/docs/wiring.json
```

校验失败 → 修改 wiring.json → 重新校验，直到 pass。

---

### Step 5: LLM 生成 CLI 文本接线图 (主要输出)

**这是本 skill 的主要输出。LLM 根据 wiring.json 的数据直接生成 Unicode box-drawing 文本图，包裹在 Markdown 代码块中。**

#### 5A: 布局规则

```
水平布局（推荐）：
  [3V3 Rail]──────────────[5V Rail]──────────────
   │                      │
  ┌┴──────────────────────┴──────────────────────┐
  │              Raspberry Pi Pico                │
  │  ┌──────────────────────────────────────────┐ │
  │  │ 左排 GPIO                   右排 GPIO     │ │
  │  │ GP0  □ Pin1      Pin40 □ VBUS           │ │
  │  │ GP1  □ Pin2      Pin39 □ VSYS           │ │
  │  │ ...                                      │ │
  │  │ GP4  □ Pin6 ───I2C0 SDA──→ SHT30(0x44)  │ │
  │  │ GP5  □ Pin7 ───I2C0 SCL──→ BMP280(0x76) │ │
  │  │                           └→ OLED(0x3C)  │ │
  │  │ ...                                      │ │
  │  │ GP16 □ Pin21───→ Buzzer                  │ │
  │  │ GP17 □ Pin22───→ LED(220Ω)               │ │
  │  │ GND  □ Pin38───→ 所有器件 GND             │ │
  │  └──────────────────────────────────────────┘ │
  └──────────────────────────────────────────────┘
   │                      │
  [GND Rail]──────────────┘

图例: ─ I2C  ═ SPI  ·· UART  ── GPIO  ▓ Power
```

#### 5B: 绘制约定

- MCU 芯片用 **粗线框** `┌┐└┘` 包围
- 每个使用的引脚显示其标签和物理编号
- 通信总线用 **不同线型**：I2C=`──`(实线)、SPI=`══`(双线)、UART=`····`(虚线)
- GPIO 直接连接：`GP16 □ Pin21 ───→ Buzzer`
- 电源轨用 **粗线** 在顶部/底部
- 末尾附简要图例

#### 5C: 文本图必须包含的元素

1. **MCU 封装框**：包含型号名、pin 编号、GPIO 标签
2. **总线连接**：每条总线的信号线从 MCU 到器件，标注 GPIO 和信号角色
3. **独立 GPIO**：直接连接线 + 器件名 + 外围元件（如"串联220Ω"）
4. **电源轨**：顶部/底部 3V3 / 5V / GND 分配
5. **图例**：线型说明

#### 5D: 输出到文件

LLM 将文本图直接写入 Markdown 文件，保存为代码块：

````markdown
# 环境监测装置 — 接线图

## 接线示意图

```
 ┌──────────────────────────────────────────────┐
 │              Raspberry Pi Pico                │
 │  ┌──────────────────────────────────────────┐ │
 │  │  左排                       右排          │ │
 │  │  GP0  □ Pin1       Pin40 □ VBUS          │ │
 │  │  ...                                      │ │
 │  │  GP4  □ Pin6 ───I2C0 SDA──→ SHT30(0x44)  │ │
 │  │                        └──→ BMP280(0x76)  │ │
 │  │                        └──→ OLED(0x3C)    │ │
 │  │  GP5  □ Pin7 ───I2C0 SCL──→ (同上)        │ │
 │  │  GP16 □ Pin21 ──→ Buzzer                  │ │
 │  │  GP17 □ Pin22 ──→ LED(220Ω)               │ │
 │  │  GND  □ Pin38 ──→ 共地                    │ │
 │  └──────────────────────────────────────────┘ │
 └──────────────────────────────────────────────┘
```

## 引脚对照表

| # | 器件 | MCU 引脚 | GPIO | 协议 | 地址/备注 |
|---|------|---------|------|------|----------|
| 1 | SHT30 | 6 | GP4 | I2C I2C0 (SDA=GP4, SCL=GP5) | 0x44 |
| 2 | BMP280 | 6,7 | GP4,GP5 | I2C I2C0 (SDA=GP4, SCL=GP5) | 0x76 |
| 3 | SSD1306 OLED | 6,7 | GP4,GP5 | I2C I2C0 (SDA=GP4, SCL=GP5) | 0x3C |
| 4 | 有源蜂鸣器 | 21 | GP16 | GPIO | 串联220Ω限流电阻 |
| 5 | LED | 22 | GP17 | GPIO | 串联220Ω限流电阻 |

## 注意事项

> **WARNING** Verify I2C pull-up resistors on SDA/SCL (typically 4.7kΩ to 3.3V)
> Add a 220Ω current-limiting resistor in series with buzzer
> **WARNING** Add a 220Ω current-limiting resistor in series with LED
````

写入 `{project_dir}/docs/wiring.md`。

### Step 6: 可选 — SVG/PNG 渲染（需要 matplotlib）

如果用户明确要求图片格式，或 VS Code WebView 需要渲染：

```bash
python G:/MicroPython_Skills/upy-wiring/scripts/render_wiring_local.py \
  --input {project_dir}/docs/wiring.json \
  --output {project_dir}/docs/ \
  --format all
```

输出 `docs/wiring.svg` + `docs/wiring.md`（脚本版引脚表）。

> 注意：SVG 中的中文标签需要系统安装中文字体（SimHei / Microsoft YaHei）。脚本会自动检测并使用第一个可用中文字体。

### Step 7: 更新 manifest

```bash
cd {project_dir} && python -c "
import json, os
from datetime import datetime, timezone
path = 'project-manifest.json'
with open(path, 'r', encoding='utf-8') as f:
    m = json.load(f)
m['wiring'] = m.get('wiring', {})
m['wiring']['json'] = 'docs/wiring.json'
m['wiring']['md'] = 'docs/wiring.md'
m['wiring']['cli_text'] = True
m['wiring']['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print('[OK] manifest wiring updated')
"
```

如果 Step 6 也执行了，额外追加 `svg` 路径：
```python
m['wiring']['svg'] = 'docs/wiring.svg'
```

---

## 与其他 skill 的关系

- ← `upy-scaffold` / `upy-generate`：输入 manifest（含 pinout/mcu/devices/bom）
- 与 `upy-diagram` 并行：可同时生成
- → VS Code 插件 WebView：展示 Markdown 中的 CLI 文本图（或 SVG）

---

## 强约束

- **LLM 生成 JSON + CLI 文本图**：JSON 通过 schema 校验，文本图直接写入 .md
- **文本图是主要输出**：不依赖 matplotlib，中文直接显示，终端原生可读
- **LLM 必须推断缺失字段**：manifest.pinout 数据不完整时，根据 Pico/ESP32 引脚图知识补全 physical_pin、type、side、pos
- **LLM 必须补充电源引脚**：3V3、GND 始终要被加入 mcu.pins[]
- **schema 是 JSON 的唯一契约**：wiring.json 必须通过 `validate_json.py` 校验
- **引脚 type 必须用 schema enum 值**：`i2c_data` 不是 `i2c_sda`，大小写严格匹配
- **I2C 器件必须有 `addr`**：格式 `0x00`，正则 `^0x[0-9a-fA-F]{2}$`
- **SPI 器件必须有 `cs_gpio`**
- **告警由 LLM 按规则判断并写入 alerts[]**
- **文本图绘制用 Unicode box-drawing 字符**：`─│┌┐└┘├┤┬┴┼□→`
