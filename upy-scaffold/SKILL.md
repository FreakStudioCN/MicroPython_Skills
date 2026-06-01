---
name: upy-scaffold
description: 第三步——项目骨架生成。读取 select-hw 阶段的 project-manifest.json，按调度模式（Timer/asyncio/_thread）生成完整 firmware/ 目录骨架。触发：upy-select-hw 完成后自动进入。
---

# 项目骨架生成 Skill

## 角色定位

给定 `project-manifest.json`（phase: select-hw），确定调度模式，生成完整的 `firmware/` 项目骨架。**不写业务逻辑，不填充驱动代码，不转换异步驱动。**

---

## 前置检查

```bash
python --version
python -c "import flake8; print('flake8 OK')"
```

无外部依赖（Python 3 标准库 + flake8）。

---

## 执行步骤

### Step 1: 审批选型 — 调度模式 + 额外文件

读取 `project-manifest.json`，使用 **AskUserQuestion** 呈现多选审批界面。

#### 1A: 调度模式（单选，推荐标记）

```
推荐规则（仅用于标记 Recommended，不影响可选项）：
  devices 中有 display 且含 LVGL              → async
  requirements.network = wifi                 → async
  requirements.special_requirements 含 "lcd"  → async
  默认                                        → timer
```

AskUserQuestion：

```
header: "调度模式"
question: "选择调度模式（推荐项已标注）："
options:
  - Timer tick (Recommended) — ISR 计数 + 主循环轮询，适合纯传感器采集
  - asyncio — uasyncio 原生协程，适合 WiFi / LVGL / LCD
  - _thread — 多线程，适合阻塞式操作
```

_mode 仅用于骨架生成时的 main.py 和 task stub 形态选择，驱动转换（同步→异步）由 `upy-generate` 负责。_

#### 1B: 额外模块（多选）

```
header: "额外模块"
question: "是否需要注入以下可选模块？（可多选）"
multiSelect: true
options:
  - 日志系统 (lib/logger/*) — logging + rotating_logger，设备端日志记录与轮转
  - 性能计时器 (lib/time_helper.py) — timed_function / timed_coro 装饰器，统计函数耗时
  - 维护任务 (tasks/maintenance.py) — GC 检查 + 空闲回调
  - 部署工具 (tools/flash_device.py) — mpy 编译 + 固件烧录 + 文件上传
  - PC 日志读取 (tools/read_device_log.py + log_report.py) — 从 PC 读取设备日志并生成 JSON 报告
```

#### 1C: 用户自定义文件（多选 + 自由输入）

```
header: "自定义"
question: "是否需要额外生成自定义文件？"
options:
  - 不需要额外文件
  - 自定义目录/文件（请在 Other 中输入，如 firmware/lib/my_utils.py, host/gui.py）
```

---

### Step 2: 按模式处理

#### 模式 A: Timer tick（默认）

**不额外获取外部文档**。注入 `lib/scheduler/timer_sched.py`，ISR 计数 + 主循环轮询。

#### 模式 B: asyncio

**WebFetch MicroPython asyncio 官方文档**以确认 API 用法：

```
WebFetch: https://docs.micropython.org/en/latest/library/asyncio.html
提取：create_task, run, sleep_ms, gather, Event, Queue 等 API
```

**不注入 scheduler.py**。main.py 直接使用 `uasyncio` 原生 API。

#### 模式 C: _thread

**WebFetch Python _thread 官方文档**以确认 API 用法：

```
WebFetch: https://docs.python.org/3.5/library/_thread.html#module-_thread
提取：start_new_thread, allocate_lock, exit 等 API
```

**不注入 scheduler.py**。main.py 直接使用 `_thread` 原生 API。

---

### Step 3: 生成项目骨架

调用 `init_scaffold.py`：

```bash
python G:/MicroPython_Skills/upy-scaffold/scripts/init_scaffold.py \
  --project-dir {project_dir} \
  --mode {timer|async|thread}
```

**脚本自动完成：**

| 步骤 | 文件 | 方式 |
|------|------|------|
| board.py | pinout → BOARDS 字典 + 查询函数 | 生成 |
| conf.py | requirements → 采样率/日志/看门狗常量 | 生成 |
| boot.py | WDT + emergency_exception_buf | 生成 |
| main.py | 按模式生成不同入口 | 生成 |
| lib/logger/* | logging + rotating_logger + __init__ | 复制模板 |
| lib/time_helper.py | timed_function + timed_coro | 复制模板 |
| lib/scheduler/* | timer_sched.py + __init__ | **仅 timer 模式** |
| tasks/maintenance.py | GC 检查 + 错误回调 | 复制模板 |
| drivers/* | 每个器件一个 stub 包 | 生成 |
| tools/flash_device.py | .py→.mpy 编译 + 烧录 + 上传 | 复制模板 |
| tools/read_device_log.py | PC 端设备日志读取 | 复制模板 |
| tools/log_report.py | 日志→JSON 报告解析 | 复制模板 |
| host/ | PC 上位机代码（不做约束） | .gitkeep |
| test/device/ | 设备端 unittest 测试框架 | .gitkeep |
| test/pc/ | PC 端测试脚本 | .gitkeep |
| build/firmware/ | .bin/.uf2/.hex 固件 | .gitkeep |
| build/mpy/ | 编译后 .mpy 文件 | .gitkeep |
| firmware/assets/ | 设备端资源文件（音频等） | .gitkeep |
| README.md | 项目名 + BOM + 引脚表 | 生成 |
| LICENSE | MIT | 生成 |
| .flake8 | F821/F401 豁免 + max-line=120 | 生成 |
| — | flake8 验证 | 脚本末尾自动执行 |

---

### 三种模式的 main.py 形态

main.py 由 scaffold **仅生成硬件实例化 + 调度器框架**，task 注册留给 `upy-generate`。

**Timer：**
```python
from machine import Pin, I2C
from lib.scheduler.timer_sched import Scheduler
from tasks.maintenance import maintenance_tick

# Pin numbers from manifest.hardware.pinout
i2c = I2C(<bus_id>, scl=Pin(<scl>), sda=Pin(<sda>), freq=400000)
# ...

sc = Scheduler(timer_id=-1, tick_ms=100, idle_cb=maintenance_tick)
# TODO: upy-generate registers tasks here
sc.start()
```

**asyncio：**
```python
import uasyncio as asyncio
from machine import Pin, I2C
from tasks.maintenance import maintenance_tick

i2c = I2C(<bus_id>, scl=Pin(<scl>), sda=Pin(<sda>), freq=400000)
# ...

async def main():
    # TODO: upy-generate creates async tasks here
    while True:
        maintenance_tick()
        await asyncio.sleep_ms(100)
asyncio.run(main())
```

**_thread：**
```python
import _thread
import time
from machine import Pin, I2C
from tasks.maintenance import maintenance_tick

i2c = I2C(<bus_id>, scl=Pin(<scl>), sda=Pin(<sda>), freq=400000)
# ...

# TODO: upy-generate starts threads here
while True:
    maintenance_tick()
    time.sleep_ms(100)
```

---

## 与其他 skill 的关系

- ← `upy-select-hw`：输入 manifest（mcu + pinout + bom + devices）
- → `upy-generate`：传入完整骨架 + manifest，业务代码生成
- → `upy-wiring`：引脚分配表 → 接线图
- → `upy-diagram`：代码结构 → 架构图
- → `upy-simulate`：PC 端全流程业务模拟

---

## 强约束

- **不生成业务 task 文件**：`tasks/` 下只放通用工具（`maintenance.py` + `__init__.py`），业务 task（sensor/display/alarm/network）由 `upy-generate` 创建
- **不转换驱动**：驱动同步/异步转换是 `upy-generate` 的职责
- **asyncio / _thread 模式不注入 scheduler.py**：直接用原生 API，不额外封装
- **timer 模式使用已有 Scheduler.py 参考实现**：ISR 只计数，主循环执行
- **board.py 不做硬件初始化**：只存常量映射，实例创建在 main.py
- **conf.py 不放敏感数据**：无 Wi-Fi 密码、API Key
- **生成结束自动 flake8**：脚本末尾自动验证，不通过打印 warning
