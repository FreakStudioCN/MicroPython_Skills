---
name: upy-autofix
description: 第六步——编排协调层。读取设备日志，解析错误，分级决策后委托上游 skill 修复（generate/select-hw/analyze），最多 3 次尝试。触发：upy-deploy 运行失败后自动进入。
---

# 自动化调试闭环 Skill

## 角色定位

**编排协调层，不是独立修复机。** 核心逻辑：`triage.py` 采集结构化数据 → LLM 读取 JSON + 原始日志 → 分级决策 → 委托上游 skill 修复 → 验证。

脚本只做数据采集 + git 管理 + 硬件信号驱动，不做修复决策。所有判断由 LLM 完成。

**新增：硬件信号验证能力** — 软件修复 2 次无效后，autofix 可以主动驱动外设（LED 闪烁/蜂鸣器响/传感器读数/显示器填色），通过自检或用户反馈判定硬件是否正常，避免在坏硬件上无限循环修代码。

---

## 前置条件

- `upy-deploy` Phase 6 判定 FAIL
- `deploy_logs/` 目录下有设备端原始日志文件（`run_*.log`）
- `triage.py` 可用（本 skill 自带的脚本）

---

## 执行步骤

### Step 1: 运行 triage.py 采集结构化数据

```bash
python G:/MicroPython_Skills/upy-autofix/scripts/triage.py \
  --log-dir {deploy_logs路径} \
  --port {COM} \
  --attempt 1
```

输出 JSON 到 stdout，LLM 捕获并解析。JSON 结构见 `triage.py` 文件头部注释。

**每个字段都有默认值**——脚本已做 try/except，不会因日志格式异常而崩溃。`warnings` 字段列出所有降级情况。

### Step 2: LLM 综合研判

LLM 同时读取两个信息源：

| 来源 | 作用 | 何时读 |
|------|------|--------|
| triage.py JSON | 快速定位：错误类型、P 级别、I2C 状态、attempt 计数 | 每次都读 |
| deploy_logs/*.log 原始日志 | 深度理解：完整 traceback、print 时序、上下文 | JSON 不足以判断时 |

**研判顺序：**

1. 先看 JSON 的 `i2c_ok` 字段
   - `false` → 硬件问题，跳 Step 5（输出排查指引），**不修代码**
   - `true` 或 `null`（无 I2C 设备）→ 软件问题，继续

2. 看 JSON 的 `p_level` + `error_type`
   - P0 拼写/import → LLM 直接 Edit 文件（一行修复，不值得启动上游 skill）
   - P0 驱动 API 错误 → Step 3 委托 upy-generate
   - P1 引脚/地址冲突 → Step 3 委托 upy-select-hw
   - P1 看门狗/内存 → Step 3 委托 upy-generate
   - P2 传感器异常 → Step 3 委托 upy-generate
   - P3 死循环/无输出 → Step 3 委托 upy-generate
   - `unknown` → 读原始日志，LLM 独立判断错误类型后走对应路径

3. 判断是否需要硬件信号验证（Step 2.5）——**任一满足即触发：**
   - `attempt >= 2` 且同一 `error_type` 连续出现 → 软件修复无效，怀疑硬件
   - `error_type` = `"NoOutput"` 或 `"unknown"` → 代码跑了但没产出，怀疑沉默外设
   - `error_type` = `"OSError_19"` 或 `"OSError_110"` → 外设通信失败，可能是接线/供电

### Step 2.5: 硬件信号验证

当 Step 2 触发条件命中时，不直接进入软件修复。先做硬件诊断。

#### Step 2.5A: LLM 读取源码 + 生成诊断配置

LLM 通读 firmware/ 全部 .py 源码 + project-manifest.json：

```
识别对象:
  ├── machine.Pin(x)     → GPIO 引脚, 外设角色(从变量名/上下文推断)
  ├── machine.PWM(Pin(x)) → PWM 输出 (LED/蜂鸣器/舵机)
  ├── machine.I2C(...)   → I2C 总线 + 从设备地址
  ├── machine.SPI(...)   → SPI 总线 + CS 引脚
  ├── machine.UART(...)  → UART 总线 + 波特率
  ├── machine.ADC(Pin(x)) → 模拟输入
  └── from xxx import Xxx → 驱动类实例化, __init__ 参数模式
```

然后按**附录 A** 的模板，为每个外设生成 `sanity_config.json`：

**生成原则：**
- 自检型优先：I2C/SPI 传感器、ADC/DAC、UART(命令响应型) 走自动判定
- 反馈型仅对纯输出：LED/Buzzer/Relay/显示器/电机 需要问用户
- 板载 LED 率先测试：如果连 LED 都点不亮 → MCU 供电/复位问题
- 最大 8 个测试，单个 timeout 10s

```bash
python G:/MicroPython_Skills/upy-autofix/scripts/hardware_sanity.py \
  --config {project_dir}/sanity_config.json \
  --port {COM}
```

输出 JSON 到 stdout，LLM 捕获。

#### Step 2.5B: LLM 解读结果

```
读 JSON:
  ├── 全部 PASS → 硬件正常，问题在代码逻辑 → 继续 Step 3 委托修复
  │
  ├── 特定外设 FAIL (I2C 传感器 scan 失败 / 读 WHO_AM_I 不匹配)
  │     → 输出该外设定向排查指引 (接线/供电/地址冲突)
  │     → 不继续修代码
  │
  ├── 特定外设 FAIL (用户反馈型: LED不亮/蜂鸣器不响)
  │     → 输出该外设定向排查指引
  │     → 不继续修代码
  │
  ├── 板载 LED 也 FAIL → MCU 供电/复位/USB 线问题
  │     → 输出基础排查指引 (换USB线/换供电口/检查EN引脚)
  │
  └── pending_feedback == true
        → AskUserQuestion 逐条询问（每条一问）
        → 收集回答后重新判定
```

#### Step 2.5C: 处理用户反馈

`hardware_sanity.py` 对 `user_feedback` 模式的测试会在结果中标记 `_pending_question`。LLM 读取后：

```
对每条 pending:
  AskUserQuestion(
    question: result._pending_question,
    header: "硬件诊断",
    options: ["是，正常", "否，没有反应"]
  )

用户回答后:
  "是" → 该外设 status = "pass"
  "否" → 该外设 status = "fail"
```

**反馈汇总后再判定一次**：
- 全部 PASS → 继续软件修复
- 任一 FAIL → 输出该外设的排查指引

**最多让用户回答 3 个问题**。如果有 4+ 个反馈型外设，优先测"最可能故障"的那个（根据 triage error_type 指向）。

---

### Step 3: 委托上游 skill 修复

LLM 使用 `Skill` 工具调用上游 skill，**打包 error context**：

**委托 upy-generate 时传入：**
- 原始 traceback（从 JSON 或原始日志提取）
- 报错文件路径 + 行号
- 涉及的驱动名称
- project-manifest.json 路径
- 前几次尝试的修改内容 + 失败原因（attempt > 1 时）

**委托 upy-select-hw 时传入：**
- 当前引脚冲突详情
- project-manifest.json 路径

**委托 upy-analyze 时传入：**
- 缺失的传感器/功能说明
- 用户原始需求描述

### Step 4: 验证修复结果

每次修复后的验证路径：

```
修复完成
  ↓
可选：Skill("upy-simulate") PC 端快速验证（2-3s，省去串口烧录延迟）
  ↓
Skill("upy-deploy") 重新烧录运行
  ↓
再次运行 triage.py（--attempt N+1）
  ↓
读 JSON：
  ├─ status="pass" → 成功，输出 PASS 摘要
  └─ status="fail" → 回到 Step 2 重新研判（可能升级回退层级）
```

**升级规则**：同一策略连续失败 → 向上一级回退（P0 直接改 → P0 委托 generate → P1 委托 select-hw → 需求层面 analyze）。

### Step 5: 硬件问题 — 输出排查指引

当 `i2c_ok: false`（已尝试 software I2C + 降速均无效）时，LLM 直接输出以下中文指引，**不修代码**：

```
I2C 总线扫描不到设备，已尝试 software I2C 和低速模式，均无响应。这是硬件连接问题，请按以下顺序排查：

1. 接线检查：
   - SDA/SCL/VCC/GND 每根线用万用表通断档确认导通
   - VCC 接 3.3V（不是 5V！）
   - GND 必须与 MCU 共地

2. 供电检查：
   - 模块电源指示灯是否亮？
   - VCC 引脚电压是否为 3.3V ± 0.1V？

3. 上拉电阻：
   - SDA/SCL 各需 4.7kΩ 上拉到 3.3V
   - 部分模块自带，部分没有——检查你的模块

4. 传感器本身：
   - 是否发热异常？
   - 替换另一块同型号传感器测试

5. 冲突检查：
   - 拔掉其他外设，只接这一个传感器测试

排查完成后发送"重新部署"重试。
```

### Step 6: 3 次全败 — 回滚 + 总结

```bash
python G:/MicroPython_Skills/upy-autofix/scripts/triage.py --rollback --log-dir {deploy_logs路径}
```

然后 LLM 输出中文卡点报告：

```
自动修复 3 次未成功。

错误类型：{error_type}
3 次尝试：
  1. {strategy1} → {result1}
  2. {strategy2} → {result2}
  3. {strategy3} → {result3}

git 已回滚到修复前状态。

建议手动排查方向：{具体建议}
```

### Step 7: 错误数据记录

triage.py 自动将每次修复的历史写入 `logs/error_report.json`（追加模式），包含：时间戳、MCU 型号、错误类型、traceback、每次尝试的策略和结果、使用的 skill 版本。

LLM 在 3 次全败时额外补充 `llm_analysis` 字段（根因分析 + 知识盲区标记）。

---

## 与其他 skill 的关系

```
upy-deploy FAIL
    ↓
upy-autofix (本 skill)
    ├── triage.py → 采集数据
    ├── LLM 研判
    ├── [新增] hardware_sanity.py → 硬件信号驱动验证
    ├── 委托 → upy-generate（代码修复）
    ├── 委托 → upy-select-hw（引脚/地址修复）
    ├── 委托 → upy-analyze（需求重新分析）
    ├── 可选验证 → upy-simulate（PC 快速验证）
    ├── 重新部署 → upy-deploy
    └── 失败回流 → CI/CD 反馈到各 skill SKILL.md
```

- ← `upy-deploy`：接收 FAIL 判定 + deploy_logs/ 日志
- ⇄ `upy-generate`：委托代码修复
- ⇄ `upy-select-hw`：委托引脚/地址重新分配
- ⇄ `upy-analyze`：委托需求重新分析
- ⇄ `upy-simulate`：可选 PC 验证
- ⇄ `upy-deploy`：修复后重新烧录

---

## 强约束

- **triage.py 不做修复决策**：只采集数据输出 JSON，LLM 读 JSON + 原始日志后独立判断
- **hardware_sanity.py 不做诊断决策**：只执行测试代码 + 采集结果/用户反馈，LLM 根据结果 JSON 做判定
- **硬件检测必须最先做**：I2C 扫描为空 → 直接输出排查指引，不进入修复循环
- **硬件信号验证触发条件**：`attempt >= 2` 连续同错误 / `NoOutput` / `OSError_19/110` — 不浪费用户时间
- **自检型优先于反馈型**：能自动判定的绝不问用户；单个 sanity check 最多让用户回答 3 个问题
- **板载 LED 先测**：如果连 LED 都点不亮 → MCU 供电/复位问题，不测其他外设
- **外设明确 FAIL (自检失败 或 用户回答 NO)**：直接终止修复循环，输出排查指引，不继续修代码
- **每次修复前 git commit 保存快照**（triage.py `--snapshot`）
- **最多 3 次尝试**：3 次全败 → git 回滚 + 输出卡点报告
- **LLM 必须读原始日志**：triage.py JSON 可能 `error_type: "unknown"`，此时 LLM 必须从原始日志独立判断
- **P0 拼写/import 由 LLM 直接 Edit**：不值得启动 upstream skill 的开销
- **所有其他修复必须委托上游 skill**：autofix 自己不写修复代码
- **错误数据回流**：每次修复记录到 `error_report.json`，驱动 CI/CD 持续改进
- **Windows 平台：禁止在 main.py 运行时读取设备日志**：`mpremote fs cp` 和 `resume exec` 在 Windows 上进入 raw REPL 模式（发送 Ctrl+C），会杀死正在运行的 main.py。而且被杀死的进程可能未 flush 日志文件，读到空文件会误判"无日志输出"。正确做法：让 main.py 运行到自然结束或崩溃 → 软复位后（程序已停）再 `fs cp` 抓日志。如需在运行时检查设备状态，用 `hardware_sanity.py` 的 I2C 扫描（独立于 main.py 进程）

---

## 附录 A: 外设硬件验证代码模板

LLM 读取 firmware/ 源码识别外设类型后，按以下模板生成 `sanity_config.json` 中的 test code。

**模板结构：**
```json
{
  "id": "peripheral_name_sanity",
  "category": "i2c_sensor|spi_sensor|uart|gpio_out|display|adc|dac|input",
  "mode": "self_verify|user_feedback",
  "label": "中文名 (引脚/地址)",
  "code": "完整 MicroPython 代码, mpremote exec 执行",
  "pass_pattern": "SCAN_OK|CHIP_OK|FRAME_OK|ADC_OK|DAC_OK|TEST_DONE",
  "fail_pattern": "SCAN_FAIL|CHIP_FAIL|FRAME_FAIL",
  "value_key": "TEMP|VOLT|RAW",
  "value_range": [min, max],
  "question": "仅 user_feedback 模式: AskUserQuestion 的问题",
  "timeout_ms": 10000
}
```

### A1: I2C 传感器 (self_verify)

**识别信号**: `__init__(i2c, address=0x??)` 或 `I2C(0, scl=Pin(x), sda=Pin(y))`

**自检步骤**: i2c.scan() 确认地址 → (可选) 读 WHO_AM_I/CHIP_ID → 读一次数据 → 物理合理范围判定

**通用模板**:
```python
from machine import I2C, Pin
i2c = I2C({bus_id}, scl=Pin({scl}), sda=Pin({sda}), freq=400000)
addrs = [hex(a) for a in i2c.scan()]
if '{expected_addr}' in addrs:
    print('SCAN_OK')
else:
    print('SCAN_FAIL:' + str(addrs))
# 读一次数据
from {driver_module} import {DriverClass}
s = {DriverClass}(i2c, address={addr_int})
try:
    r = s.{read_method}()
    print('VALUE:' + str(r))
except Exception as e:
    print('READ_ERR:' + str(e))
```

**示例 — BMP280 (地址 0x76)**:
```python
from machine import I2C, Pin
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
addrs = [hex(a) for a in i2c.scan()]
if '0x76' in addrs:
    print('SCAN_OK')
else:
    print('SCAN_FAIL:' + str(addrs))
from bmp280_float import BMP280
s = BMP280(i2c, address=0x76)
data = s.read_compensated_data()
print('TEMP:' + str(data[0]) + ',' + 'PRESS:' + str(data[1]))
```
`pass_pattern: "SCAN_OK"`, `value_key: "TEMP"`, `value_range: [-40, 85]`

---

### A2: SPI 传感器 (self_verify)

**识别信号**: `__init__(spi, cs)` 或 `SPI(1, sck=Pin(x), mosi=Pin(y), miso=Pin(z))`

**自检步骤**: 读 WHO_AM_I / CHIP_ID / DEVICE_ID 寄存器 → 与 datasheet 预期值比对

**通用模板**:
```python
from machine import SPI, Pin
spi = SPI({bus_id}, sck=Pin({sck}), mosi=Pin({mosi}), miso=Pin({miso}))
cs = Pin({cs}, Pin.OUT)
cs.value(1)
# 读 WHO_AM_I 寄存器
cs.value(0)
spi.write(bytearray([0x80 | {who_am_i_reg}]))
resp = spi.read(1)
cs.value(1)
if resp[0] == {expected_id}:
    print('CHIP_OK:' + hex(resp[0]))
else:
    print('CHIP_FAIL: expected ' + hex({expected_id}) + ' got ' + hex(resp[0]))
```
`pass_pattern: "CHIP_OK"`, `fail_pattern: "CHIP_FAIL"`

**示例 — ADXL345**:
```python
from machine import SPI, Pin
spi = SPI(1, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
cs = Pin(9, Pin.OUT); cs.value(1)
cs.value(0)
spi.write(bytearray([0x80]))  # DEVID register
resp = spi.read(1)
cs.value(1)
if resp[0] == 0xE5:
    print('CHIP_OK')
else:
    print('CHIP_FAIL: got ' + hex(resp[0]))
```
`pass_pattern: "CHIP_OK"`, `fail_pattern: "CHIP_FAIL"`

---

### A3: UART 外设 (self_verify)

**识别信号**: `__init__(uart)` 或 `UART(1, baudrate=9600, tx=Pin(x), rx=Pin(y))`

**自检步骤**: 发查询命令 → 等响应 → 超时判定

**通用模板**:
```python
from machine import UART, Pin
import time
u = UART({uart_id}, baudrate={baud}, tx=Pin({tx}), rx=Pin({rx}), timeout=2000)
u.write(b'{query_cmd}')
time.sleep(0.5)
resp = u.read()
if resp and len(resp) > 0:
    print('FRAME_OK:' + str(resp[:32]))
else:
    print('FRAME_FAIL: no response')
```
`pass_pattern: "FRAME_OK"`, `fail_pattern: "FRAME_FAIL"`

**示例 — PMS7003 (主动模式，等数据帧)**:
```python
from machine import UART, Pin
import time
u = UART(2, baudrate=9600, tx=Pin(17), rx=Pin(16), timeout=5000)
t0 = time.time()
while time.time() - t0 < 5:
    if u.any():
        d = u.read()
        if d and len(d) >= 2 and d[0] == 0x42 and d[1] == 0x4D:
            print('FRAME_OK: start bytes valid')
            break
else:
    print('FRAME_FAIL: no valid frame in 5s')
```
`pass_pattern: "FRAME_OK"`, `fail_pattern: "FRAME_FAIL"`

**示例 — SIM800/SIM7600 (AT 指令)**:
```python
from machine import UART, Pin
import time
u = UART(2, baudrate=115200, tx=Pin(17), rx=Pin(16), timeout=3000)
u.write(b'AT\r\n')
time.sleep(1)
resp = u.read()
if resp and b'OK' in resp:
    print('FRAME_OK: AT response')
else:
    print('FRAME_FAIL: ' + str(resp))
```

---

### A4: GPIO 输出 (user_feedback)

**识别信号**: `__init__(pin: int)` → Pin(x, Pin.OUT) 或 PWM(Pin(x))

**测试步骤**: PWM/电平周期性变化 ×3 → 问用户

**通用模板**:
```python
from machine import Pin, PWM
import time
p = PWM(Pin({pin}), freq=1000)
for i in range(3):
    p.duty_u16(32768); time.sleep(0.3)
    p.duty_u16(0); time.sleep(0.3)
p.deinit()
print('TEST_DONE')
```
`pass_pattern: "TEST_DONE"`, `question: "{label} {动作描述}？(y/n)"`

**变体 — LED**:
```python
from machine import Pin, PWM
import time
p = PWM(Pin({pin}), freq=1000)
for _ in range(3):
    for d in range(0, 65535, 16384):  # 渐亮
        p.duty_u16(d); time.sleep(0.05)
    p.duty_u16(0); time.sleep(0.2)
p.deinit()
print('TEST_DONE')
```
`question: "LED({pin}引脚) 闪烁了3次吗？"`

**变体 — 蜂鸣器**:
```python
from machine import Pin, PWM
import time
p = PWM(Pin({pin}), freq=1000)
for f in [440, 660, 880]:  # A4, E5, A5
    p.freq(f); p.duty_u16(32768)
    time.sleep(0.25)
    p.duty_u16(0)
    time.sleep(0.1)
p.deinit()
print('TEST_DONE')
```
`question: "蜂鸣器响了3声吗？"`

**变体 — 继电器**:
```python
from machine import Pin
import time
p = Pin({pin}, Pin.OUT)
for _ in range(3):
    p.value(1); time.sleep(0.3)
    p.value(0); time.sleep(0.3)
print('TEST_DONE')
```
`question: "听到继电器咔哒声了吗？"`

---

### A5: 显示器 (user_feedback)

**识别信号**: `__init__(i2c/spi, ...)` + `.fill()` / `.show()` 方法

**测试步骤**: 全屏交替填充 → 问用户

**通用模板**:
```python
from machine import {bus_type}, Pin
{init_code}
# 全屏闪烁
display.fill(1); display.show()
import time; time.sleep(0.5)
display.fill(0); display.show()
time.sleep(0.5)
display.fill(1); display.show()
print('TEST_DONE')
```
`question: "{label} 屏幕闪烁了吗？"`

**示例 — SSD1306 (I2C)**:
```python
from machine import I2C, Pin
from ssd1306 import SSD1306
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
display = SSD1306(128, 64, i2c)
display.fill(1); display.show()
import time; time.sleep(0.5)
display.fill(0); display.show()
time.sleep(0.5)
display.fill(1); display.show()
print('TEST_DONE')
```

**示例 — ST7789 (SPI, 彩色)**:
```python
from machine import SPI, Pin
from st7789 import ST7789
spi = SPI(1, sck=Pin(10), mosi=Pin(11), miso=Pin(12))
dc = Pin(8, Pin.OUT); cs = Pin(9, Pin.OUT); rst = Pin(7, Pin.OUT)
display = ST7789(spi, 240, 240, dc=dc, cs=cs, rst=rst)
import time
for color in [0xF800, 0x07E0, 0x001F]:  # 红→绿→蓝
    display.fill(color); time.sleep(0.5)
print('TEST_DONE')
```
`question: "屏幕显示红→绿→蓝了吗？"`

---

### A6: ADC (self_verify)

**识别信号**: `__init__(i2c, address=0x??)` + `read()` 含 channel/gain 参数

**自检步骤**: 读悬空通道 vs 读 VCC 或固定电压 → 差值判定

**通用模板**:
```python
from machine import I2C, Pin
i2c = I2C({bus_id}, scl=Pin({scl}), sda=Pin({sda}))
from {driver_module} import {DriverClass}
adc = {DriverClass}(i2c, address={addr})
import time
r1 = adc.read(channel1=0)
time.sleep(0.1)
r2 = adc.read(channel1=0)
diff = abs(r1 - r2)
if diff < 50:
    # 读数太稳定可能是悬空读噪声 或 短路
    # 尝试读另一个通道
    r3 = adc.read(channel1=3)
    if abs(r1 - r3) > 100:
        print('ADC_OK: ch0=' + str(r1) + ', ch3=' + str(r3))
    else:
        print('ADC_FAIL: all channels same ~' + str(r1))
else:
    print('ADC_OK: fluctuation ' + str(diff))
```
`pass_pattern: "ADC_OK"`, `fail_pattern: "ADC_FAIL"`

---

### A7: DAC (self_verify)

**识别信号**: `__init__(i2c, address=0x??)` + `write()` + `read()` (有读回)

**自检步骤**: write(中值) → read() → 对比

**通用模板**:
```python
from machine import I2C, Pin
i2c = I2C({bus_id}, scl=Pin({scl}), sda=Pin({sda}))
from {driver_module} import {DriverClass}
dac = {DriverClass}(i2c, address={addr})
dac.write(2048)
import time; time.sleep(0.05)
state = dac.read()
if state and len(state) >= 2:
    val = (state[0] << 4) | (state[1] >> 4)
    if abs(val - 2048) < 100:
        print('DAC_OK: wrote=2048, read=' + str(val))
    else:
        print('DAC_FAIL: wrote=2048, read=' + str(val))
else:
    print('DAC_FAIL: no response')
```
`pass_pattern: "DAC_OK"`, `fail_pattern: "DAC_FAIL"`

**变体 — 无 read() 的 DAC** (如部分 MCP4725 实现):
不测值回读，改为 `write(0) → write(2048) → write(0)` 接万用表测电压，此时降级为 `user_feedback` 模式。`question: "DAC 输出引脚电压在 write(0) 和 write(2048) 之间有变化吗？"`

---

### A8: 输入器件 (user_feedback, 半自检)

**识别信号**: `__init__(pin, ...)` + 含 callback/idle_state/debounce

**测试步骤**: 读初值 → 打印 → 等待 → 读终值

**通用模板**:
```python
from machine import Pin
import time
p = Pin({pin}, Pin.IN, Pin.PULL_UP)
print('INIT_VAL:' + str(p.value()))
time.sleep(6)  # 给用户操作时间
print('FINAL_VAL:' + str(p.value()))
```
`question: "请在6秒内{操作描述}（按按钮/旋转编码器/在PIR前移动），REPL 输出的 INIT_VAL 和 FINAL_VAL 值变化了吗？"`

**示例 — 按钮**:
```python
from machine import Pin
import time
p = Pin(5, Pin.IN, Pin.PULL_UP)
print('INIT:' + str(p.value()))
time.sleep(6)
print('FINAL:' + str(p.value()))
print('TEST_DONE')
```
`question: "请在6秒内按下按钮，REPL 中 INIT 和 FINAL 的值变化了吗？"`

---

### A9: 板载 LED 基础测试 (self_verify 降级为 headless)

**何时用**: 任何 sanity check 的第一步。如果这个失败，不用测其他外设。

```python
from machine import Pin
import time
led = Pin({pin}, Pin.OUT)
for _ in range(4):
    led.value(1); time.sleep(0.2)
    led.value(0); time.sleep(0.2)
print('LED_OK')
```
`pass_pattern: "LED_OK"`, `question: "板载LED闪烁了吗？"`

注意：板载 LED 虽属 GPIO 输出，但它是 MCU 供电/复位/烧录成功的最基本标志。如果 LED_OK 都不打印 → 设备根本没进入 REPL。

---

### 生成 sanity_config.json 的决策树

```
LLM 读 firmware/ 源码:
    │
    ├── 找到 Pin(x, Pin.OUT) / PWM(Pin(x)) 且变量名含 "led"
    │     → A9: 板载 LED 基础测试 (优先级最高，放 config.tests[0])
    │
    ├── 找到 I2C(0, scl=Pin(x), sda=Pin(y))
    │     └── 遍历所有 I2C 驱动类实例
    │           → A1: I2C 传感器 (self_verify)
    │
    ├── 找到 SPI(1, sck=Pin(x), ...)
    │     └── 遍历所有 SPI 驱动类实例
    │           → A2: SPI 传感器 (self_verify)
    │
    ├── 找到 UART(1, baudrate=..., tx=Pin(x), rx=Pin(y))
    │     └── 遍历所有 UART 驱动类实例
    │           → A3: UART 外设 (self_verify 或 user_feedback)
    │
    ├── 找到 Pin(x, Pin.OUT) / PWM(Pin(x)) 且变量名含 "buzzer"/"relay"/"motor"
    │     → A4: GPIO 输出 (user_feedback)
    │
    ├── 找到 I2C/SPI 驱动 含 .fill() / .show() 方法
    │     → A5: 显示器 (user_feedback)
    │
    ├── 找到 I2C 驱动 含 .read() + channel/gain 参数
    │     → A6: ADC (self_verify)
    │
    ├── 找到 I2C 驱动 含 .write() + .read()
    │     → A7: DAC (self_verify)
    │
    └── 找到 Pin(x, Pin.IN) 含 callback/idle_state
          → A8: 输入器件 (semi_auto)
```

**测试顺序**：板载 LED → I2C 传感器 → SPI 传感器 → UART → ADC/DAC → 显示器 → GPIO 输出 → 输入器件。前一个 FAIL 且是基础级别的（LED / 供电相关），后面的不跑了。
