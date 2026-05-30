---
name: upy-analyze
description: 第一步——解析用户自然语言需求，多关键词并行搜索 upypi 和 awesome-micropython 驱动，输出结构化 project-manifest.json。触发：用户描述嵌入式项目需求，"我想做"、"做一个"、"帮我写一个"。
---

# 需求解析与驱动搜索 Skill

## 角色定位

给定用户的一句话项目描述，完成**意图拆解 → 交互确认 → 驱动搜索 → 输出 manifest**。不选型、不生成代码、不分配引脚。输出 `project-manifest.json` 给下游 `upy-select-hw`。

## 前置检查

```bash
python --version
python -c "import requests; print('requests OK')"
```

任一失败则停止，提示用户安装。

---

## 执行步骤

### Step 1: 意图拆解

从用户描述中提取结构化信息：

| 维度 | 提取内容 | 用途 |
|------|---------|------|
| 功能描述 | 要做什么（采集/控制/显示/通信/报警） | 生成交互确认 |
| 器件列表 | 传感器/模块/执行器（型号或通用名） | 驱动搜索 |
| 接口类型 | I2C/SPI/UART/GPIO/I2S 等 | 驱动搜索关键词 |
| 关键词 | 英文章词：功能类别 + 接口 + 芯片型号 | 并行搜索 |

**注意：**
- 用户可能只说了器件通用名（"温湿度传感器"），未指定型号 → 先在交互确认中追问
- 用户可能完全没说器件 → 根据功能反推（"监测温度" → 需要温度传感器）→ 在交互确认中呈现

### Step 2: 交互确认

**先分流，再确认。使用 `AskUserQuestion`，用户点击即可。**

#### Step 2A: 分流（1 问）

```
header: "使用模式"
question: "选择配置方式"
options:
  - "小白模式：帮我自动推荐 (默认)" (description: "只确认器件和主控，其他全部自动配置")
  - "自定义模式：我要逐项选择" (description: "主控、场景、性能、输出方式逐项定制")
```

#### Step 2B: 小白模式（1~2 问）

**Q1: 主控确认**（仅当用户未在描述中指定 MCU 时询问）

```
header: "主控"
question: "用什么开发板？"
options:
  - "ESP32 (推荐默认)" (description: "最通用，WiFi/BLE，接口丰富")
  - "Raspberry Pi Pico" (description: "RP2040，性价比高")
  - "ESP32-S3" (description: "更强的 AI 能力，USB-OTG")
  - "Other"
```

用户选 "Other" → 记录 `mcu_specified` = Other 输入值，具体核验交给 Phase 2 `upy-select-hw`

**Q2: 器件清单确认** (multiSelect)

```
header: "器件清单"
question: "这些器件对吗？不对的选择去掉，缺的选择补上"
multiSelect: true
options:
  - "{器件1} — {接口}/{型号}"
  - "{器件2} — {接口}/{型号}"
  - ...
  - "缺了器件，需补充"
```

用户确认后 → **进入 Step 3 驱动搜索。**（MCU 固件核验由 Phase 2 `upy-select-hw` 负责）
所有 requirements 维度使用默认值。
`experience = "beginner"`

#### Step 2C: 自定义模式（最多 4 问）

`experience = "experienced"`

##### 第一轮（4 问）

**Q1: 主控确认**（仅当用户未指定时；已指定则跳过此问）

```
header: "主控"
question: "用什么开发板？"
options:
  - "ESP32 (推荐默认)" (description: "最通用，WiFi/BLE，接口丰富")
  - "Raspberry Pi Pico" (description: "RP2040，性价比高，无 WiFi")
  - "ESP32-S3" (description: "AI 加速，USB-OTG")
  - "Other"
```

**Q2: 器件清单确认** (multiSelect，含 LLM 建议新增的器件)

```
header: "器件清单"
question: "以下识别的器件是否正确？"
options:
  - "{器件1} — {接口}/{型号}"
  - ...
  - "+ {建议器件}（建议，{原因}）"
  - "缺了器件，需补充"
```

**Q3: 场景与供电** (singleSelect)

```
header: "场景供电"
question: "使用场景和供电方式？"
options:
  - "室内桌面 + USB供电 (默认)" → scene=indoor, power=usb, temp_range=normal_0_40
  - "室内 + 电池供电" → scene=indoor, power=battery_li
  - "室外 + 电池/太阳能" → scene=outdoor, power=battery_li, network=wifi, temp_range=extended_-20_70
  - "Other"
```

**Q4: 性能 + 输出** (合并第 3、4 维)

```
header: "性能输出"
question: "性能和输出要求？"
options (前 3 个 singleSelect-like 但用 multiSelect 实现单选行为):
  - "通用级 + 串口打印 (默认)" → sample_rate=normal_1hz, precision=normal, response_time=1s, output=["serial"]
  - "高性能 + 屏幕显示" → sample_rate=high_100hz_plus, precision=high, response_time=ms_level, output=["display_oled","serial"]
  - "低功耗 + 串口打印" → sample_rate=low_minute, precision=low_power_first, response_time=minute_level, output=["serial"]
  - "Other（逐项指定）"
```

若用户选 "Other" → 第二轮追加性能 + 输出各一问。

##### 第二轮（按需）

仅当 Q2~Q4 有 "Other" 或 "缺器件" 时追加补充。

---

#### 默认值汇总（用户不改的维度自动填充）

| 维度 | 小白模式 | 自定义模式 | 说明 |
|------|---------|-----------|------|
| scene | "indoor" | 由 Q2 推导 | |
| power | "usb" | 由 Q2 推导 | |
| network | "none" | 由 Q2/Q4 推导 | |
| sample_rate | "normal_1hz" | 由 Q3 推导 | |
| precision | "normal" | 由 Q3 推导 | |
| response_time | "1s" | 由 Q3 推导 | |
| temp_range | "normal_0_40" | 由 Q2 推导 | |
| size_constraint | "none" | "none" | 默认，不提 |
| budget_yuan | "medium_50" | "medium_50" | 默认，不提 |
| experience | "beginner" | "experienced" | 由分流决定 |
| existing_hardware | [] | [] | 默认，不提 |
| special_requirements | ["none"] | ["none"] | 默认，不提 |
| mcu_specified | "ESP32"（或用户选择） | 由 Q1 推导 | 记录型号，固件核验交给 upy-select-hw |

### Step 3: 驱动搜索

确认器件清单后，**对每个器件调用 `upy-pkg-guide` skill**。

> `upy-pkg-guide` 内部已支持：upypi 搜索 → awesome-micropython fallback（GitHub/GitLab/Codeberg）

```
对每个器件：
  调用 upy-pkg-guide → 结果分三种：

  A. 有驱动 → 记录 driver 信息（source/package/version/install_cmd/api_ref）

  B. 无驱动 + 器件型号是用户明确指定的
     → 标记 driver.source = "none"
     → 后续由 upy-cold-driver 处理

  C. 无驱动 + 器件型号是系统推荐的（用户未指定具体型号）
     → 触发 Step 3B：同类替代推荐
```

**并行策略：** 多个器件可同时调 `upy-pkg-guide`（无依赖关系）。

#### Step 3B: 同类替代推荐（仅情况 C 触发）

当系统推荐的器件找不到驱动，但用户并未指定具体型号时，**动态搜 upypi 找同类别有驱动的替代器件**。

upypi 支持模糊搜索，不需要维护静态替代列表。**每次触发 3B 都实时搜**：

```
对每个"情况 C"器件：
  1. 确定器件类别 + 接口类型（如 I2C 温湿度传感器）
  2. 多轮模糊搜 upypi（利用 upypi /api/search?q= 的模糊匹配）：
     第一轮：搜该类别最常用的芯片型号前缀
       温湿度 → "sht" "dht" "hdc" "aht" "bme" "si70"
       气压   → "bmp" "lps" "dps" "ms56" "ms58"
       屏幕   → "ssd" "sh" "st77" "st7789" "ili" "gc9"
       IMU    → "mpu" "icm" "bmi" "bno" "lsm" "adxl"
       距离   → "vl53" "tof" "sr04" "tfmini"
       光线   → "bh17" "tsl" "veml" "max440" "opt"
       麦克风 → "inmp" "ics" "sph" "msm" "max98" "max44"
       LED    → "ws28" "sk68" "apa102" "tm16" "max72"
       RTC    → "ds32" "ds13" "pcf85" "rv30"
       ADC    → "ads1" "mcp30" "mcp47" "pcf85" "hx71"
     第二轮：搜类别英文关键词（兜底，覆盖前缀遗漏的）
       温湿度 → "temperature" "humidity"
       气压   → "pressure" "barometer"
       ...
  3. 合并去重所有搜索结果
  4. 对每个结果调 upy-pkg-guide 确认有完整驱动
  5. 按流行度/驱动完整度排序，取 Top 2
```

**搜索规则：**
- 搜的是具体芯片型号前缀（"sht"、"bmp"），不是类别关键词（"temperature sensor"）
- 每个前缀单独搜，利用 upypi 模糊匹配
- 找到 2 个有完整驱动的就停，不需要全部搜完
- **不维护静态替代列表——每次都实时搜，数据永远是最新的**

输出替代推荐给用户确认：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SHT30 在 upypi/awesome-micropython/GitHub 均未找到驱动

  同类别（I2C 温湿度传感器）有现成驱动的替代：
  ┌────────────────────────────────────────────┐
  │  #  型号      驱动来源    安装命令            │
  │  1  HDC1080   upypi      mpremote mip ...   │
  │  2  AHT20     upypi      mpremote mip ...   │
  └────────────────────────────────────────────┘

  建议用 #1 HDC1080（精度高、价格相近、驱动成熟）
  是否接受？或者选择其他编号。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**确认后：** 用替代器件更新 devices 列表，填充 driver 信息，继续 Step 4。

**若替代搜索也无结果：** 该类别的所有器件都没有驱动 → 标记 `driver.source = "none"`，触发 upy-cold-driver。

### Step 4: 输出 manifest

调用 `init_manifest.py` 写入 `project-manifest.json`：

```bash
python G:/MicroPython_Skills/upy-analyze/scripts/init_manifest.py \
  --project-dir {project_dir} \
  --input {llm_output_json}
```

脚本校验 JSON 结构、补充元数据、写入项目目录。

**manifest 结构要点：**
- `phase`: "analyze"
- `requirements`: 所有 13 项用户确认的需求维度（含默认值）
- `devices`: 每个器件含 `driver` 对象（source/package_name/version/install_cmd/api_ref）
- `devices[].driver.source = "none"` → 无驱动器件，触发 cold-driver

---

## 输出示例

### 交互确认阶段（小白模式）

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  项目：温湿度监测报警器
  功能：定时采集温湿度 → 屏幕显示 → 超出阈值蜂鸣器报警
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 2A: 分流
  ● 小白模式：帮我自动推荐 (默认)
  ○ 自定义模式：我要逐项选择

Step 2B: 确认器件
  ☑ SHT30 — I2C温湿度传感器
  ☑ SSD1306 OLED — I2C屏幕
  ☑ 有源蜂鸣器 — GPIO
  ☐ 缺了器件，需补充

→ 全部默认 → 进入 Step 3 搜驱动
```

### 交互确认阶段（自定义模式）

```
Step 2A: 分流
  ○ 小白模式
  ● 自定义模式

Q1 [器件清单] (多选)
  ☑ SHT30 — I2C温湿度传感器
  ☑ SSD1306 OLED — I2C屏幕
  ☑ 有源蜂鸣器 — GPIO
  ☐ + 按键（建议，用于手动触发）
  ☐ 缺了器件

Q2 [场景供电] (单选)
  ● 室内桌面 + USB供电 (默认)
  ○ 室内 + 电池供电
  ○ 室外 + 电池/太阳能
  ○ Other

Q3 [性能等级] (单选)
  ● 通用级：1Hz + 常规精度 + 1秒响应 (默认)
  ○ 高性能：100Hz+ + 高精度 + 毫秒响应
  ○ 低功耗优先
  ○ Other

Q4 [输出方式] (多选)
  ☑ 串口打印 (默认)
  ☑ 屏幕显示
  ☑ 声光反馈
  ☐ WiFi/蓝牙上报
```

### manifest 节选

```json
{
  "schema_version": "1.0",
  "phase": "analyze",
  "project_name": "温湿度监测报警器",
  "requirements": {
    "description": "定时采集温湿度 → 屏幕显示 → 超过阈值蜂鸣器报警",
    "scene": "indoor",
    "power": "usb",
    "output": ["display_oled", "serial", "buzzer"],
    "experience": "beginner"
  },
  "devices": [
    {
      "name": "SHT30",
      "type": "temperature_sensor",
      "interface": "I2C",
      "i2c_addr": ["0x44", "0x45"],
      "driver": {
        "source": "upypi",
        "package_name": "sht30-driver",
        "version": "1.2.0",
        "install_cmd": "mpremote mip install https://upypi.net/pkgs/sht30-driver/1.2.0/package.json",
        "api_ref": { "init": "SHT30(i2c, addr=0x44)", "read": "sht30.measure() → (temp, humidity)" }
      }
    },
    {
      "name": "有源蜂鸣器",
      "type": "buzzer",
      "interface": "GPIO",
      "driver": { "source": "none" }
    }
  ]
}
```

---

## 与其他 skill 的关系

- ← 用户输入：自然语言项目描述
- → `upy-select-hw`：传入 manifest（含 devices + requirements），硬件选型 + 引脚分配
- → `upy-cold-driver`：对 `driver.source = "none"` 的器件，触发冷硬件驱动生成

## 强约束

- **不得在器件型号不明确时自行假设**——必须追问确认
- **所有需求维度必须有明确值**——用户未指定 = 默认值，不允许留空
- **不在此阶段生成代码、分配引脚、选择 MCU**
- **driver.source = "none" 也要写入 manifest**——让下游 skill 能感知到
- **manifest 中所有枚举值必须来自 schema**——不得自创枚举值
