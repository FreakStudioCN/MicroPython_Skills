# 板卡数据库说明文档

> 适用读者：插件端工程师、服务器端工程师、Skill 维护者
>
> 版本：2.0 / 最后更新：2026-06-16

---

## 1. 文件位置

```
G:\MicroPython_Skills\upy-analyze\boards\
├── README.md               ← 本文件
├── _template.json          ← 新增板卡用的模板（复制后填）
├── matching-rules.json     ← 板卡选型打分规则
├── esp32-devkit-v1.json    ← ESP32 DevKit V1
├── esp32-s3-devkitc.json   ← ESP32-S3-DevKitC-1
├── esp32-c3-devkitm.json   ← ESP32-C3-DevKitM-1
├── raspberry-pi-pico.json  ← Raspberry Pi Pico
├── raspberry-pi-pico-w.json← Raspberry Pi Pico W
├── esp8266-nodemcu.json    ← ESP8266 NodeMCU V3
└── m5stack-core.json       ← M5Stack Core (ESP32)
```

**一块板卡一个 JSON 文件**。文件名等于板卡 id，加 `.json` 后缀。

---

## 2. 模板怎么用

复制 `_template.json`，改名为 `{板卡id}.json`，按下面的字段说明逐项填写。模板里已经列出了所有字段，空的就留空，不用删。

模板里有两个部分是选填的：
- `onboard_peripherals`：板子自带了什么外设。纯 GPIO 开发板（ESP32 DevKit 之类）填空数组 `[]`
- `pin_layout.pin_options`：只有 RP2040/Pico 这种"引脚和外设固定绑定"的芯片才填。ESP32 系列留空对象 `{}`

---

## 3. 字段说明

### 3.1 基础信息（每块板卡必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识。命名规则：`{芯片}-{板型}`，全小写+连字符。如 `esp32-devkit-v1` |
| `display_name` | string | 插件 UI 显示的名称，用官方全称。如 `ESP32-S3-DevKitC-1` |
| `mcu` | string | MCU 完整型号，会出现在 BOM 表里。如 `ESP32-S3-WROOM-1` |
| `chip_family` | string | 芯片家族。可选值：`esp32` / `esp32s3` / `esp32c3` / `esp8266` / `rp2` |

### 3.2 固件信息（每块板卡必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `firmware.url` | string | MicroPython 官方下载页面 URL |
| `firmware.port` | string | MicroPython 端口：`esp32` / `rp2` / `esp8266` |
| `firmware.board_name` | string | 编译时的板卡目标名，如 `ESP32_GENERIC_S3` |
| `firmware.latest_version` | string | 已知最新固件版本号 |

板卡一旦选定，固件 URL 就确定了。`upy-select-hw` 不再去网上搜固件。

### 3.3 硬件规格（每块板卡必填）

specs 里共 13 个字段。按 AI 用到的频率分三档：

**★★★ 影响 AI 选型和代码生成，必须填准：**

| 字段 | 类型 | AI 怎么用 |
|------|------|---------|
| `flash_mb` | number | 判断文件系统能不能放下所有驱动 + 日志 |
| `psram_mb` | number | 0=无 PSRAM，分配大 buffer 时 AI 会提示风险 |
| `gpio` | number | 外设多+GPIO 少 → AI 会警告引脚不够 |
| `i2c` | number | I2C 器件多但控制器少 → 建议软 I2C |
| `spi` | number | SPI 器件多但控制器少 → 建议共享总线 |
| `wifi` | boolean | 联网需求 vs 板卡能力匹配 |
| `ble` | boolean | 蓝牙需求 vs 板卡能力匹配 |

**★★ 引脚分配时会参考，尽量填准：**

| 字段 | 类型 | AI 怎么用 |
|------|------|---------|
| `pwm` | number | 舵机/LED 调光需要 PWM 通道 |

**★ 板卡详情页展示用，填了更好，没填也不影响 AI 决策：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `adc` | number | 模拟输入通道数 |
| `dac` | number | 模拟输出通道数 |
| `uart` | number | 硬件串口数量 |
| `touch` | number | 触摸引脚数 |
| `usb_otg` | boolean | 是否支持 USB 设备模式 |

### 3.4 选购信息（每块板卡必填）

| 字段 | 类型 | 说明 |
|------|------|------|
| `typical_use_cases` | string[] | 典型用途。插件用做筛选标签，LLM 用做选型匹配 |
| `beginner_friendly` | boolean | 是否适合新手。upy-analyze 小白模式下优先推荐 |
| `price_yuan` | number | 参考价格（人民币），展示用 |
| `notes` | string | 给用户看的备注。**LLM 也会读这一段做判断**。写关键技术限制、兼容性警告、和其他板卡的关键区别 |

### 3.5 板载外设 `onboard_peripherals`（选填）

**什么时候填：** 板子上自带了屏幕、传感器、按键等外设（不只是指示灯）。

**什么时候空数组：** 纯 GPIO 开发板，比如 ESP32 DevKit 就板载一个 LED，写一条占位或直接空数组。

每条外设的字段：

| 字段 | 类型 | 必须 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 外设名称，如 "ILI9342C LCD" |
| `type` | string | 是 | 类别。可选：`display` / `sensor` / `imu` / `button` / `led` / `led_rgb` / `speaker` / `storage` / `power_mgmt` / `wifi_module` / `usb_uart` |
| `interface` | string | 是 | I2C / SPI / GPIO / I2S / UART |
| `occupied_pins` | object | 是 | 占用了哪些引脚。键=功能名，值=GPIO 号。-1 表示不占 GPIO |
| `i2c_addr` | string | I2C器件必填 | I2C 地址，如 "0x68" |
| `driver` | object? | 有已知驱动时填 | 驱动信息（见下面小表） |
| `always_used` | boolean | 是 | true=这个脚肯定被占了，引脚分配跳过。false=用户可以不启用这个外设，脚能释放 |
| `notes` | string | 否 | 补充说明 |

driver 对象（有已知驱动时填）：

| 字段 | 说明 |
|------|------|
| `source` | 驱动来源，通常是 `"upypi"` |
| `package_name` | upypi 上的包名 |
| `url` | 驱动页面或 API 链接 |
| `install_cmd` | mpremote 安装命令 |

**注意：** 不确定的驱动不要填。只有经过验证、确认这个驱动能在这个板卡这个外设上跑通的，才填 driver 信息。否则留空，让 AI 自己搜。

### 3.6 引脚布局 `pin_layout`（每块板卡必填）

不同芯片的引脚分配方式完全不同。先看 `model` 字段：

| model | 适用芯片 | 含义 |
|-------|---------|------|
| `"flexible"` | ESP32 / ESP32-S3 / ESP32-C3 / ESP8266 | I2C/SPI/UART 可以映射到任意空闲 GPIO。约束来自"哪些脚不能碰" |
| `"fixed"` | RP2040 / Pico | 每个外设功能只能从固定的几个脚里选。约束来自"哪些脚能用" |

#### flexible 模型

**等于是"告诉 AI 避开雷区，剩下的随便分"。**

`default_bus_pins`：每路总线的一组默认引脚。AI 优先用这些，不行再换。格式：

```json
"default_bus_pins": {
  "i2c0": { "sda": 21, "scl": 22 },
  "spi0": { "mosi": 23, "miso": 19, "clk": 18, "cs": 5 },
  "uart0": { "tx": 1, "rx": 3 }
}
```

`restricted_gpio`：不能碰的引脚，按原因分类：

| 类别 | 含义 | 示例 |
|------|------|------|
| `input_only` | 只能做输入，不能输出/上下拉 | ESP32 GPIO 34-39 |
| `strapping` | 启动时决定工作模式，乱接可能导致板子起不来 | ESP32 GPIO 0/2/5/12/15 |
| `flash_psram_occupied` | 被 Flash/PSRAM 内部占用，外面看不到 | ESP32 GPIO 6-11 |
| `adc2_wifi_conflict` | 开 WiFi 时 ADC2 不可靠 | ESP32 大部分 ADC2 通道 |
| `usb_otg_pins` | USB OTG 专用，挪作他用就失去 USB 功能 | ESP32-S3 GPIO 19/20 |
| `usb_serial_pins` | USB 串口脚，调试下载用的 | ESP32-C3 GPIO 18/19 |
| `boot_fail_risk` | 不一定会导致启动失败，但历史上有人踩过坑 | ESP8266 GPIO 0/1/2/3/9/10 |
| `wifi_chip_occupied` | 被 WiFi 模组内部占用 | Pico W GPIO 23/24/25 |
| `onboard_occupied` | 汇总：所有被板载外设占用的引脚列表 | M5Stack 各种外设脚 |

`pin_options`：flexible 模型下留空 `{}`。

#### fixed 模型

**等于"告诉 AI 每个功能只能从哪几个脚里选"。**

`default_bus_pins`：同上，填数组即可。

`restricted_gpio`：同上，填不能被占用的脚。

`pin_options`：**这是 fixed 模型的关键字段。** 列出每个外设功能的可选引脚：

```json
"pin_options": {
  "i2c0_sda": [0, 4, 8, 12, 16, 20],
  "i2c0_scl": [1, 5, 9, 13, 17, 21],
  "spi0_mosi": [3, 7, 11, 15, 19, 23],
  ...
}
```

SDA 和 SCL 必须从同一组里成对选。比如选了 I2C0 SDA=8，就必须用 SCL=9，不能混搭。

---

## 4. matching-rules.json 说明

LLM 做板卡选型时的打分规则。每条规则包含：

| 字段 | 说明 |
|------|------|
| `id` | 规则 ID |
| `trigger` | 触发条件（给人读的，LLM 判断是否触发） |
| `action` | `boost`（加分）或 `exclude`（排除） |
| `chip_families` | 适用哪些 chip_family |
| `note` | 补充说明 |

用法：
1. LLM 读取用户 requirements，判断触发哪些规则
2. 对每块板卡：boost 规则匹配 chip_family → 加分；exclude 规则匹配 → 排除
3. 得分最高的两块板卡作为推荐
4. 排除的不一定是板卡不行，可能是不适合当前场景（比如多 I2C 器件时排除只有 1 路 I2C 的板卡）

---

## 5. 插件端怎么用

### 5.1 获取板卡列表

**本地测试阶段：** 插件直接读本目录的 JSON 文件。

**生产阶段：** 服务器提供 API，插件调用：
```
GET /v1/boards
→ { version: "2.0", boards: [...] }
```

服务器启动时扫描本目录所有 `*.json`（除了 `_template.json` 和 `matching-rules.json`），合并后返回。

### 5.2 渲染板卡画廊

插件侧边栏渲染板卡选择器时用这些字段：

| UI 位置 | 字段 |
|---------|------|
| 卡片标题 | `display_name` |
| 芯片型号 | `mcu` |
| 关键规格 | `specs.wifi`, `specs.ble`, `specs.gpio`, `specs.i2c`, `specs.spi` |
| 新手标记 | `beginner_friendly` → "新手推荐" 徽章 |
| 价格标签 | `price_yuan` |
| 用途标签 | `typical_use_cases`（可点击筛选） |
| 详情弹窗 | 全部 specs 13 项 + `onboard_peripherals` 列表 + `pin_layout.notes` |

### 5.3 用户选了板卡之后

插件把选中板卡的精简信息放入请求：

```json
{
  "pre_selected_board": {
    "id": "esp32-devkit-v1",
    "display_name": "ESP32 DevKit V1",
    "mcu": "ESP32-WROOM-32",
    "chip_family": "esp32",
    "firmware_url": "https://micropython.org/download/ESP32_GENERIC/"
  }
}
```

只传这 5 个字段，完整 specs 和 pin_layout 等 skill 需要时再从服务器端读完整 JSON。

---

## 6. 会更新/会过期的字段

| 字段 | 更新频率 | 谁来更新 |
|------|---------|---------|
| `firmware.latest_version` | MicroPython 发新版时 | 服务器 CI 自动检查并更新 |
| `firmware.url` | MicroPython 改下载地址时（极少） | 手动更新 |
| `price_yuan` | 市场波动 | 人工维护，半年看一次 |
| `specs` 数值 | 不会变（芯片出厂就定了） | 不需要更新 |
| `driver` 信息 | upypi 包更新或改名时 | 人工验证后更新 |

---

## 7. 新增一块板卡的步骤

1. 复制 `_template.json`，改名为 `{板卡id}.json`
2. 填写基础信息（id / display_name / mcu / chip_family）
3. 填写 firmware（去 micropython.org/download 查找对应的 board_name 和 URL）
4. 填写 specs（查芯片数据手册，13 项按实际情况填）
5. 填写 typical_use_cases / beginner_friendly / price_yuan / notes
6. 填写 onboard_peripherals：
   - 板子只带一个 LED → 写一条或空数组
   - 板子带了屏幕/传感器/按键 → 每条外设写 occupied_pins、有没有驱动链接
7. 填写 pin_layout：
   - ESP32/ESP8266 → model: "flexible"，填 default_bus_pins + restricted_gpio，pin_options 留空
   - RP2040/Pico → model: "fixed"，填所有字段包括 pin_options
8. 检查 matching-rules.json：新 chip_family 有没有对应的规则，没有就加
9. 验证：`python -c "import json; json.load(open('{新文件}.json'))"` 不报错
10. 提交

新增板卡不需要改插件代码——插件从 API 拉取列表后动态渲染。
