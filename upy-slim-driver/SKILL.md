---
name: upy-slim-driver
description: Use this skill when the user wants to reduce the memory footprint of an existing MicroPython driver .py file (or all driver files in a directory) according to the GraftSense memory minimization guide. Invoke when user says things like "减少内存占用", "slim driver", "降低RAM使用", "对驱动做内存优化", or provides a driver .py file path or directory path and asks for memory reduction.
---

# MicroPython 驱动内存占用优化 Skill

## 角色定位

你是 GraftSense MicroPython 驱动内存优化助手。给定一个已规范化的驱动 `.py` 文件（或包含多个驱动文件的目录），按照 GraftSense 内存占用最小化指南逐项检查并改写，输出完整优化后的文件内容。

本 Skill 聚焦 **RAM 占用**（峰值堆内存、运行时对象数量），与 `upy-opt-driver`（聚焦执行速度）互补。两者存在一处重叠：预分配缓冲区（P0#1）——本 Skill 从"避免堆分配、降低峰值 RAM"角度处理，`upy-opt-driver` 从"消除 GC 抖动、提升速度"角度处理；两者改写结果相同，不重复执行。

## 核心约束（不可违反）

- 不得修改对外 API 名称（公共方法名、属性名）
- 不得修改方法签名语义（参数含义、返回值含义）
- 不得修改硬件通信时序（I2C/SPI/UART 读写顺序、延时）
- `_CONST` 私有常量改写仅适用于**模块内部使用**的常量；若常量被外部代码直接引用（如 `driver.REG_CONFIG`），保留公共名称，在说明表中提示用户
- `gc.disable()` 区间必须短且有界，禁止在可能阻塞的 I/O 操作内使用

## 执行步骤

### 单文件模式（用户提供 `.py` 路径）

1. 读取用户指定的驱动 `.py` 文件；**必须重新读取文件完整内容，不得使用会话缓存**
2. 分析文件：识别常量声明方式、缓冲区分配位置、字符串拼接方式、寄存器表数据结构、GC 控制现状、`struct` 使用情况
3. 按 P0→P1→P2 优先级逐项检查并改写
4. 输出完整优化后的文件内容

### 多文件模式（用户提供目录路径）

1. 扫描目录下所有 `.py` 文件，排除 `main.py`
2. 列出所有驱动文件，询问用户："确认对全部文件执行内存优化，还是只选其中某个？"
3. 用户确认后，对每个文件依次执行单文件模式流程
4. 每个文件完成后暂停，显示：
   ```
   [文件 X/N — upy-slim-driver: xxx.py 完成]
   确认写入并继续下一个文件？还是需要修改？
   ```
5. 用户确认写入后继续下一个文件

---

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

#### P0#1 预分配缓冲区（避免堆分配）

**判断标准**：方法内有 `readfrom_mem()`、`read()`、`bytearray(n)` 动态创建——每次调用都在堆上分配新对象，增加峰值 RAM 并触发 GC。

**错误写法（禁止）：**
```python
def _read_reg(self, reg: int, nbytes: int) -> bytearray:
    # 每次调用堆分配 nbytes 字节，调用 100 次 = 100 次堆分配
    data = self._i2c.readfrom_mem(self._addr, reg, nbytes)
    return data
```

**正确写法：**
```python
# 全局变量区声明复用缓冲区（按实际最大字节数声明，固定 RAM 占用）
_BUF1 = bytearray(1)
_BUF2 = bytearray(2)
_BUF6 = bytearray(6)

class SensorDriver:
    def _read_reg(self, reg: int, nbytes: int) -> bytearray:
        # 复用预分配缓冲区，堆分配次数从 N 次降为 0 次
        if nbytes == 1:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF1)
            return _BUF1
        elif nbytes == 2:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF2)
            return _BUF2
```

**规则细节：**
- 缓冲区命名 `_BUFn`（n 为字节数），声明在全局变量区
- `read()` 一律改为 `readinto()` 或 `readfrom_mem_into()`
- 若已由 `upy-opt-driver` 执行过此项，跳过并在说明表中标注"已由 upy-opt-driver 处理"

---

#### P0#2 私有 `_CONST` 常量（零 RAM 占用）

**判断标准**：模块级常量使用公共名称（如 `REG_CONFIG = const(0x1A)`）且仅在模块内部使用——公共 `const` 仍会在模块全局字典中占用一个条目（约 40 字节/条目）；私有 `_CONST` 不写入全局字典，RAM 占用为零。

**错误写法（禁止，仅内部使用却用公共名称）：**
```python
from micropython import const

REG_CONFIG  = const(0x1A)
REG_DATA    = const(0x00)
REG_STATUS  = const(0x02)
MAX_RETRY   = const(3)
TIMEOUT_MS  = const(500)
```

**正确写法：**
```python
from micropython import const

# 私有名称（下划线前缀）：不写入全局字典，RAM 占用为零
# 5 个常量节省约 200 字节 RAM
_REG_CONFIG  = const(0x1A)
_REG_DATA    = const(0x00)
_REG_STATUS  = const(0x02)
_MAX_RETRY   = const(3)
_TIMEOUT_MS  = const(500)
```

**规则细节：**
- 仅改写**模块内部使用**的常量；被外部引用的公共常量保留原名，在说明表中提示
- 同步更新文件内所有引用该常量的位置（方法体内的 `REG_CONFIG` → `_REG_CONFIG`）
- 若文件已全部使用 `_CONST` 私有形式，标注"已符合规范，跳过"

---

#### P0#3 避免循环内字符串 `+` 拼接

**判断标准**：循环体内有字符串 `+` 拼接——每次 `+` 都创建新字符串对象，N 次循环 = N 次堆分配，且旧对象需等 GC 回收。

**错误写法（禁止）：**
```python
def build_report(self, readings: list) -> str:
    result = ""
    for i, val in enumerate(readings):
        # 每次 + 创建新字符串对象，100 次循环 = 100 次堆分配
        result = result + "ch" + str(i) + "=" + str(val) + "\n"
    return result
```

**正确写法（`.join()` + 生成器）：**
```python
def build_report(self, readings: list) -> str:
    # 仅创建一个最终字符串对象，中间对象在同一次 GC 周期内回收
    return "\n".join("ch{}={}".format(i, val) for i, val in enumerate(readings))
```

**静态拼接写法（编译期合并，零运行时分配）：**
```python
# 相邻字符串字面量在编译期合并为一个对象，运行时零分配
_MSG_INIT = "SensorDriver " "init " "ok"
_MSG_ERR  = "I2C " "read " "failed"
```

**规则细节：**
- 仅改写**循环内**的字符串 `+`；单次拼接（循环外）无需改写
- 优先用 `.format()` 或 f-string（MicroPython 1.20+ 支持）；多段静态字符串用相邻字面量合并
- 日志/调试字符串若仅在 `DEBUG` 模式下执行，可豁免

---

#### P0#4 `bytes`/`bytearray` 替代寄存器列表

**判断标准**：模块级或类级有存储寄存器地址、配置序列、查找表的 `list`——`list` 存储对象引用（每个元素约 8 字节指针 + 对象头），`bytes` 存储原始字节（每个元素 1 字节），100 个寄存器地址节省约 700 字节 RAM。

**错误写法（禁止）：**
```python
# list 存储：8 个元素约占 64+ 字节 RAM
_REG_TABLE = [0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x20]
_INIT_SEQ  = [0xAE, 0x00, 0x10, 0x40, 0xA1, 0xC8, 0xA6]
```

**正确写法：**
```python
# bytes 存储：每个元素 1 字节，8 个元素仅占 8 字节 RAM（节省约 90%）
_REG_TABLE = b'\x00\x01\x02\x03\x10\x11\x12\x20'
_INIT_SEQ  = b'\xAE\x00\x10\x40\xA1\xC8\xA6'

# 需要修改元素时用 bytearray
_CAL_TABLE = bytearray(b'\x00\x80\xFF\x40')
```

**`struct` 存储多字节数值（如 16 位寄存器地址）：**
```python
import struct

# list 存储 16 位地址：10 个元素约 80+ 字节
# struct 存储：10 x 2 字节 = 20 字节（节省约 75%）
_REG16_TABLE = struct.pack('10H', 0x0100, 0x0200, 0x0300, 0x0400, 0x0500,
                                   0x0600, 0x0700, 0x0800, 0x0900, 0x0A00)

def _get_reg(self, idx: int) -> int:
    return struct.unpack_from('H', _REG16_TABLE, idx * 2)[0]
```

**规则细节：**
- 仅适用于**同类型数值**的容器；混合类型（字符串+数字）的 `list` 不改写
- 元素值须在 0–255 范围内才能用 `bytes`/`bytearray`；超出范围用 `struct`
- 只读表用 `bytes`，需要运行时修改的用 `bytearray`

---

### P1 — 尽量改

#### P1#5 `gc.collect()` 前置批量操作

**判断标准**：方法内有批量动态对象创建（多次 `bytearray`、列表推导、字符串拼接），且对响应时间敏感——提前触发 GC 可避免操作过程中随机触发（随机触发时机不可控，可能在 I2C 传输中途暂停）。

```python
import gc

def batch_read(self, count: int) -> list:
    # 批量操作前手动触发 GC，清理碎片，降低操作中途被打断的概率
    # gc.collect() 耗时约 1ms，比操作中途随机触发代价更可控
    gc.collect()
    results = []
    for i in range(count):
        results.append(self._read_reg(i, 2))
    return results
```

**规则细节：**
- 放在批量操作**之前**，不是之后
- 不要在 ISR 回调中调用 `gc.collect()`
- 单次小操作无需添加；仅在已知会创建大量临时对象的方法前添加

---

#### P1#6 `gc.disable()`/`gc.enable()` 保护关键区间

**判断标准**：有对时序敏感的连续操作序列（如多步 I2C 写入、SPI 帧传输），且中途触发 GC 会导致时序违规或数据错误。

```python
import gc

def _send_frame(self, data: bytearray) -> None:
    """
    发送完整数据帧
    Notes:
        - ISR-safe: 否
        - gc.disable() 保护区间：禁止 GC 在帧传输中途触发，避免时序违规
        - 区间内不得有动态内存分配操作
    """
    # 禁用 GC，保证帧传输不被中断
    gc.disable()
    try:
        self._cs.value(0)
        self._spi.write(data)
        self._cs.value(1)
    finally:
        # 必须在 finally 中恢复，防止异常导致 GC 永久禁用
        gc.enable()
```

**规则细节：**
- `gc.disable()` 区间必须**短且有界**（微秒到毫秒级），禁止包含可能阻塞的 I/O
- 必须用 `try/finally` 包裹，确保异常时也能恢复
- 区间内禁止动态内存分配（否则内存耗尽时直接崩溃，无 GC 兜底）
- 不适用于普通读写方法；仅用于有明确时序要求的帧级操作

---

#### P1#7 `struct.pack_into()` 复用缓冲区

**判断标准**：有重复调用 `struct.pack()` 的方法——`struct.pack()` 每次返回新 `bytes` 对象（堆分配）；`struct.pack_into()` 写入预分配缓冲区，零堆分配。

**错误写法（禁止）：**
```python
def _build_cmd(self, reg: int, value: int) -> None:
    # 每次调用创建新 bytes 对象，触发堆分配
    cmd = struct.pack('>BH', reg, value)
    self._i2c.writeto(self._addr, cmd)
```

**正确写法：**
```python
import struct

# 全局变量区预分配命令缓冲区（1 byte reg + 2 bytes value = 3 bytes）
_CMD_BUF = bytearray(3)

class SensorDriver:
    def _build_cmd(self, reg: int, value: int) -> None:
        # pack_into 写入预分配缓冲区，零堆分配
        struct.pack_into('>BH', _CMD_BUF, 0, reg, value)
        self._i2c.writeto(self._addr, _CMD_BUF)
```

**规则细节：**
- 缓冲区大小须与 `struct` 格式字符串匹配（用 `struct.calcsize()` 验证）
- 命名遵循 `_CMD_BUF`、`_PKT_BUF` 等语义化名称，声明在全局变量区
- 若方法已使用预分配缓冲区（P0#1），检查是否可合并复用同一缓冲区

---

### P2 — 可选

#### P2#8 `__slots__` 限制实例属性

**判断标准**：驱动类有固定的实例属性集合（`__init__` 中全部声明，运行时不动态添加）——默认 Python 类用 `__dict__` 存储实例属性（字典开销约 200+ 字节/实例）；`__slots__` 用固定数组替代，节省约 50–200 字节/实例。

```python
class SensorDriver:
    # 声明固定属性集合，禁用 __dict__，节省约 50-200 字节/实例
    __slots__ = ('_i2c', '_addr', '_buf', '_mv', '_last_val')

    def __init__(self, i2c, addr: int = 0x68) -> None:
        self._i2c      = i2c
        self._addr     = addr
        self._buf      = bytearray(6)
        self._mv       = memoryview(self._buf)
        self._last_val = 0
```

**规则细节：**
- `__slots__` 中必须列出 `__init__` 内所有 `self.xxx` 赋值的属性名
- 若子类继承此类，子类也需声明 `__slots__ = ()`（否则子类仍有 `__dict__`）
- 若驱动类在运行时动态添加属性（如插件式扩展），不适用此优化

---

#### P2#9 生成器替代列表（流式数据）

**判断标准**：方法返回大型列表（> 50 个元素），且调用方逐个处理元素——返回完整列表需一次性分配全部内存；生成器按需产出，峰值 RAM 仅为单个元素大小。

**错误写法（禁止，大列表一次性分配）：**
```python
def read_all_channels(self) -> list:
    results = []
    for ch in range(16):
        results.append(self._read_channel(ch))
    return results
```

**正确写法（生成器，峰值 RAM = 单个元素）：**
```python
def iter_channels(self):
    """
    逐通道产出读数（生成器）
    Yields:
        int: 单通道原始读数
    Notes:
        - 峰值 RAM 仅为单个读数大小，适合通道数 > 16 的场景
    """
    for ch in range(16):
        yield self._read_channel(ch)
```

**规则细节：**
- 仅适用于调用方**逐个处理**的场景；若调用方需要随机访问（`results[5]`），不适用
- 生成器方法命名建议用 `iter_` 前缀，与返回列表的方法区分
- 若原方法名是公共 API，保留原方法（返回列表），新增 `iter_` 版本，在说明表中提示

---

#### P2#10 `micropython.mem_info()` 诊断标注

**判断标准**：用户要求诊断内存使用，或文件中有复杂的内存分配逻辑需要验证优化效果。

```python
import micropython
import gc

def _check_memory(self, label: str) -> None:
    """输出当前堆内存状态（调试用，生产环境删除）"""
    # [调试] 输出详细堆信息
    micropython.mem_info(1)
    free  = gc.mem_free()
    alloc = gc.mem_alloc()
    print("{}: free= alloc={} total={}".format(label, free, alloc, free + alloc))
```

**规则细节：**
- 此项仅在用户明确要求诊断时执行
- 诊断代码必须标注 `# [调试]` 注释，提醒用户在生产环境删除
- 不主动在所有方法中插入诊断代码

---

## 优化效果参考（判断是否值得改写）

| 优化手段 | 典型场景 | RAM 节省估算 | 改写成本 |
|---|---|---|---|
| 私有 `_CONST`（P0#2） | 10 个模块常量 | **~400 字节** | 低 |
| `bytes` 替代 `list`（P0#4） | 100 个寄存器地址 | **~700 字节** | 低 |
| 预分配缓冲区（P0#1） | I2C/SPI 读写 | **消除峰值堆分配** | 低 |
| `__slots__`（P2#8） | 单驱动实例 | **50–200 字节/实例** | 低 |
| `struct.pack_into()`（P1#7） | 高频命令构造 | 消除临时 bytes 对象 | 低 |
| 避免循环字符串 `+`（P0#3） | 日志/报告生成 | 消除临时字符串对象 | 低 |
| `gc.collect()` 前置（P1#5） | 批量读取操作 | 降低 GC 触发随机性 | 低 |
| `gc.disable()` 保护（P1#6） | 时序敏感帧传输 | 防止 GC 中途打断 | 中 |
| 生成器替代列表（P2#9） | 16+ 通道流式读取 | **峰值 RAM O(N)→O(1)** | 中 |

---

## 输出格式

1. 输出完整优化后的 Python 文件内容（代码块预览）。
2. 附简短说明表：
   - **P0 执行情况**：列出全部 4 项，标注"已执行"或"不适用（原因）"
   - **P1 执行情况**：列出实际执行的 P1 项及判断依据（为何适用）
   - **P2 执行情况**：列出实际执行的 P2 项及判断依据
   - **与 upy-opt-driver 重叠说明**：若 P0#1 已由 `upy-opt-driver` 处理，在此标注
3. 询问用户："确认写入原文件吗？"，用户确认后将内容覆盖写入原文件。

---

## 完整规范参考

[内存优化指南（本地）](../MicroPython_Memory_Footprint_Minimization_Guide.md)

[完整驱动规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-slim-driver/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-slim-driver/SKILL.md && git commit -m "skill(upy-slim-driver): <规则描述>"`
