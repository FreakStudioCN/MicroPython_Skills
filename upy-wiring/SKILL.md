---
name: upy-wiring
description: 接线图生成。通读 firmware/ 全部 .py 源码提取实际引脚/地址/总线，与 project-manifest.json 交叉验证后 LLM 生成中间 JSON，脚本渲染 Mermaid 接线图（.md 代码块，CLI 原生可读）+ SVG + PNG + HTML（双击浏览器可看）。触发：upy-scaffold 或 upy-generate 完成后。
---

# 接线图生成 Skill

## 角色定位

**通读 `firmware/` 全部 `.py` 源码 + `project-manifest.json`**，以 firmware 为权威数据源、manifest 为设计参考，交叉验证后 LLM 填写中间 JSON，脚本校验并渲染 Mermaid 接线图 + SVG + PNG + HTML + 引脚交叉引用表。**LLM 负责理解数据并填写 JSON，脚本只做校验和渲染。**

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

### Step 2: LLM 通读 firmware/ 全部 .py 源码 → 提取硬件事实

**这是本 skill 的核心数据源。** 读取 `{project_dir}/firmware/` 下所有 `.py` 文件，按以下优先级提取硬件连接事实：

#### 2A: main.py — 硬件初始化（最高优先级）

搜索模式并提取：

| 搜索模式 | 提取内容 | 用途 |
|----------|----------|------|
| `I2C(id, scl=Pin(n), sda=Pin(n), freq=f)` | 总线 ID、SCL/SDA GPIO 编号、频率 | buses[].signals, frequency_hz |
| `SPI(id, sck=Pin(n), mosi=Pin(n), miso=Pin(n))` | SPI 总线信号线 | buses[].signals |
| `UART(id, tx=Pin(n), rx=Pin(n), baudrate=b)` | UART 总线信号线 | buses[].signals |
| `Pin(n, Pin.OUT)` / `Pin(n, Pin.IN)` | GPIO 编号、方向 | standalone[].type, mcu.pins[].type |
| `Pin(n, Pin.IN, Pin.PULL_UP)` | GPIO 编号、上拉 | standalone[].type=gpio_in_pullup |
| `create_*(i2c, ...)` / `create_*(pin, ...)` | 器件工厂调用、实际地址参数 | buses[].devices / standalone[] |
| `i2c.scan()` 附近的地址常量 / 日志 | 实际使用的 I2C 地址 | buses[].devices[].addr |
| `Pin.OUT` 初始值 `Pin(n).value(0)` | 初始电平 | standalone[].active_level |

**示例**：`I2C(0, scl=Pin(5), sda=Pin(4), freq=400000)` → I2C0 总线，SCL=GP5, SDA=GP4, 400kHz。

#### 2B: board.py — 引脚映射表

提取 `BOARDS` 字典中的所有引脚定义：

| 路径 | 内容 |
|------|------|
| `BOARDS[name]["FIXED_PINS"]` | 板载固定引脚（如 Pico 板载 LED=GP25），**必须加入 mcu.pins[]** |
| `BOARDS[name]["INTERFACES"]["I2C"][id]` | I2C 总线引脚映射 (SDA/SCL) |
| `BOARDS[name]["INTERFACES"]["SPI"][id]` | SPI 总线引脚映射 (MOSI/MISO/SCK) |
| `BOARDS[name]["INTERFACES"]["UART"][id]` | UART 引脚映射 (TX/RX) |
| `BOARDS[name]["DEFAULTS"]` | 默认频率/波特率 |

**即使 device 未在 main.py 中用到，board.py 定义的固定引脚（如板载 LED）也应出现在 mcu.pins[] 中。**

#### 2C: drivers/*/__init__.py — 默认 I2C 地址 & 器件信息

每个 driver 的 `__init__.py` 查找：

| 模式 | 提取 |
|------|------|
| `_XXXX_DEFAULT_ADDR = 0xNN` | 器件默认 I2C 地址（**这是最权威的地址来源**） |
| `create_*(i2c, address=...)` | 可覆盖地址参数，确认实际使用的地址 |
| 类名 / 导入语句 | 器件型号和驱动来源 |

#### 2D: conf.py — 项目身份

提取 `PROJECT_NAME`, `BOARD_NAME` → 填入 `meta.project`, `meta.mcu_model`。

#### 2E: tasks/*.py — 补充引脚使用

任务文件中可能有额外的 Pin 引用（如报警任务中操作 GPIO），扫描确认无遗漏。

#### 2F: lib/*.py — 第三方驱动

检查 `firmware/lib/` 下的驱动文件，确认是否有硬编码的引脚或地址。这些通常与 `drivers/*/__init__.py` 一致，但有时驱动作者会写死默认值。

### Step 3: LLM 阅读 manifest → 提取设计意图 + 交叉验证

读取 `{project_dir}/project-manifest.json`，提取 `mcu`, `pinout`, `devices`, `bom`。

**交叉验证规则（firmware 为权威）：**

| 场景 | 处理 |
|------|------|
| firmware 和 manifest 一致 | 直接采用 |
| firmware 有、manifest 无 | 采用 firmware，额外补入 pins[] / buses[].devices[] |
| manifest 有、firmware 无 | 加入 alerts[] 标记为 "planned only, not found in firmware" |
| I2C 地址不一致 | 以 driver `_DEFAULT_ADDR` 为准；若 main.py 显式传入则以 main.py 为准 |
| GPIO 编号不一致 | 以 main.py `Pin(x)` 为准，添加 manifest 与实际不符的告警 |

#### 3A: 字段推断规则（当 manifest.pinout 缺少字段时）

**物理引脚编号 (physical_pin) 推断：**

| MCU | 规则 |
|-----|------|
| Raspberry Pi Pico | GP0=Pin1, GP1=Pin2, ..., GP28=Pin34。3V3(OUT)=Pin36。GND=Pin3/8/13/18/23/28/33/38 |
| ESP32 | 查阅引脚图（WebSearch `ESP32 pinout diagram`） |
| ESP32-S3 | 查阅引脚图（WebSearch `ESP32-S3 pinout diagram`） |

**引脚电气类型 (type) 推断（结合 firmware Pin 初始化模式和 manifest pin_name）：**

| 判断依据 | type 值 |
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
| `Pin(x, Pin.OUT)` — LED/蜂鸣器/继电器 | `gpio_out` |
| `Pin(x, Pin.IN)` — 按键 | `gpio_in` |
| `Pin(x, Pin.IN, Pin.PULL_UP)` | `gpio_in_pullup` |
| `ADC` / `Pin(x, Pin.IN)` + 模拟传感器 | `adc` |
| `PWM` / `Pin(x, Pin.OUT)` + 舵机/调光 | `pwm` |
| I2S | `i2s` |

**引脚侧边 (side) 推断：**

| MCU | 规则 |
|-----|------|
| Pico (40-pin DIP) | 左侧=Pin1~20（GP0~GP15），右侧=Pin21~40（GP16~GP28 + 电源） |
| ESP32 (38-pin) | 左侧=Pin1~19，右侧=Pin20~38 |

**引脚序位 (pos) 推断：** 从 0 开始，在 side 内部按 physical_pin 递增编号。

#### 3B: 电源引脚补充

**manifest 中通常缺少电源引脚，LLM 必须主动补充：**

- 3V3(OUT) 引脚：所有 I2C/SPI 传感器、屏幕的 VCC
- GND 引脚：所有器件的共地
- 如果有大功率器件（舵机/电机），补充 5V/VBUS 引脚

#### 3C: 总线归类（以 firmware 为准）

- I2C 器件 → `buses[]` type=`i2c`，信号线 SDA/SCL。I2C 地址以 driver `_DEFAULT_ADDR` 为准，若 main.py 显式传入则以实际传入值为准
- SPI 器件 → `buses[]` type=`spi`，信号线 MOSI/MISO/SCK/CS
- UART 器件 → `buses[]` type=`uart`，信号线 TX/RX
- GPIO 器件（无总线，`Pin.OUT`/`Pin.IN`） → `standalone[]`

#### 3D: 告警自动生成

**告警信息必须精简，每条 `msg` ≤60 英文字符**（告警框在接线图中宽度固定 ~260px，过长文本会被截断或挤占整个布局）。

**硬件告警：**

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

**交叉验证告警（firmware vs manifest）：**

| 条件 | level | category | msg |
|------|-------|----------|-----|
| firmware 用到的 pin，manifest.pinout 未声明 | `warning` | `firmware_only` | "GP{n} used in firmware but missing from manifest pinout" |
| manifest.pinout 声明，firmware 未用到 | `info` | `manifest_only` | "{device}: in manifest but not found in firmware code" |
| I2C 地址 firmware 与 manifest 不一致 | `danger` | `conflict` | "{device}: firmware uses {addr1}, manifest says {addr2}" |
| GPIO 编号 firmware 与 manifest 不一致 | `danger` | `conflict` | "{device}: firmware uses GP{n1}, manifest says GP{n2}" |

### Step 4: LLM 生成 wiring.json

根据 schema 和 Step 2/3 提取/验证的数据，生成 `{project_dir}/docs/wiring.json`。

**数据优先级：firmware > manifest > LLM 推断**

**LLM 自主决定：** `canvas` 布局坐标（可为空对象）、`mcu.orientation`、`mcu.pins[].pos` 排列顺序、告警补充。

### Step 5: 校验 wiring.json

```bash
python G:/MicroPython_Skills/upy-project-gen-toolchain-spec/scripts/validate_json.py \
  --schema G:/MicroPython_Skills/upy-project-gen-toolchain-spec/wiring.schema.json \
  --json {project_dir}/docs/wiring.json
```

校验失败 → 修改 wiring.json → 重新校验，直到 pass。

### Step 6: 生成 Mermaid .md + SVG + PNG + HTML 文件（联合必需输出）

**这是本 skill 的主要输出。** 脚本从 wiring.json 生成 Mermaid 接线图 .md + SVG + PNG + HTML + 引脚交叉引用表。架构与 `upy-diagram` 一致：JSON → Mermaid 代码 → .md + SVG + PNG + HTML。

```bash
python G:/MicroPython_Skills/upy-wiring/scripts/render_wiring_local.py \
  --input {project_dir}/docs/wiring.json \
  --output {project_dir}/docs/
```

脚本默认 `--format all`，同时输出：

| 文件 | 内容 |
|------|------|
| `docs/wiring.md` | Mermaid `graph TB` 接线示意图：MCU 引脚子图 + 总线子图 + 独立 GPIO + 电源连线 + 注意事项 |
| `docs/wiring.svg` | SVG 接线图（矢量格式，清晰不模糊） |
| `docs/wiring.png` | PNG 接线图（位图格式，通用兼容） |
| `docs/wiring.html` | 自包含 HTML 页面（Mermaid.js CDN 动态渲染，Tab 切换接线图/源码，浏览器双击即看） |
| `docs/wiring_pins.md` | Markdown 引脚交叉引用表（GPIO → 器件 → 类型 → 备注） |

### Step 7: SVG 渲染（必需，已包含在 Step 6 的 --format all 中）

脚本默认使用 mermaid.ink API 渲染 SVG（零本地依赖，需要网络）：

```bash
# 仅 SVG（跳过 .md 重写）：
python G:/MicroPython_Skills/upy-wiring/scripts/render_wiring_local.py \
  --input {project_dir}/docs/wiring.json \
  --output {project_dir}/docs/ \
  --format svg
```

原理：Mermaid 代码 Base64 编码 → GET `https://mermaid.ink/img/{base64}?type=svg` → 保存 SVG。

HTML 使用 Mermaid.js CDN 直接在浏览器中渲染，与 mermaid.ink 无关。

### Step 8: 更新 manifest

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
m['wiring']['png'] = 'docs/wiring.png'
m['wiring']['html'] = 'docs/wiring.html'
m['wiring']['md'] = 'docs/wiring.md'
m['wiring']['generated_at'] = datetime.now(timezone.utc).isoformat()
with open(path, 'w', encoding='utf-8') as f:
    json.dump(m, f, ensure_ascii=False, indent=2)
print('[OK] manifest wiring updated')
"
```

---

## 与其他 skill 的关系

- ← `upy-scaffold` / `upy-generate`：输入 firmware/ 源码 + manifest（含 pinout/mcu/devices/bom）
- 与 `upy-diagram` 并行：可同时生成，共用 mermaid.ink SVG 渲染管线
- → VS Code 插件 WebView：展示 Mermaid 图（Markdown 预览）或 PNG

---

## 强约束

- **firmware 是权威数据源，manifest 是设计参考**：当两者冲突时以 firmware 为准
- **必须通读 firmware/ 全部 .py 源码**：不可跳过此步骤
- **board.py 的 FIXED_PINS 必须加入 mcu.pins[]**：如 Pico 板载 LED=GP25
- **LLM 生成 JSON，脚本只做校验 + 渲染**：与 `upy-generate` / `upy-diagram` 模式一致
- **schema 是唯一契约**：wiring.json 必须通过 `validate_json.py` 校验
- **LLM 必须推断缺失字段**：manifest.pinout 数据不完整时，优先从 firmware 补全，其次根据 Pico/ESP32 引脚图知识
- **LLM 必须补充电源引脚**：3V3、GND 始终要被加入 mcu.pins[]
- **引脚类型枚举必须匹配**：`mcu.pins[].type` 必须是 schema 定义的 enum 值
- **I2C 器件必须有 `addr`**：格式 `0x00`，正则 `^0x[0-9a-fA-F]{2}$`。地址以 driver `_DEFAULT_ADDR` 为准
- **SPI 器件必须有 `cs_gpio`**：片选引脚
- **告警由 LLM 按规则判断并写入 alerts[]**
- **SVG + PNG + HTML 为必需输出**：脚本默认 `--format all`，同时生成 .md、.svg、.png 和 .html；仅 `--format md` 可跳过图片渲染
- **canvas 可为空对象**：渲染器自动布局，不要求 LLM 计算坐标
- **渲染脚本防御式读取**：缺失字段不会崩溃，但会在 stderr 输出警告
- **与 upy-diagram 共用 mermaid.ink 管线**：两者 PNG 渲染方式一致
- **可读性约束（保证 PNG 在 ~1200px 宽度下清晰可读）**：

  | 字段 | 上限 | 说明 |
  |------|------|------|
  | `alerts[].msg` | ≤60 英文字符 | 告警框宽度 ~260px，过长被截断或挤占布局 |
  | `standalone[].external_components` | ≤20 字 | 器件附属说明，过长使独立器件框膨胀 |
  | `buses[].devices[].notes` | ≤20 字 | 器件备注，保持简洁 |
