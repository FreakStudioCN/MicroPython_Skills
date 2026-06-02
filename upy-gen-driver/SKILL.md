---
name: upy-gen-driver
description: 从 PDF 数据手册或 Arduino/C++ 代码生成 MicroPython 驱动。当 upypi 和 GitHub 均无驱动时使用。流程：提取→生成调试版→硬件验证循环→脱调试→规范化。触发：upy-analyze 搜不到驱动时调用，或用户直接 /upy-gen-driver。
---

# MicroPython 驱动生成 Skill

## 角色定位

从非 MicroPython 来源（PDF 数据手册、Arduino/C++ 代码、芯片型号）生成规范化的 MicroPython 驱动。**独立 skill**，可被 `upy-analyze`、`upy-autofix` 或用户直接调用。

核心流程：**提取 → 生成调试版 → 硬件验证 → 脱调试 → 规范化**。

**执行顺序硬性约束：Step 3 完成前，禁止执行 Step 4；Step 3 完成前，禁止执行 Step 5。每一步进入前检查前置条件。**

---

## 前置条件

- 以下之一：PDF 数据手册 / Arduino/C++ 源码 / Arduino GitHub 仓库 URL / 芯片型号
- `mpremote` 可用（硬件验证阶段需要）
- Python 3 环境 + `pymupdf`（PDF 提取）

---

## 执行步骤

### Step 0: 确定输入类型

根据用户提供的材料判断走哪条路径：

```
├─ PDF 数据手册（.pdf）          → Step 1A
├─ Arduino/C++ 代码（.ino/.cpp） → Step 1B
├─ GitHub Arduino 仓库 URL       → git clone → Step 1B
└─ 仅芯片型号                    → WebSearch datasheet → 下载 PDF → Step 1A
```

---

### Step 1A: PDF 路径 — 提取文本

```bash
python G:/MicroPython_Skills/upy-gen-driver/scripts/extract_pdf.py \
  --input {datasheet.pdf} \
  --output {chip}_text.json
```

输出 JSON 结构：
```json
{
  "source": "datasheet.pdf",
  "pages": [
    {"num": 1, "text": "页面完整文本..."},
    {"num": 2, "text": "页面完整文本..."}
  ]
}
```

脚本只做纯文本提取（pymupdf），不做任何理解。保留页码便于引用。

**LLM 阅读提取的文本，理解并显式输出以下清单（写入 `{chip}_understanding.json`）：**
- 通信协议（I2C 地址 / SPI 模式 / UART 波特率）
- **芯片识别方式**：有无 ID/WHO_AM_I/CHIP_ID 寄存器？（有 → 地址+期望值；无 → 标注 N/A，自检用寄存器读写回代替）
- **数据就绪通知方式**：状态寄存器轮询 / 硬件引脚中断 / 固定延时 / 无（标注具体寄存器位或引脚）
- 寄存器映射表（地址 + 位定义 + 读写权限），**标注哪些是只写寄存器（read-back 会失败）**
- 初始化序列（步骤 + 时序 + 延时要求）
- 数据格式（大端/小端、无符号/二进制补码、转换公式）
- AT 指令格式（发送格式 + 响应格式 + 超时）
- **状态变量映射**：哪些硬件配置需要 shadow 追踪（如 `_gain` → GAIN bit, `_vref` → VREF bit, `_mode` → CM bit），每个 setter 的独立边界（谁管什么，互不越界）
- **等待策略**：芯片有就绪标志/状态位？→ 轮询该标志 + timeout；无就绪标志？→ 固定延时（datasheet 转换时间 + margin）
- **数据完整性**：芯片通信有 CRC/校验？→ 读数据时必须验证；无？→ 标注 N/A

---

### Step 1B: Arduino 路径 — API 映射 + 源码分析

```bash
python G:/MicroPython_Skills/upy-gen-driver/scripts/convert_arduino.py \
  --input {source.ino} \
  --output {chip}_mapping.json
```

输出 JSON 结构：
```json
{
  "source": "source.ino",
  "includes": ["Wire.h", "SPI.h"],
  "global_vars": [{"name": "sensor_addr", "value": "0x44"}],
  "functions": [
    {"name": "readSensor", "return_type": "float", "params": [], "line": 42}
  ],
  "api_mapping": [
    {"arduino": "Wire.beginTransmission(0x44)", "mpy": "i2c.writeto(0x44, buf)", "line": 45}
  ],
  "has_setup_loop": true,
  "logic_summary": "setup() 中初始化 Wire，loop() 中每 2 秒读取一次传感器数据并通过 Serial 打印"
}
```

脚本做 API 映射表查询 + 代码结构提取，**不翻译代码**。

**LLM 同时读取：**
1. Arduino 原始源码（理解逻辑意图、控制流、错误处理方式）
2. 映射 JSON（辅助定位 API 对应关系）

**翻译原则：**
- 不能机械逐行翻译 —— 理解原始代码逻辑后，用 MicroPython 惯用写法重写
- Arduino `loop()` 中的轮询 → MPY 中用 callback 或 timer 替代
- Arduino `delay()` → MPY 中用 `time.sleep_ms()` 或异步方式
- Arduino `Serial.print()` → MPY 中用 `print()` 或 logging

---

### Step 2: LLM 生成"调试版"单文件驱动

输出文件：`firmware/drivers/{chip}_driver/{chip}_debug.py`

**生成前，先根据 `{chip}_understanding.json` 确定以下分支，再套用对应模板：**

```
通信协议?
├─ I2C  → 自检含 i2c.scan() + 地址验证
├─ SPI  → 自检含 CS 引脚切换 + 回读测试
└─ UART → 自检含 AT 指令往返验证

芯片识别?
├─ 有 ID 寄存器 → 读取并比对期望值
└─ 无 ID 寄存器 → 用寄存器读写回验证替代（写入已知值→读回→断言）

数据就绪?
├─ 状态寄存器轮询 → while not (read_status() & MASK): sleep_ms(N), 加 timeout 上限
├─ 硬件引脚中断 → 等待 pin.value() == 0, 加 timeout 上限
└─ 固定延时     → time.sleep_ms(conversion_time + margin)

数据完整性?
├─ 有 CRC/校验 → 读数据后验证完整性，校验失败 raise RuntimeError
└─ 无 CRC/校验 → 跳过
```

**调试版必须包含以下自检步骤（按芯片实际情况取舍，不适用则跳过）：**

```python
# === 文件头：芯片信息 + 数据来源 ===
print("=" * 50)
print("Driver: {chip} ({protocol}: {detail})")
print("Source: {datasheet.pdf Page X / Arduino code}")
print("=" * 50)

# === [连接验证] 按协议选择 ===
# I2C: 扫描总线
print("[INIT] I2C scan...")
i2c_devices = i2c.scan()
print("  Found: %s" % [hex(a) for a in i2c_devices])
if 0xXX not in i2c_devices:
    print("  [FAIL] Device 0x%02X not found!" % 0xXX)
    print("  [HINT] Check wiring / power / pull-up resistors")

# SPI: 读已知寄存器（如 WHO_AM_I 或配置寄存器默认值）
# UART: 发送 AT 并检查响应

# === [初始化] 复位 + 默认值验证 ===
print("[INIT] Reset device...")
reset()  # 或发送 RESET 命令 / 拉低 RESET 引脚
time.sleep_ms(N)  # datasheet 规定的复位后等待时间
# 读取默认配置寄存器，验证与 datasheet 默认值一致

# === [身份识别] 有 ID 寄存器则验证，无则跳过 ===
# 有 ID 寄存器时：
print("[INIT] Read ID register (0x%02X)..." % ID_REG)
val = read_reg(ID_REG)
print("  Value: 0x%02X (expected: 0x%02X)" % (val, EXPECTED_ID))
if val != EXPECTED_ID:
    print("  [FAIL] ID mismatch! Got 0x%02X, expected 0x%02X" % (val, EXPECTED_ID))
    print("  [HINT] Check protocol config / wiring / datasheet Page X")

# 无 ID 寄存器时：用寄存器读写回替代
print("[INIT] Communication sanity check (write → read-back)...")
test_patterns = [0x00, 0x55, 0xAA]  # 选可安全写入的寄存器
for pat in test_patterns:
    write_reg(CONFIG_REG, pat)
    rb = read_reg(CONFIG_REG)
    if rb != pat:
        print("  [FAIL] Wrote 0x%02X, read-back 0x%02X" % (pat, rb))
    else:
        print("  [OK] Write 0x%02X → read-back 0x%02X" % (pat, rb))

# === [初始化序列] 逐步写入寄存器，逐项 read-back ===
print("[INIT] Configuration sequence...")
init_seq = [(REG_A, VAL_A, "说明A"), (REG_B, VAL_B, "说明B"), ...]
for reg, val, desc in init_seq:
    write_reg(reg, val)
    rb = read_reg(reg)
    if rb != val:
        print("  [FAIL] %s: reg 0x%02X wrote 0x%02X, read-back 0x%02X" % (desc, reg, val, rb))
        # 只写寄存器：标注 "write-only, skipping read-back"
    else:
        print("  [OK] %s (reg 0x%02X = 0x%02X)" % (desc, reg, val))

# === [功能验证] 读取一次数据 / 发送一次指令 ===
print("[TEST] Functional test...")
try:
    data = read_sensor()
    print("  Reading: %s" % str(data))
except Exception as e:
    print("  [FAIL] %s" % e)
    import sys
    sys.print_exception(e)

# === 最终判定 ===
print("=" * 50)
print("SELF_TEST_PASS")   # 或 print("SELF_TEST_FAIL: <原因>")
```

**关键要求：**
- 所有 print 字符串英文
- 失败时打印具体期望值 vs 实际值
- 失败时打印排查提示（查哪个寄存器/哪个页面/哪根线）
- 单文件，不拆包，方便反复修改
- **只写寄存器标注 "write-only"，不做 read-back 验证**
- **`__init__` 必须将芯片置于已知状态**（调用 reset 或读取当前配置确认）
- **`__init__` 顶部参数校验**：检查 bus 类型（I2C/SPI/UART）、address 范围（0x00-0x7F for I2C）、参数合法性，失败立即 `raise TypeError` / `ValueError`
- **如果类提供依赖配置的便捷方法（如电压转换依赖 gain/VREF），用 `_gain`/`_vref` 等实例变量追踪当前值，且每个 setter 只修改自己负责的状态，禁止跨 setter 污染**
- **所有轮询必须有 timeout**：禁止无限 `while True` 轮询。用 `ticks_ms()`/`ticks_diff()` 或 `for _ in range(max_iterations)` 限界。超时后 `raise RuntimeError` 并附排查提示
- **通信异常转义**：I2C/SPI/UART 操作包 `try`/`except OSError`，转为 `RuntimeError` 并附描述性消息（设备地址/寄存器/期望操作）
- **预分配 bytearray**：重复的 I2C/SPI 读写操作用预分配 `buf = bytearray(N)`，避免 MicroPython heap 碎片
- **优先轮询就绪位**：若芯片有状态寄存器/就绪标志，用 polling+timeout 等待；仅在芯片无任何就绪标志时使用固定延时

---

### Step 3: 硬件验证循环

**循环上限：10 轮。**

**此步骤不可跳过。若当前环境无 MicroPython 设备，必须暂停并询问用户，禁止直接进入 Step 4。**

#### 3.0 设备预检（每次进入 Step 3 必须首先执行）

```bash
mpremote devs
```

| 输出 | 行动 |
|------|------|
| 有 COM 口列表 | 记录 COM 口，进入 3A |
| 无输出（无设备） | **暂停**，输出 `[HALT] No MicroPython device detected. Please connect device and tell me the COM port, or type "skip" to skip hardware verification.` **禁止在用户确认前继续执行。** |

若用户明确输入 "skip" 跳过硬件验证，则直接跳到 Step 4，并在最终输出中标注"⚠️ 未经硬件验证"。

#### 3A. 烧录运行

```bash
mpremote connect {COM} resume run firmware/drivers/{chip}_driver/{chip}_debug.py
```

使用 `resume run` 而非 `fs cp` —— 通过 REPL 送入执行，不写 flash，秒级反馈。

#### 3B. LLM 分析输出

| 输出 | 判断 | 行动 |
|------|------|------|
| `SELF_TEST_PASS` | 全部自检通过 | 退出循环，进入 Step 4 |
| `ID/known-value mismatch` | 芯片识别失败或通信异常 | 查 datasheet 确认 ID 寄存器地址/期望值；若芯片无 ID 寄存器，检查寄存器读写回测试是否使用了只写寄存器 |
| `read-back mismatch` | 时序问题或寄存器为只写 | 加延时 / 查 datasheet 确认该寄存器读写权限 |
| AT 响应格式不符 | 指令/波特率/解析有误 | 调整指令格式 / 尝试不同波特率 |
| 初始化卡住 | 某步超时或就绪位未置位 | 加 timeout / 改用 polling 替代固定延时 / 检查数据就绪方式是否正确 |
| 设备崩溃无响应 | 代码导致 crash | `mpremote connect {COM} soft-reset` → 下一轮 |
| 总线扫描为空 / 设备无应答 | 硬件连接问题或协议配置错误 | 输出排查指引（接线/供电/上拉/CS 引脚/波特率），暂停循环 |

#### 3C. LLM 直接 Edit 文件 → 回到 3A

---

### Step 4: 脱调试 → 生产版驱动

**前置条件（必须全部满足，否则禁止执行 Step 4）：**

| # | 条件 | 验证方式 |
|---|------|----------|
| 1 | Step 3 硬件验证循环已执行 | 最近一次 `mpremote resume run` 有输出 |
| 2 | 最后一次运行输出 `SELF_TEST_PASS` | 输出中出现 `SELF_TEST_PASS` |
| 3 | 调试版文件存在 | `firmware/drivers/{chip}_driver/{chip}_debug.py` 存在 |

**若任一条件不满足 → 回到 Step 3 完成硬件验证，不得跳过。**

硬件验证通过后：

1. 去掉所有逐行调试打印（`[INIT] [1/5]...`、`[TX]/[RX]` 等）
2. 保留 SELF_TEST 逻辑但改为 `_self_test()` 私有方法（默认不调用）
3. 保留关键错误信息（异常消息、关键寄存器校验失败）
4. 按协议保留连接验证方法（I2C: `scan()` 公共方法；SPI: 读取已知寄存器；UART: AT 探测）
5. 按标准结构组织：类常量 → `__init__` → 公共方法 → 私有方法 → `deinit()`
6. 遵循依赖注入（I2C/SPI/UART 实例从外部传入）
7. **`__init__` 必须将芯片置于已知状态**（调用硬件复位 / 发送 RESET 命令 / 读取并确认默认寄存器值）
8. **内部状态一致性**：如果类提供依赖芯片配置的便捷方法（如电压转换依赖 gain/VREF），用 `_gain`、`_vref` 等实例变量追踪当前值。每个 setter 只修改自己负责的追踪变量，禁止跨 setter 污染。例如 `set_gain()` 不得修改 `_vref`；`set_vref(VREF_EXTERNAL)` 需提示用户自行设置 `_vref` 或提供参数传入外部参考电压值
9. **`deinit()` 方法**：若芯片 datasheet 支持低功耗/休眠/待机模式，实现 `deinit()` 发送 POWERDOWN/STANDBY 命令，释放资源
10. **可选 `__del__`**：可添加 `__del__` 在 GC 时自动调用 `deinit()`，用于低功耗场景

输出：`firmware/drivers/{chip}_driver/{chip}.py`

---

### Step 5: 规范化

```bash
Skill("upy-norm-driver")
```

传入 `{chip}.py`，执行全部 38 条 P0 规则检查与修复。

完成后输出规范化驱动。**驱动就绪。**

---

## 与其他 skill 的关系

```
upy-analyze (upypi + GitHub 无结果)
    ↓
upy-gen-driver (本 skill)
    ├── scripts/extract_pdf.py       ← PDF 文本提取
    ├── scripts/convert_arduino.py   ← Arduino API 映射
    ├── mpremote resume run          ← 硬件验证（mpremote-device-interaction）
    └── Skill("upy-norm-driver")     ← 规范化
    ↓
输出: firmware/drivers/{chip}_driver/{chip}.py
    ↓
可供 upy-generate (Phase 4) 使用
```

- ← `upy-analyze`：搜不到驱动时调用本 skill
- ← `upy-autofix`：诊断为缺驱动时调用本 skill
- → `upy-norm-driver`：规范化生成的驱动
- → `upy-generate`：使用生成好的驱动继续主流程

---

## 强约束

- **extract_pdf.py 只做文本提取**：不解析寄存器表、不判断协议类型，所有理解由 LLM 完成
- **convert_arduino.py 只做映射 + 结构提取**：不翻译代码，翻译由 LLM 在理解原逻辑后完成
- **调试版驱动必须全量自检**：每个寄存器/指令/读操作都有期望值比对，失败要打印期望 vs 实际
- **硬件验证必须先行（硬性约束，违反即流程错误）**：禁止在 Step 3 完成且输出 `SELF_TEST_PASS` 之前执行 Step 4/5。若当前环境无设备，必须暂停等待用户确认；不得以"当前无设备"为由跳过 Step 3。Step 4 有前置条件检查点，每次进入 Step 4 前必须自检。
- **验证用 `mpremote resume run`**：不改动 flash，快速迭代
- **Arduino 翻译不能机械**：必须理解原代码逻辑后用 MPY 惯用写法重写
- **依赖注入是硬要求**：I2C/SPI/UART 实例必须外部传入，不在类内创建
- **数据手册页码引用保留**：注释中标注数据来源 `(Datasheet Page X, Table Y)`
- **最多 10 轮验证**：超过则放弃，输出排查摘要
- **print/raise 字符串英文**
- **禁止无限轮询**：所有等待/轮询循环必须带 timeout（用 `ticks_diff()` 或 `for _ in range(N)`），超时后 `raise RuntimeError` 附排查提示
- **禁止跨 setter 污染 shadow state**：`set_gain()` 不得修改 `_vref`，`set_vref()` 不得修改 `_gain`。每个 setter 的边界在 `{chip}_understanding.json` 中显式定义
