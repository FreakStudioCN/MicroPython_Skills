---
name: upy-wiring
description: 接线图生成。读取 project-manifest.json 的 pinout/mcu/devices/bom，LLM 生成中间 JSON，脚本渲染 Mermaid 接线图（.md 代码块，CLI 原生可读）+ 必需 SVG。触发：upy-scaffold 或 upy-generate 完成后。
---

# 接线图生成 Skill

## 角色定位

给定 `project-manifest.json`（phase: scaffold 或 generate），LLM 理解 `wiring.schema.json` 后从 manifest 提取引脚、总线、器件、供电信息，填入中间 JSON，再由脚本校验并生成 Mermaid 接线图 + PNG 图片 + 引脚交叉引用表。**LLM 负责理解数据并填写 JSON，脚本只做校验和渲染。**

---

## 前置检查

```bash
python --version
python -c "import jsonschema; print('jsonschema OK')"
```

缺失则提示安装：`pip install jsonschema`

SVG 渲染需要网络（mermaid.ink API，零本地依赖）。

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

**告警信息必须精简，每条 `msg` ≤60 英文字符**（告警框在接线图中宽度固定 ~260px，过长文本会被截断或挤占整个布局）。

| 条件 | level | category | msg |
|------|-------|----------|-----|
| I2C 地址冲突（多个器件同地址） | `danger` | `conflict` | "{d1} and {d2} both at {addr} — address conflict" |
| I2C 无上拉电阻说明 | `warning` | `pullup` | "Verify I2C pull-up resistors on SDA/SCL (4.7kΩ to 3.3V)" |
| 5V 器件接 3.3V 引脚 | `danger` | `level_shift` | "{device}: 5V device on 3.3V pin — level shifter needed" |
| 3.3V 器件接 5V 引脚 | `danger` | `level_shift` | "{device}: 3.3V device on 5V pin — risk of damage" |
| 使用 GP0/GP1（Pico 启动敏感） | `warning` | `startup` | "GP0/GP1 used during boot on some boards; verify compatible" |
| 蜂鸣器无限流电阻 | `info` | `current_limit` | "Add 220Ω current-limiting resistor in series with buzzer" |
| LED 无电阻 | `warning` | `current_limit` | "Add 220Ω current-limiting resistor in series with LED" |
| SPI 器件缺 CS 引脚 | `warning` | `general` | "SPI device {name}: missing CS pin assignment" |

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

### Step 5: 生成 Mermaid .md + PNG 文件（联合必需输出）

**这是本 skill 的主要输出。** 脚本从 wiring.json 生成 Mermaid 接线图 .md + SVG + 引脚交叉引用表。架构与 `upy-diagram` 一致：JSON → Mermaid 代码 → .md + SVG。

```bash
python G:/MicroPython_Skills/upy-wiring/scripts/render_wiring_local.py \
  --input {project_dir}/docs/wiring.json \
  --output {project_dir}/docs/
```

脚本默认 `--format all`，同时输出：

| 文件 | 内容 |
|------|------|
| `docs/wiring.md` | Mermaid `graph TB` 接线示意图：MCU 引脚子图 + 总线子图 + 独立 GPIO + 电源连线 + 注意事项 |
| `docs/wiring.svg` | SVG 接线图（通过 mermaid.ink API 渲染，矢量格式清晰不模糊） |
| `docs/wiring_pins.md` | Markdown 引脚交叉引用表（GPIO → 器件 → 类型 → 备注） |

### Step 6: SVG 渲染（必需，已包含在 Step 5 的 --format all 中）

脚本默认使用 mermaid.ink API 渲染 SVG（零本地依赖，需要网络）：

```bash
# 仅 SVG（跳过 .md 重写）：
python G:/MicroPython_Skills/upy-wiring/scripts/render_wiring_local.py \
  --input {project_dir}/docs/wiring.json \
  --output {project_dir}/docs/ \
  --format svg
```

原理：Mermaid 代码 Base64 编码 → GET `https://mermaid.ink/img/{base64}?type=svg` → 保存 SVG。

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
m['wiring']['svg'] = 'docs/wiring.svg'
m['wiring']['md'] = 'docs/wiring.md'
m['wiring']['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print('[OK] manifest wiring updated')
"
```

---

## 与其他 skill 的关系

- ← `upy-scaffold` / `upy-generate`：输入 manifest（含 pinout/mcu/devices/bom）
- 与 `upy-diagram` 并行：可同时生成，共用 mermaid.ink SVG 渲染管线
- → VS Code 插件 WebView：展示 Mermaid 图（Markdown 预览）或 PNG

---

## 强约束

- **LLM 生成 JSON，脚本只做校验 + 渲染**：与 `upy-generate` / `upy-diagram` 模式一致
- **schema 是唯一契约**：wiring.json 必须通过 `validate_json.py` 校验
- **LLM 必须推断缺失字段**：manifest.pinout 数据不完整时，根据 Pico/ESP32 引脚图知识补全 physical_pin、type、side、pos
- **LLM 必须补充电源引脚**：3V3、GND 始终要被加入 mcu.pins[]
- **引脚类型枚举必须匹配**：`mcu.pins[].type` 必须是 schema 定义的 enum 值
- **I2C 器件必须有 `addr`**：格式 `0x00`，正则 `^0x[0-9a-fA-F]{2}$`
- **SPI 器件必须有 `cs_gpio`**：片选引脚
- **告警由 LLM 按规则判断并写入 alerts[]**
- **SVG 为必需输出**：脚本默认 `--format all`，同时生成 .md 和 .svg；仅 `--format md` 可跳过 SVG
- **canvas 可为空对象**：渲染器自动布局，不要求 LLM 计算坐标
- **渲染脚本防御式读取**：缺失字段不会崩溃，但会在 stderr 输出警告
- **与 upy-diagram 共用 mermaid.ink 管线**：两者 PNG 渲染方式一致
- **可读性约束（保证 PNG 在 ~1200px 宽度下清晰可读）**：

  | 字段 | 上限 | 说明 |
  |------|------|------|
  | `alerts[].msg` | ≤60 英文字符 | 告警框宽度 ~260px，过长被截断或挤占布局 |
  | `standalone[].external_components` | ≤20 字 | 器件附属说明，过长使独立器件框膨胀 |
  | `buses[].devices[].notes` | ≤20 字 | 器件备注，保持简洁 |
