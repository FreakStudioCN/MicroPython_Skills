---
name: upy-simulate
description: PC 端全流程业务模拟。读取 firmware/ 全部代码为上下文，LLM 自主设计调度/器件/可视化方案，生成 test/pc/ 下的模拟脚本，经 flake8 + pylint 校验后运行。触发：upy-generate 完成后手动触发，或 upy-autofix 修复后调用。
---

# PC 端全流程模拟 Skill

## 角色定位

读取 `firmware/` 下全部代码作为上下文，**由 LLM 自主设计**调度方案、Mock 器件组装、可视化形式、数据场景，生成 `test/pc/sim_main.py`（及需要的辅助文件），在不依赖硬件的情况下模拟完整业务流程。

**这是代码生成 skill，不是运行框架 skill。** 不预先写死调度器、不硬编码 CLI 格式——LLM 读完全量代码后，针对当前项目生成专属模拟脚本。

---

## 核心约束

- **不修改 firmware/ 下任何文件**（除非发现确定的语法错误或逻辑 bug）
- **所有模拟代码写入 `test/pc/`**，通过 `sys.path.insert(0, ...)` 导入 firmware/ 模块
- **可以继承、包装 firmware/ 的类和函数**，但不能修改原文件
- **flake8 + pylint 校验必须通过**，有错误则修复后重新校验，循环直到无错误
- **运行前必须用 AskUserQuestion 询问用户**

---

## 执行步骤

### Step 1: 全量读取上下文

LLM 必须读完以下所有文件，不遗漏：

```
firmware/
├── main.py              → 硬件 init 层 + 回调包装 + 任务注册 + 数据流（_data dict 的 key）
├── conf.py              → 采样率、刷新间隔、告警阈值、常量
├── project-manifest.json → mode (timer|async|thread), devices[], mcu{}
├── tasks/
│   ├── *.py             → 每个 task 的函数签名、参数、返回值
├── drivers/
│   └── */mock.py        → 每个 Mock 类的 __init__ 参数、方法、_raise_on 异常注入点
├── lib/
│   ├── scheduler/*.py   → Scheduler API（add_task, start, etc.）
│   ├── logger/*.py      → 日志系统（模拟时可能不需要设备端日志轮转）
│   └── time_helper.py   → 装饰器（CPython 兼容分支已存在）
├── board.py             → 引脚映射（仅参考，模拟不需要）
├── boot.py              → 启动引导（模拟跳过）
└── assets/              → 设备端资源文件（音频、图片等），模拟可能需要引用
```

### Step 1B: 项目类型分类 + 可模拟接口提取

读完所有文件后，LLM 必须执行以下两项分析：

#### 1. 项目类型自动分类

扫描 firmware/ 所有代码，检测以下信号，输出分类结果到 `sim_main.py` 头部注释：

| 信号 | 判定为 |
|------|--------|
| `import network` / `WLAN` / `socket` / `umqtt` / `urequests` / `bluetooth` / `NFC` | **物联网 / 网络** |
| `PWM` / `Servo` / `Stepper` / `encoder` / `H-bridge` / 电机驱动芯片型号 | **电机控制** |
| display 器件 + `Pin.IRQ` / button / touch / rotary encoder / keypad 驱动 | **GUI 交互** |
| `conf.py` 含 `*_THRESHOLD` / `*_ALARM` 常量 | **告警监控** |
| `_thread` / `uasyncio` 且 ≥ 3 个并发任务 | **多任务并发** |
| `uart` / `CAN` / `RS485` / `Modbus` / 外部通信协议 | **工业通信** |

一个项目可属于多个类型。格式：
```python
# @ProjectTypes: sensor_monitoring, alarm_monitoring, gui_display
```

#### 2. 可模拟接口清单

不能只读 `drivers/*/mock.py`，还要从 firmware 全部代码中提取所有**可模拟的外部边界**：

- **网络**：`wlan.isconnected()`, `wlan.ifconfig()`, `socket.send()/recv()`, `umqtt.publish()/subscribe()/check_msg()`, `urequests.get()/post()`
- **电机**：`pwm.duty()`, `servo.angle()`, `stepper.step()`, 编码器读数，限位开关状态
- **输入**：`pin.value()`, `pin.irq()` 触发时机，去抖时间段
- **协议**：MQTT CONNECT/SUBACK/PUBACK 状态，HTTP response status code

对每个可模拟接口，记录：**调用它的 task 名称、正常行为、可能的故障模式**。

---

### Step 2: LLM 自主设计

LLM 基于 Step 1 的全量上下文，自主决定以下 5 件事。**不预置框架，不硬编码方案。**

#### 2A. 调度方案

| manifest mode | CPython 替代方案 | 说明 |
|--------------|-----------------|------|
| timer | `while` + `time.sleep(tick_ms/1000)` + 手动计数器 | LLM 需生成 `SimScheduler` 类，与 `firmware/lib/scheduler/timer_sched.py` 的 `Scheduler` 同 API（`add_task`, `start`），去 `machine.Timer` ISR |
| async | `asyncio.run()` | CPython 3.7+ 原生 asyncio，与 MicroPython `uasyncio` API 高度兼容，LLM 可直接用 |
| thread | `threading.Thread(target=loop, daemon=True)` | CPython 原生 threading，主线程 `time.sleep` 保持存活 |

**timer 模式特别注意**：LLM 生成的 `SimScheduler` 必须与原始 `Scheduler` 接口一致。CPython 用 `time.sleep` 循环替代 ISR，在每个 tick 递增所有 task 的计数器，执行到期的 callback。

#### 2B. Mock 器件组装 + 数据发生器（核心）

**这是 upy-simulate 最关键的设计决策。** 不能把 Mock 设为静态值——`MockSHT30(measure=(25.0, 60.0))` 每次都返回相同数据，tick 之间无变化，业务逻辑分支永远测不到。

**正确做法：数据发生器 = 以 tick 为自变量的函数。**

LLM 读取每个 `drivers/*/mock.py`，从中确定：
- `__init__` 接受哪些参数（如 `measure=(25.0, 60.0)`, `temp=25.5`）
- 支持哪些 `_raise_on` 值（如 `'measure'`, `'read_compensated_data'`）
- 提供了哪些方法

**数据注入机制**（不改 firmware/ 代码）：

```python
# sim_main.py 中定义数据发生器（tick → 返回值）
def gen_sht30(tick):
    """温度 22-28°C 正弦波动，周期 60s"""
    import math
    temp = 25.0 + 3.0 * math.sin(2 * math.pi * tick / 600)
    hum = 60.0 + 10.0 * math.cos(2 * math.pi * tick / 600)
    return (temp, hum)

def gen_bmp280(tick):
    """气压 1000-1020 hPa，带随机噪声"""
    import random
    press = 101000 + 1000 * math.sin(2 * math.pi * tick / 300) + random.uniform(-200, 200)
    return (25.0, press, 55.0)  # temp, pressure, humidity

# 在每个 sensor callback 执行前，更新 mock 内部状态
def _sensor_cb():
    sht30._measure = gen_sht30(tick_count)   # ← 动态注入
    bmp280._read_data = gen_bmp280(tick_count)
    sensor_read(sht30, bmp280, _data)
```

**Mock 状态更新必须在 callback 之前**，确保 task 函数调用 `mock.measure()` 时拿到的是当前 tick 的数据。

#### 2B+. Mock 设计模式（按项目类型）

以下为**非传感器项目**的 Mock 设计参考。LLM 必须根据 Step 1B 的分类结果选择对应的模式。

**网络 Mock（状态机驱动的跨 tick 行为）：**

```python
class MockWLAN:
    """关键：状态机 —— 连接中→已连接→断开→重连中"""
    def __init__(self, **kwargs):
        self._connected = kwargs.get('connected', True)
        self._rssi = kwargs.get('rssi', -40)
        self._raise_on = kwargs.get('_raise_on', None)  # 'connect', 'disconnect'
        self._connect_delay_ticks = kwargs.get('connect_delay', 0)

    def isconnected(self):
        if self._raise_on == 'isconnected':
            raise OSError('WLAN error')
        return self._connected

    def ifconfig(self):
        return ('192.168.1.100', '255.255.255.0', '192.168.1.1', '8.8.8.8')

# 数据发生器：network_state(tick) → (connected, rssi, raise_on)
def gen_network_disconnect(tick):
    if 10 <= tick <= 14:
        return (False, -80, None)     # 断连 5 ticks
    elif tick == 15:
        return (True, -40, None)      # 重连
    return (True, -40, None)
```

**协议 Mock（高于 socket 层，模拟应用协议行为）：**

```python
class MockMQTT:
    """模拟 MQTT 协议行为，不模拟 TCP socket"""
    def __init__(self, **kwargs):
        self._connected = False
        self._subscriptions = {}
        self._pending_messages = []      # broker → device 的消息队列
        self._connect_fail_until = kwargs.get('_connect_fail_until', -1)
        self._raise_on = kwargs.get('_raise_on', None)

    def connect(self):
        if self._raise_on == 'connect':
            raise OSError('Connection refused')
        self._connected = True

    def check_msg(self):
        if self._raise_on == 'check_msg':
            raise OSError('Socket error')
        return self._pending_messages.pop(0) if self._pending_messages else None

# 场景数据：向 _pending_messages 注入特定的 MQTT 消息序列
# 场景：服务器下发错误指令 → 验证解析拒止
```

**电机 Mock（跨 tick 累积物理状态）：**

```python
class MockStepper:
    """关键：跨 tick 累积物理状态，不是每 tick 重新赋值"""
    def __init__(self, **kwargs):
        self._position = kwargs.get('position', 0)
        self._target = kwargs.get('target', 0)
        self._speed = kwargs.get('speed', 100)         # steps/s
        self._stall_at = kwargs.get('_stall_at', None)  # 在某个位置卡住
        self._limit_switch = kwargs.get('_limit_switch', None)
        self._raise_on = kwargs.get('_raise_on', None)

    def step(self, direction, steps=1):
        if self._raise_on == 'step':
            raise RuntimeError('Motor driver error')
        if self._stall_at is not None and self._position >= self._stall_at:
            raise RuntimeError('Motor stalled at position {}'.format(self._position))
        self._position += steps * direction

    def position(self):
        return self._position

# 电机场景不用"数据发生器"，用"事件注入"：
# def _scenario_motor_stall(sht30, bmp280, tick):
#     if tick == 10:
#         stepper._stall_at = 300  # ← 注入堵转事件
```

**输入设备 Mock（事件队列 + 时间序列回放）：**

```python
class MockButton:
    """关键：预加载事件队列，按 tick 回放，模拟真实物理时序"""
    def __init__(self, **kwargs):
        self._event_queue = kwargs.get('events', [])  # [(tick, value), ...]
        self._current_tick = 0

    def set_tick(self, tick):
        self._current_tick = tick

    def value(self):
        for tick, val in reversed(self._event_queue):
            if self._current_tick >= tick:
                return val
        return 0

# 场景：10 次快速连按（100ms 间隔）验证去抖：
# events = [(1,1), (2,0), (3,1), (4,0), (5,1), (6,0), ...]
```

**执行器 Mock（记录状态翻转历史而非仅仅当前值）：**

```python
# 标准 MockBuzzer/MockLED 已经足够（_state + on/off + value）
# 但 LLM 应在 scenario 中验证：on() 被调用后 value() 为 True 的时间点
```

**工业通信 Mock（Modbus / RS485 / CAN）：**

```python
class MockModbus:
    """模拟 Modbus RTU 从设备"""
    def __init__(self, **kwargs):
        self._registers = kwargs.get('registers', {})  # {addr: value}
        self._raise_on = kwargs.get('_raise_on', None)  # 'read', 'write', 'timeout'
        self._response_delay = kwargs.get('response_delay', 0)

    def read_holding_registers(self, addr, count):
        if self._raise_on == 'read':
            raise OSError('Modbus timeout')
        return [self._registers.get(addr + i, 0) for i in range(count)]

# 场景：从设备离线 → read_holding_registers 持续超时 → 主设备进入 safe mode
```

#### 2C. 可视化形式

**CLI + rich 优先。tkinter GUI 为可选降级方案。**

tkinter 在 Windows 上存在已知问题：`root.after()` 回调链中 `StringVar.set()` / Canvas 操作可能不刷新，`sys.stdout` 重定向会干扰事件循环。CLI + rich 无此问题，且开发迭代更快。

| 项目特征 | 首选方案 | 说明 |
|---------|---------|------|
| 所有项目 | **`rich` 库 (Live/Table/Panel/Layout)** | 终端动态仪表盘，跨平台无渲染问题 |
| 有 display 器件（OLED/LCD/TFT） | rich `Panel` + `Text` 模拟屏幕内容 | Panel 标题标注器件型号，内容区实时更新虚拟屏幕文本 |
| 有执行器（Buzzer/LED/Relay） | rich `Table` 行内状态标记 | `ON`/`OFF` 带颜色高亮（绿色=激活，灰色=待机） |
| 日志输出 | rich `Live` 底部固定区域滚动 | 不劫持 `sys.stdout`，直接写入 Panel |

**LLM 默认只生成 CLI 模式（rich）**。`--mode gui`（tkinter）仅在用户明确要求时生成，且生成时遵循以下注意事项：
- 不使用 `sys.stdout` 重定向，改为直接调用 `log_widget.insert()` 
- `root.after()` 回调末尾调用 `root.update_idletasks()` 强制刷新
- 每个 `scheduler_tick()` 包裹 `try/except` 防止静默失败

GUI 模式在 sim_main.py 头部标注：`# @GUI: experimental — prefer --mode cli for reliable output`

#### 2D. 数据场景（时序演化 + 覆盖框架）

LLM 必须根据 Step 1B 的项目分类结果 + `conf.py` 的常量 + `tasks/*.py` 的逻辑分支，**为每个覆盖维度设计至少一个 scenario**。

##### 2D-1. 覆盖维度表（按项目类型）

LLM 必须针对项目的每个分类，在以下维度中设计对应的 scenario：

| 项目类型 | 覆盖维度 | scenario 设计要点 |
|----------|---------|------------------|
| **传感器监控** | 正常数据流 | 数据在阈值内波动，验证调度 + 数据流完整性 |
| | 阈值跨越（高） | 数据从阈值之下跨到之上，验证条件触发 |
| | 阈值跨越（低） | 同上，方向相反 |
| | 传感器故障 | `_raise_on` 注入异常，验证独立容错 |
| | 传感器恢复 | 异常后恢复，验证自动恢复 |
| | 多传感器部分故障 | A 故障 B 正常，验证互不干扰 |
| **告警/执行器** | 告警触发 → 执行器 ON | 验证 buzzer/LED/relay 激活时序 |
| | 告警冷却 | 验证冷却期内不重复触发 |
| | 告警恢复 → 执行器 OFF | 条件清除后执行器关闭 |
| | 告警重复触发 | 冷却期过后再次触发（需 ticks > cooldown_ticks × 2） |
| **物联网/网络** | 连接丢失 | `isconnected() → False`，验证离线缓存/队列 |
| | 连接恢复 | 重连 + 队列重发 |
| | 发送超时 | `send() → timeout`，验证重试逻辑 |
| | 收到异常数据 | 格式错误 / 校验失败 → 验证拒止 |
| | 服务器断开 | broker 主动断开，验证重连 |
| | 弱信号 | RSSI 持续下降，验证降级策略 |
| **电机控制** | 正常运动 | 目标位置到达，验证运动完成 |
| | 堵转/失速 | 位置不再变化，验证堵转检测 |
| | 限位触发 | 到达限位开关，验证停止逻辑 |
| | 紧急停止 | 中途停止指令，验证中断 |
| **GUI/人机交互** | 正常操作路径 | 完整菜单浏览 / 流程 |
| | 快速连续输入 | N ms 内多次事件，验证去抖 |
| | 长按 vs 短按 | 不同时长区分，验证按键时长解析 |
| | 无效输入 | 越界数据，验证拒绝 |
| **工业通信** | 从设备超时 | Modbus/CAN 超时 → safe mode |
| | 从设备返回错误 | 异常码 → 错误处理 |
| | 总线断开 | 物理层断开 → 报警 |
| **多任务并发** | 所有任务同时到期 | 验证无饿死 |
| | 一个任务耗时过长 | 验证对其他任务的影响 |

##### 2D-2. 场景数量下限

每个项目至少生成 **N 个 scenario**，其中 `N = 项目分类数 × 2 + 1`。对应关系：

| 项目分类型 | 最少 scenario 数 |
|-----------|-----------------|
| 仅传感器 | 3（正常 + 故障 + 阈值触发） |
| 传感器 + 告警 | 5 |
| 传感器 + 告警 + 网络 | 7 |
| 传感器 + 电机 + 告警 | 8 |

##### 2D-3. 场景自检 + @Coverage 注释（强制）

LLM 生成每个 scenario 后，**必须**在代码中以 `@Coverage` 注释声明它覆盖了哪个分类下的哪个维度、预期在哪个 tick 触发什么事件。注释写入 scenario 函数文档字符串或文件头：

```python
def _scenario_temp_rising(sht30, bmp280, tick):
    """@Coverage: [alarm] TEMP_HIGH_THRESHOLD(35.0) crossed at tick ~21
       @Coverage: [alarm] buzzer.on() + led.on() called at tick ~21
       @Coverage: [alarm] cooldown active ticks 21-50 — no repeat trigger within 30 ticks
    """
```

LLM **必须逐条核对**：每个 scenario 在其声明的 `--ticks` 默认值内是否真的能触发声明的事件。核对结论写入 sim_main.py 头部：

```python
# @CoverageReport:
#   normal:              [sensor] data flow only — no threshold crossed
#   temp_rising:         [alarm] temp high at tick 21, buzzer+LED ON
#   temp_dropping:       [alarm] temp low at tick 23
#   intermittent:        [sensor] OSError at ticks 3,6,9,...
#   sensor_death:        [sensor] permanent failure from tick 5
#   ⚠ GAP: humidity threshold (80% HIGH / 20% LOW) not covered by any scenario
#   ⚠ GAP: alarm recovery (all clear) needs ticks > 51 with temp_rising
```

**如果 LLM 发现某个覆盖维度在当前 5 个 scenario 模板中无对应，必须新增 scenario。** 如果项目本身不涉及某维度（如无网络模块），在报告中标注 "N/A"。

##### 2D-4. 场景数据设计参考

每个场景是一个 **Python 函数 `(tick: int) → 副作用`**（更新 mock 内部状态）。LLM 自主选择以下设计手段：

- **数学表达式**：正弦波、线性上升/下降、指数衰减
- **事件注入**：在特定 tick 修改 `mock._stall_at`、`mock._connected`、`mock._event_queue` 等
- **异常注入**：在特定 tick 设置 `mock._raise_on = 'xxx'`
- **查表序列**：预定义 `[(tick1, val1), (tick2, val2), ...]` 的时间序列

#### 2E. 用户自定义场景（自然语言 → Mock API）

**触发条件**：用户调用 skill 时携带了自然语言描述，或 Step 5 的 AskUserQuestion 中用户选择了自定义场景。

##### 2E-1. 用户输入示例

- "我想测 WiFi 断连 5 秒后自动重连的场景"
- "如果电机在 position=300 卡住，系统会不会停？"
- "用户狂点按钮 10 次，菜单会不会乱跳？"
- "BMP280 和 SHT30 同时故障会怎样？"
- "MQTT broker 突然断开然后 3 秒后恢复"

##### 2E-2. LLM 映射规则

LLM 必须把用户自然语言映射到对应 mock 的 API：

```
用户描述                      →  LLM 解析                   →  Mock API 映射
──────────────────────────────────────────────────────────────────────────
"WiFi 断连 5 秒"              →  网络连接丢失，持续 5000ms    →  wlan._connected = False
                                                                 for tick in range(t, t+5)

"自动重连"                    →  恢复连接                     →  wlan._connected = True
                                                                 wlan._raise_on = None

"电机卡在 position=300"       →  堵转事件                     →  stepper._stall_at = 300

"狂点按钮 10 次"              →  100ms 间隔脉冲序列            →  button._event_queue =
                                                                  [(t,1), (t+1,0), (t+2,1), ...]

"两个传感器同时故障"          →  双 raise_on 注入              →  sht30._raise_on = 'measure'
                                                                 bmp280._raise_on = 'read_compensated_data'

"MQTT broker 断开然后恢复"    →  断连 + 延迟 + 重连            →  mqtt._raise_on = 'connect' ticks 5-7
                                                                 mqtt._raise_on = None from tick 8

"Modbus 从设备超时 3 次"      →  read 连续 fail                →  modbus_reg._raise_on = 'read' for ticks 1-3
```

##### 2E-3. 映射失败处理

如果 LLM 无法将用户描述映射到现有 mock 的可用 API，**必须输出反馈而非静默跳过**：

```
⚠ 无法映射："电机扭矩超限" —— MockStepper 不提供扭矩模拟。
   可用注入点：_stall_at（位置堵转），step() 抛 RuntimeError
   建议：改为 "电机在 position=200 处堵转"，或为 MockStepper 增加 _torque_limit 属性。

⚠ 无法映射："WPA3 握手失败" —— MockWLAN 不模拟认证层。
   可用注入点：_raise_on='connect'（连接被拒），_connect_delay_ticks（连接耗时）
   建议：改为 "WiFi connect 失败 3 次后放弃"
```

##### 2E-4. 生成规则

- 映射成功后的 scenario 函数命名为 `_scenario_custom_N`，键名 `custom_N`
- 自动加入 `SCENARIOS` dict
- `sim_main.py` 头部注释增加：
  ```python
  # @CustomScenario: custom_1 = "WiFi 断连 5 秒后重连" → wlan disconnect ticks 10-14, reconnect tick 15
  # @CustomScenario: custom_2 = "双击按钮" → button events at ticks 3,4,8,9
  ```

##### 2E-5. 前置询问（可选）

如果用户调用 skill 时未提供自定义描述，LLM 可以在 Step 5 之前插入一个问题：
```
header: "自定义场景"
question: "是否需要自定义测试场景？如有，请描述（如：WiFi 断连、电机堵转、按钮连按等）"
options:
  - 使用预设场景 — 根据项目类型自动生成覆盖清单
  - 自定义场景 — 在 Other 中输入自然语言描述
```

---

### Step 3: 生成模拟代码

生成一个或多个 `.py` 文件到 `test/pc/`：

```
test/pc/
├── sim_main.py          # 主入口（Mock 组装 + 调度 + 可视化 + 场景控制）
└── sim_scheduler.py     # timer 模式需要（SimScheduler 类）
```

**`sim_main.py` 必须在文件头注释中说明：**
```python
# @Generated by upy-simulate
# @Date: <生成时间>
# @ProjectTypes: sensor_monitoring, alarm_monitoring, gui_display
# @Description: PC 端全流程模拟入口
#   不依赖 MicroPython 运行时，不依赖硬件设备
#   通过 sys.path 导入 firmware/ 的 task 函数和 mock 驱动
# @CoverageReport:
#   normal:              [sensor] data flow only — no threshold crossed
#   temp_rising:         [alarm] temp high at tick ~21, buzzer+LED ON
#   temp_dropping:       [alarm] temp low at tick ~23
#   intermittent:        [sensor] OSError at ticks 3,6,9,...
#   sensor_death:        [sensor] permanent failure from tick 5
```

**代码约束：**
- 通过 `sys.path.insert(0, os.path.join(...))` 导入 firmware/
- 回调包装方式与 `firmware/main.py` 保持一致
- 任务注册方式与 `firmware/main.py` 保持一致
- `_data` dict 的 key 与 `firmware/main.py` 保持一致
- 接受 `--ticks`（运行轮数）、`--scenario`（场景）、`--mode`（CLI/GUI，默认 CLI）命令行参数
- **每个场景必须定义数据发生器函数** `gen_xxx(tick) → value`，tick 变化则返回值变化
- **在 sensor callback 执行前，必须更新 mock 内部状态**：`mock._measure = gen_sht30(tick_count)`，确保 task 函数拿到当前 tick 的数据
- **禁止一次创建 Mock 后不再更新其内部状态**

---

### Step 4: flake8 + pylint 校验

```bash
# flake8
python -m flake8 test/pc/sim_main.py --max-line-length=120

# pylint（嵌入式项目适当放宽）
python -m pylint test/pc/sim_main.py --max-line-length=120 --disable=missing-docstring,too-few-public-methods
```

**校验循环：**
```
生成代码 → flake8 → 有错误 → 修复 → 重新校验
       → 无错误 → pylint → 有警告/错误 → 修复 → 重新校验
                        → 无错误 → Step 5
```

每次修复后必须重新运行两个工具确认。最多 5 轮修复，超过则报告用户。

---

### Step 5: 询问用户

flask8 + pylint 均通过后，用 **AskUserQuestion** 询问。

#### 5a. 运行前分析（LLM 必须在询问前完成）

1. 检测项目类型（复用 Step 1B 的分类结果）
2. 如存在告警/阈值逻辑，计算**最小推荐 ticks**：
   - `min_recommended_ticks = max(各阈值跨越所需 tick 数) + ALARM_COOLDOWN_MS / SAMPLE_INTERVAL_MS × 2`
   - 确保至少覆盖：触发 → 冷却 → 第二次触发（完整循环）
3. 从生成的 scenario 列表中，区分**"仅验证数据流"**和**"覆盖业务分支"**两类

#### 5b. AskUserQuestion 内容

**默认模式始终为 CLI（rich）。**

```
header: "模拟运行"
question: "PC 模拟脚本已通过语法校验，是否开始运行？

  项目类型: [sensor ×2, alarm, OLED display, 无网络]
  已生成 scenario: normal, temp_rising, temp_dropping, intermittent_failure, sensor_death
  推荐: temp_rising --ticks 60（覆盖完整告警循环：触发→冷却→恢复）
  normal 场景仅验证数据流通，不触发任何业务分支。
"
options:
  - 运行推荐场景 (Recommended) — temp_rising --mode cli --ticks 60
  - 运行 normal 场景 — 仅验证数据流通 + 调度
  - 切换场景运行 — 在 Other 中输入（如 --mode cli --scenario intermittent_failure）
  - 运行 GUI 模式（实验性） — 在 Other 中输入（如 --mode gui --scenario temp_rising）
  - 自定义场景 — 在 Other 中输入自然语言描述（如 "WiFi 断连 5 秒"）
  - 暂不运行 — 保留 test/pc/sim_main.py，稍后手动运行
```

---

### Step 6: 运行 + 判定

```bash
python test/pc/sim_main.py --ticks {N} --mode {mode} --scenario {scenario}
```

**运行中观察：**
- 有无 Python Traceback → FAIL（LLM 修复 sim_main.py，回到 Step 3）
- 输出中 task 函数是否正常执行 → 查看每 tick 的日志
- 业务逻辑是否触发 → 对照该 scenario 的 `@Coverage` 注释检查
- 数据流是否完整 → `_data` dict 的 key 应被各 task 正确读写

**判定规则（三级）：**
```
有 Traceback                              → FAIL  → 修复 sim_main.py，回到 Step 3
无 Traceback，所有 @Coverage 声明的事件
  在预期 tick 范围内发生                   → PASS  → 流程结束
无 Traceback，部分 @Coverage 声明的事件
  未发生（场景保守 or ticks 不够）          → WEAK_PASS → 提示用户换场景
```

**运行完成后，LLM 必须输出按项目类型的覆盖摘要报告：**
```
=== Simulation Coverage Report ===
☑ [sensor] 传感器读取:             30/30 ticks 正常
☑ [sensor] 传感器故障容错:          触发 → SHT30 read failed at ticks 3,6,9,12,...
☑ [alarm]  告警检查:                30/30 ticks 正常
☑ [alarm]  高温告警触发:            触发 → [alarm] temp high at tick 21
☑ [alarm]  执行器激活:              触发 → Buzzer ON, LED ON at tick 21
☐ [alarm]  告警恢复 (all clear):   未触发 → ticks 不够，需 > 51
☐ [alarm]  低温告警触发:            未触发 → current scenario 不覆盖
☐ [alarm]  湿度告警触发:            未触发 → 无 scenario 覆盖 80%/20% 湿度阈值
☐ [network] 网络容错:               N/A → 项目无网络模块
☐ [motor]  电机控制:               N/A → 项目无电机模块
==================================
Result: WEAK_PASS — 3/5 覆盖维度已测，2 个维度未覆盖。
  建议: python test/pc/sim_main.py --scenario temp_dropping --ticks 30
  建议: 新增 humidity_high scenario 覆盖 80% 湿度阈值
```

WEAK_PASS 时，LLM 必须**主动提出具体的重跑建议**（具体到命令行参数或新增 scenario 名称）。

---

## 调度模式详细参考

### Timer 模式：SimScheduler 设计

LLM 读取 `firmware/lib/scheduler/timer_sched.py` 的 `Scheduler` 类后，生成 `SimScheduler`：

```
原 Scheduler                      SimScheduler
───────────                       ─────────────
machine.Timer ISR 驱动              time.sleep 循环驱动
ISR 只递增 tick_cnt                 循环体手动递增 tick_cnt
主循环检查 tick_cnt → 执行 cb       主循环检查 tick_cnt → 执行 cb
start() 永不返回                    start() 支持 max_ticks 限制
无可视化钩子                         on_tick 回调推送状态
```

关键接口必须一致：`add_task(callback, interval_ms, name=None) → tid`, `start()`

### Async 模式：直接使用 CPython asyncio

```python
import asyncio
# task 函数签名是 async def xxx_coro():
# 直接 asyncio.create_task() 注册
# asyncio.run(main_coro()) 启动
```

MicroPython `uasyncio` 与 CPython `asyncio` API 高度兼容，通常无需适配。

### Thread 模式：直接使用 CPython threading

```python
import threading
# task 函数是 while True 循环
# threading.Thread(target=sensor_loop, daemon=True).start()
# 主线程 time.sleep 保持存活
```

---

## 可视化示例（供 LLM 参考，非强制）

### 首选：rich CLI 终端仪表盘

```python
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

# 主布局：传感器数据表 + 虚拟屏幕 + 状态面板
layout = Layout()
layout.split_column(
    Layout(Table(...), name="data"),
    Layout(Panel("", title="SSD1306 OLED 128x64"), name="display"),
)

# 每 tick 更新
with Live(layout, refresh_per_second=10, transient=False) as live:
    while running:
        # 更新传感器 Table
        table.add_row(str(tick), f"{temp:.1f}°C", f"{hum:.1f}%", ...)

        # 更新虚拟 OLED Panel（模拟 display 器件）
        oled_content = f"T: {temp:.1f}°C\nH: {hum:.1f}%\n{'ALARM!' if alarm else 'OK'}"
        layout["display"].renderable = Panel(oled_content, title="SSD1306")

        # 执行器状态：用 rich Text 带颜色标记
        buzzer_text = Text("Buzzer: ", style="bold")
        buzzer_text.append("ON", style="bold red") if buzzer_on else buzzer_text.append("OFF", style="dim")
```

display 器件用 `rich.Panel` 模拟虚拟屏幕内容，执行器状态用 `rich.Text` 颜色标记（绿色=正常，红色=激活，灰色=待机）。不劫持 `sys.stdout`，日志直接追加到独立的 `log_lines` 列表并在 `Live` 刷新时写入底部 Panel。

### 可选：tkinter GUI（实验性）

仅用户明确要求时生成。生成时必须在代码头部标注 `# @GUI: experimental — prefer --mode cli for reliable output`。

```python
import tkinter as tk
root = tk.Tk()
root.title("PC 模拟 [EXPERIMENTAL GUI]")

# 关键规则：
# 1. 不重定向 sys.stdout → 直接调用 log_widget.insert()
# 2. 每次更新后调用 root.update_idletasks()
# 3. scheduler_tick() 包裹 try/except 防止静默失败

def scheduler_tick():
    try:
        sc.execute_one_tick()
        render_oled()
        update_status()
        root.update_idletasks()  # ← 强制刷新
    except Exception as e:
        print(f"[GUI ERROR] {e}", file=sys.stderr)
    if sc._running:
        root.after(sc._tick_ms, scheduler_tick)

root.after(100, scheduler_tick)
root.mainloop()
```

---

## 与其他 skill 的关系

```
upy-generate
    │
    ├─→ upy-simulate（手动触发）
    │       test/pc/sim_main.py → PASS → 流程结束 / 进入 deploy
    │
    └─→ upy-deploy
            │
            └─→ FAIL → upy-autofix
                          │
                          └─→ 修复后可选调用: python test/pc/sim_main.py --ticks 30
                                 快速验证修复效果 → 再 deploy
```

- ← `upy-generate`：提供完整的 firmware/ + manifest
- → 可被 `upy-autofix` 调用：修复后先在 PC 验证，再烧录
- 与 `upy-deploy` 并行可选：用户可先 simulate 再 deploy

---

## 强约束

- **不修改 firmware/ 下任何文件**（除非发现确定的 bug）
- **所有新代码写入 `test/pc/`**
- **flake8 + pylint 校验必须通过**，否则循环修复
- **运行前必须 AskUserQuestion 询问用户**
- **调度方案由 LLM 根据 manifest.mode 自主决定**，不预置框架
- **可视化形式由 LLM 根据项目器件组合自主决定**，不硬编码
- **CLI + rich 为首选模式**：所有项目默认生成 CLI 模式（rich Live/Table/Panel），数据随时间变化在终端动态刷新
- **有 display 器件的项目，用 rich Panel 模拟虚拟屏幕**：Panel 标题标注器件型号，内容区每 tick 更新当前显示文本
- **不劫持 sys.stdout**：日志直接写入 rich Panel 或独立的 `loguru`/`print`，避免重定向干扰输出时序
- **tkinter GUI 为可选实验模式**：仅用户明确要求时生成，生成时须在代码头部标注 `# @GUI: experimental`，且遵循 GUI 安全规则（无 stdout 重定向、update_idletasks、try/except 包裹）
- **在 sensor callback 执行前，必须更新 mock 内部状态**（如 `mock._measure = gen_sht30(tick_count)`），不改 firmware/ 代码的前提下让 task 函数拿到动态数据
- **模拟入口 `sim_main.py` 必须支持 `--ticks`, `--scenario`, `--mode` 三个命令行参数**，`--mode` 可选 `cli|gui`
- **不模拟驱动内部细节**（传感器协议、I2C 时序等），仅通过 Mock 对象的返回值和异常注入验证业务逻辑
- **Step 1B 强制**：LLM 必须进行项目类型分类，输出 `@ProjectTypes` 到 sim_main.py 头部
- **Step 2D 强制**：每个 scenario 必须包含 `@Coverage` 注释声明覆盖维度；LLM 必须逐条核对每个 scenario 是否真的能在默认 ticks 内触发声明的事件，结论写入 `@CoverageReport`
- **Step 2D 强制**：场景数量 ≥ 项目分类数 × 2 + 1；必须覆盖每个项目分类的每个覆盖维度（见覆盖维度表）；现有模板不足时必须新增 scenario
- **Step 2E 强制**：用户提供自然语言描述时，LLM 必须映射到 mock API；映射失败必须输出反馈告知原因和替代建议
- **Step 5 强制**：AskUserQuestion 必须注明项目类型 + 推荐能覆盖业务逻辑分支的 scenario + 标注哪些 scenario 仅验证数据流
- **Step 6 强制**：判定分 PASS / WEAK_PASS / FAIL 三级；运行后必须输出按项目类型的覆盖摘要报告；WEAK_PASS 时必须主动建议替代 scenario
