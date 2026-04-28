---
name: upy-slim-driver
description: Use this skill when the user wants to reduce the memory footprint of any existing MicroPython .py file (driver, main.py, or any other file) according to the GraftSense memory minimization guide. Invoke when user says things like "减少内存占用", "slim", "降低RAM使用", "对文件做内存优化", "优化内存", or provides any .py file path or directory path and asks for memory reduction.
---

# MicroPython 内存占用优化 Skill

## 角色定位

你是 GraftSense MicroPython 内存优化助手。给定任意一个 `.py` 文件（驱动文件、`main.py` 或其他文件），按照 GraftSense 内存占用最小化指南逐项检查并改写，输出完整优化后的文件内容。

本 Skill 聚焦 **RAM 占用**（峰值堆内存、运行时对象数量），与 `upy-opt-driver`（聚焦执行速度）互补。两者存在一处重叠：预分配缓冲区（P0#1）——本 Skill 从"避免堆分配、降低峰值 RAM"角度处理，`upy-opt-driver` 从"消除 GC 抖动、提升速度"角度处理；两者改写结果相同，不重复执行。

## 核心约束（不可违反）

- 不得修改对外 API 名称（公共方法名、属性名）
- 不得修改方法签名语义（参数含义、返回值含义）
- 不得修改硬件通信时序（I2C/SPI/UART 读写顺序、延时）
- `_CONST` 私有常量改写仅适用于**模块内部使用**的常量；若常量被外部代码直接引用（如 `driver.REG_CONFIG`），保留公共名称，在说明表中提示用户
- `gc.disable()` 区间必须短且有界，禁止在可能阻塞的 I/O 操作内使用
- `const()` 优化仅在 `.mpy` 或 frozen 字节码中完全生效，REPL 下效果极小

## 执行步骤

### 单文件模式（用户提供 `.py` 路径）

1. 读取用户指定的驱动 `.py` 文件；**必须重新读取文件完整内容，不得使用会话缓存**
2. 分析文件：识别常量声明方式、缓冲区分配位置、字符串拼接方式、寄存器表数据结构、GC 控制现状、`struct` 使用情况、类属性存储方式
3. 按 P0→P1→P2 优先级逐项检查并改写
4. 输出完整优化后的文件内容

### 多文件模式（用户提供目录路径）

1. 扫描目录下所有 `.py` 文件（包含 `main.py`，不排除任何文件）
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
    # 峰值 RAM = 所有未回收对象总和，可能导致内存碎片化
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
        # 峰值 RAM = 缓冲区大小（固定），无碎片化风险
        if nbytes == 1:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF1)
            return _BUF1
        elif nbytes == 2:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF2)
            return _BUF2
        elif nbytes == 6:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF6)
            return _BUF6
```

**规则细节：**
- 缓冲区命名 `_BUFn`（n 为字节数），声明在全局变量区
- `read()` 一律改为 `readinto()` 或 `readfrom_mem_into()`
- 多尺寸缓冲区分别声明，不用动态 `bytearray(nbytes)`
- 若已由 `upy-opt-driver` 执行过此项，跳过并在说明表中标注"已由 upy-opt-driver 处理"

#### P0#2 私有 `_CONST` 常量（零 RAM 占用）

**判断标准**：模块级常量使用公共名称（如 `REG_CONFIG = const(0x1A)`）且仅在模块内部使用——公共 `const` 仍会在模块全局字典中占用一个条目（约 40 字节/条目）；私有 `_CONST` 不写入全局字典，RAM 占用为零。

**错误写法（禁止，仅内部使用却用公共名称）：**
```python
from micropython import const

# 公共常量：每个在全局字典中占用约 40 字节
# 5 个常量 = 约 200 字节 RAM
REG_CONFIG  = const(0x1A)
REG_DATA    = const(0x00)
REG_STATUS  = const(0x02)
MAX_RETRY   = const(3)
TIMEOUT_MS  = const(500)

class SensorDriver:
    def _read_status(self) -> int:
        # 模块内部使用，外部代码不访问这些常量
        return self._read_reg(REG_STATUS, 1)[0]
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

class SensorDriver:
    def _read_status(self) -> int:
        # 使用私有常量，编译时直接替换为数值
        return self._read_reg(_REG_STATUS, 1)[0]
```

**规则细节：**
- 仅改写**模块内部使用**的常量；被外部引用的公共常量（如 `driver.REG_CONFIG`）保留原名，在说明表中提示用户
- 同步更新文件内所有引用该常量的位置（方法体内的 `REG_CONFIG` → `_REG_CONFIG`）
- 若文件已全部使用 `_CONST` 私有形式，标注"已符合规范，跳过"
- **关键限制**：`const()` 优化仅在 `.mpy` 或 frozen 字节码中完全生效，REPL 下效果极小

**边界情况处理：**

| 场景 | 处理方式 |
|---|---|
| 常量被外部代码引用（如 `from driver import REG_CONFIG`） | 保留公共名称，在说明表中标注"公共 API，不可改为私有" |
| 常量用于位运算表达式（如 `const(1 << 5)`） | 支持，`const()` 可处理编译时整数表达式 |
| 常量引用其他常量（如 `COLS = const(0x10 + ROWS)`） | 报错，必须改为字面值 `const(0x10 + 33)` |

#### P0#3 避免循环内字符串 `+` 拼接

**判断标准**：循环体内有字符串 `+` 拼接——每次 `+` 都创建新字符串对象，N 次循环 = N 次堆分配，且旧对象需等 GC 回收。

**错误写法（禁止）：**
```python
def build_report(self, readings: list) -> str:
    result = ""
    for i, val in enumerate(readings):
        # 每次 + 创建新字符串对象，100 次循环 = 100 次堆分配
        # 第 1 次："" + "ch" = "ch" (创建对象1)
        # 第 2 次："ch" + "0" = "ch0" (创建对象2，对象1成为垃圾)
        # 第 3 次："ch0" + "=" = "ch0=" (创建对象3，对象2成为垃圾)
        # ...累计创建数百个临时对象，峰值 RAM 极高
        result = result + "ch" + str(i) + "=" + str(val) + "\n"
    return result
```

**正确写法 1（`.join()` + 生成器，推荐）：**
```python
def build_report(self, readings: list) -> str:
    # 生成器逐个产出字符串片段，join() 一次性分配最终字符串
    # 仅创建一个最终字符串对象，中间对象在同一次 GC 周期内回收
    # 峰值 RAM = 最终字符串大小 + 生成器开销（约 100 字节）
    return "\n".join("ch{}={}".format(i, val) for i, val in enumerate(readings))
```

**正确写法 2（`.format()` 预分配，适合固定格式）：**
```python
def build_report(self, readings: list) -> str:
    # 预分配列表，避免动态增长
    lines = []
    for i, val in enumerate(readings):
        # format() 仅创建一个字符串对象，无中间拼接
        lines.append("ch{}={}".format(i, val))
    return "\n".join(lines)
```

**正确写法 3（静态拼接，编译期合并）：**
```python
# 相邻字符串字面量在编译期合并为一个对象，运行时零分配
_MSG_INIT = "SensorDriver " "init " "ok"
_MSG_ERR  = "I2C " "read " "failed"
_HEADER   = "GraftSense " "v1.0 " "2026"
```

**规则细节：**
- 仅改写**循环内**的字符串 `+`；单次拼接（循环外）无需改写
- 优先用 `.format()` 或 f-string（MicroPython 1.20+ 支持）；多段静态字符串用相邻字面量合并
- 日志/调试字符串若仅在 `DEBUG` 模式下执行，可豁免
- 若循环次数 < 10 且字符串总长 < 100 字节，改写收益极小，可跳过

**内存对比（100 次循环）：**

| 方法 | 临时对象数 | 峰值 RAM 估算 |
|---|---|---|
| 循环内 `+` 拼接 | ~400 个 | ~10KB（碎片化严重） |
| `.join()` + 生成器 | ~1 个 | ~2KB（连续内存） |
| 静态字面量合并 | 0 个 | 0（编译期处理） |

#### P0#4 `bytes`/`bytearray` 替代寄存器列表

**判断标准**：模块级或类级有存储寄存器地址、配置序列、查找表的 `list`——`list` 存储对象引用（每个元素约 8 字节指针 + 对象头），`bytes` 存储原始字节（每个元素 1 字节），100 个寄存器地址节省约 700 字节 RAM。

**错误写法（禁止）：**
```python
# list 存储：8 个元素约占 64+ 字节 RAM（每个整数对象 4 字节 + 指针 8 字节）
_REG_TABLE = [0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x20]
_INIT_SEQ  = [0xAE, 0x00, 0x10, 0x40, 0xA1, 0xC8, 0xA6]

class DisplayDriver:
    def _init_display(self) -> None:
        for reg in _INIT_SEQ:
            self._write_reg(reg)
```

**正确写法（`bytes` 只读表）：**
```python
# bytes 存储：每个元素 1 字节，8 个元素仅占 8 字节 RAM（节省约 90%）
_REG_TABLE = b'\x00\x01\x02\x03\x10\x11\x12\x20'
_INIT_SEQ  = b'\xAE\x00\x10\x40\xA1\xC8\xA6'

class DisplayDriver:
    def _init_display(self) -> None:
        # bytes 支持迭代和索引，用法与 list 一致
        for reg in _INIT_SEQ:
            self._write_reg(reg)
```

**正确写法（`bytearray` 可修改表）：**
```python
# 需要运行时修改元素时用 bytearray
_CAL_TABLE = bytearray(b'\x00\x80\xFF\x40')

class SensorDriver:
    def _update_calibration(self, idx: int, val: int) -> None:
        # bytearray 支持元素赋值
        _CAL_TABLE[idx] = val
```

**`struct` 存储多字节数值（如 16 位寄存器地址）：**
```python
import struct

# list 存储 16 位地址：10 个元素约 80+ 字节
# struct 存储：10 x 2 字节 = 20 字节（节省约 75%）
_REG16_TABLE = struct.pack('10H', 0x0100, 0x0200, 0x0300, 0x0400, 0x0500,
                                   0x0600, 0x0700, 0x0800, 0x0900, 0x0A00)

class AdvancedDriver:
    def _get_reg(self, idx: int) -> int:
        # unpack_from 从指定偏移解包，无需切片（切片会创建副本）
        return struct.unpack_from('H', _REG16_TABLE, idx * 2)[0]
```

**规则细节：**
- 仅适用于**同类型数值**的容器；混合类型（字符串+数字）的 `list` 不改写
- 元素值须在 0–255 范围内才能用 `bytes`/`bytearray`；超出范围用 `struct`
- 只读表用 `bytes`，需要运行时修改的用 `bytearray`
- `struct.pack()` 格式码：`'B'` = 无符号字节，`'H'` = 无符号 16 位，`'I'` = 无符号 32 位

**适用场景对照表：**

| 数据类型 | 推荐方案 | 内存占用（100 个元素）| 使用限制 |
|---|---|---|---|
| 8 位寄存器地址（0-255） | `bytes` | ~100 字节 | 只读 |
| 8 位配置序列（需修改） | `bytearray` | ~100 字节 | 可修改 |
| 16 位寄存器地址 | `struct.pack('100H', ...)` | ~200 字节 | 需 `unpack_from` 访问 |
| 混合类型（字符串+数字） | `list`（保持原样） | ~800+ 字节 | 无限制 |

---

### P1 — 尽量改

#### P1#5 `gc.collect()` 前置批量操作

**判断标准**：方法内有批量动态对象创建（多次 `bytearray`、列表推导、字符串拼接），且对响应时间敏感——提前触发 GC 可避免操作过程中随机触发（随机触发时机不可控，可能在 I2C 传输中途暂停）。

```python
import gc

def batch_read(self, count: int) -> list:
    """
    批量读取传感器数据
    Args:
        count (int): 读取次数
    Returns:
        list: 读数列表
    Notes:
        - 批量操作前手动触发 GC，清理碎片，降低操作中途被打断的概率
        - gc.collect() 耗时约 1ms，比操作中途随机触发代价更可控
    """
    # 批量操作前手动触发 GC，清理碎片
    gc.collect()
    results = []
    for i in range(count):
        results.append(self._read_reg(i, 2))
    return results
```

**规则细节：**
- 放在批量操作**之前**，不是之后（之后清理无法避免操作中途触发）
- 不要在 ISR 回调中调用 `gc.collect()`（ISR 需要极低延迟）
- 单次小操作无需添加；仅在已知会创建大量临时对象的方法前添加
- 适用场景：批量 I2C 读取、大型数据帧构造、多通道采样

#### P1#6 `gc.disable()`/`gc.enable()` 保护关键区间

**判断标准**：有对时序敏感的连续操作序列（如多步 I2C 写入、SPI 帧传输），且中途触发 GC 会导致时序违规或数据错误。

**关键约束**：区间内禁止动态内存分配（否则内存耗尽时直接崩溃，无 GC 兜底）

```python
import gc

def _send_frame(self, data: bytearray) -> None:
    """
    发送完整数据帧
    Args:
        data (bytearray): 帧数据（必须预分配，禁止在 gc.disable 区间内创建）
    Notes:
        - ISR-safe: 否
        - gc.disable() 保护区间：禁止 GC 在帧传输中途触发，避免时序违规
        - 区间内不得有动态内存分配操作（bytearray、list、str 拼接等）
        - 区间必须短且有界（微秒到毫秒级），禁止包含可能阻塞的 I/O
    """
    # 禁用 GC，保证帧传输不被中断
    gc.disable()
    try:
        # 关键时序操作：CS 拉低 → SPI 写入 → CS 拉高
        # 此区间内禁止任何动态内存分配
        self._cs.value(0)
        self._spi.write(data)  # data 必须是预分配的 bytearray
        self._cs.value(1)
    finally:
        # 必须在 finally 中恢复，防止异常导致 GC 永久禁用
        gc.enable()
```

**错误示例（禁止，区间内动态分配）：**
```python
def _send_frame_bad(self, reg: int, value: int) -> None:
    gc.disable()
    try:
        # 错误：区间内创建 bytearray，若内存不足直接崩溃
        data = bytearray([reg, value])  # 禁止！
        self._spi.write(data)
    finally:
        gc.enable()
```

**正确示例（预分配缓冲区）：**
```python
# 全局预分配缓冲区
_FRAME_BUF = bytearray(64)

def _send_frame_good(self, reg: int, value: int) -> None:
    # 区间外准备数据
    _FRAME_BUF[0] = reg
    _FRAME_BUF[1] = value
    
    gc.disable()
    try:
        # 区间内仅操作预分配缓冲区，零动态分配
        self._spi.write(memoryview(_FRAME_BUF)[:2])
    finally:
        gc.enable()
```

**规则细节：**
- `gc.disable()` 区间必须**短且有界**（微秒到毫秒级），禁止包含可能阻塞的 I/O
- 必须用 `try/finally` 包裹，确保异常时也能恢复
- 区间内禁止动态内存分配（否则内存耗尽时直接崩溃，无 GC 兜底）
- 不适用于普通读写方法；仅用于有明确时序要求的帧级操作
- 不适用于 ISR 回调（ISR 本身已禁用中断，无需额外保护）

**适用场景判断：**

| 场景 | 是否适用 `gc.disable()` | 原因 |
|---|---|---|
| SPI 连续帧传输（CS 保持低电平） | 是 | 中途 GC 会导致帧间隔超时 |
| I2C 多字节写入（单次事务） | 否 | I2C 硬件自动处理时序，无需保护 |
| 普通传感器读取 | 否 | 单次操作耗时短，GC 影响可忽略 |
| 高频 GPIO 翻转（> 1kHz） | 是 | GC 暂停会导致波形失真 |

#### P1#7 `struct.pack_into()` 复用缓冲区

**判断标准**：有重复调用 `struct.pack()` 的方法——`struct.pack()` 每次返回新 `bytes` 对象（堆分配）；`struct.pack_into()` 写入预分配缓冲区，零堆分配。

**错误写法（禁止）：**
```python
import struct

def _build_cmd(self, reg: int, value: int) -> None:
    # 每次调用创建新 bytes 对象，触发堆分配
    # 调用 100 次 = 100 次堆分配 + 100 个临时对象等待 GC
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
        # 调用 100 次 = 0 次堆分配，峰值 RAM = 缓冲区大小（3 字节）
        struct.pack_into('>BH', _CMD_BUF, 0, reg, value)
        self._i2c.writeto(self._addr, _CMD_BUF)
```

**复杂示例（多格式命令）：**
```python
import struct

# 预分配多种命令格式的缓冲区
_CMD_SHORT = bytearray(2)   # 格式 'BB'
_CMD_LONG  = bytearray(5)   # 格式 'BHH'

class AdvancedDriver:
    def _send_short_cmd(self, reg: int, val: int) -> None:
        # 格式 'BB'：2 个无符号字节
        struct.pack_into('BB', _CMD_SHORT, 0, reg, val)
        self._i2c.writeto(self._addr, _CMD_SHORT)
    
    def _send_long_cmd(self, reg: int, val1: int, val2: int) -> None:
        # 格式 'BHH'：1 个字节 + 2 个 16 位无符号整数
        struct.pack_into('BHH', _CMD_LONG, 0, reg, val1, val2)
        self._i2c.writeto(self._addr, _CMD_LONG)
```

**规则细节：**
- 缓冲区大小须与 `struct` 格式字符串匹配（用 `struct.calcsize()` 验证）
- 命名遵循 `_CMD_BUF`、`_PKT_BUF` 等语义化名称，声明在全局变量区
- 若方法已使用预分配缓冲区（P0#1），检查是否可合并复用同一缓冲区
- 多种格式命令分别声明缓冲区，不用动态 `bytearray(struct.calcsize(fmt))`

**缓冲区大小验证：**
```python
import struct

# 验证缓冲区大小是否匹配格式字符串
assert len(_CMD_BUF) == struct.calcsize('>BH'), "Buffer size mismatch"
# '>BH' = 大端序 + 1 字节 + 2 字节 = 3 字节
```

**内存对比（100 次调用）：**

| 方法 | 堆分配次数 | 峰值 RAM 估算 | 临时对象数 |
|---|---|---|---|
| `struct.pack()` | 100 次 | ~300 字节（碎片化） | 100 个 |
| `struct.pack_into()` | 0 次 | 3 字节（固定） | 0 个 |

---

### P2 — 可选

#### P2#8 `__slots__` 限制实例属性

**判断标准**：驱动类有固定的实例属性集合（`__init__` 中全部声明，运行时不动态添加）——默认 Python 类用 `__dict__` 存储实例属性（字典开销约 200+ 字节/实例）；`__slots__` 用固定数组替代，节省约 50–200 字节/实例。

**关键约束**：若子类继承此类，子类也需声明 `__slots__ = ()`（否则子类仍有 `__dict__`）

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

**子类继承示例：**
```python
class AdvancedSensor(SensorDriver):
    # 子类必须声明 __slots__，否则子类仍有 __dict__
    # 空元组表示子类不新增属性，仅继承父类属性
    __slots__ = ()
    
    def advanced_read(self) -> int:
        # 可正常访问父类属性
        return self._last_val * 2
```

**新增属性的子类：**
```python
class ExtendedSensor(SensorDriver):
    # 子类新增属性需在 __slots__ 中声明
    __slots__ = ('_calibration', '_offset')
    
    def __init__(self, i2c, addr: int = 0x68) -> None:
        super().__init__(i2c, addr)
        self._calibration = 1.0
        self._offset      = 0
```

**规则细节：**
- `__slots__` 中必须列出 `__init__` 内所有 `self.xxx` 赋值的属性名
- 若子类继承此类，子类也需声明 `__slots__ = ()`（否则子类仍有 `__dict__`）
- 若驱动类在运行时动态添加属性（如插件式扩展），不适用此优化
- 属性名必须是字符串字面量，不支持动态属性名

**不适用场景：**

| 场景 | 是否适用 `__slots__` | 原因 |
|---|---|---|
| 固定属性集合的驱动类 | 是 | 节省 50-200 字节/实例 |
| 运行时动态添加属性 | 否 | `__slots__` 禁止动态属性 |
| 需要 `__dict__` 的插件系统 | 否 | 插件需要动态注入属性 |
| 单例驱动类（仅 1 个实例） | 否 | 节省效果不明显（< 200 字节） |

**内存节省估算：**
- 默认类（有 `__dict__`）：约 200+ 字节/实例
- `__slots__` 类：约 50 字节/实例（仅属性数组）
- 节省：约 150 字节/实例（10 个实例 = 1.5KB）

#### P2#9 生成器替代列表（流式数据）

**判断标准**：方法返回大型列表（> 50 个元素），且调用方逐个处理元素——返回完整列表需一次性分配全部内存；生成器按需产出，峰值 RAM 仅为单个元素大小。

**错误写法（禁止，大列表一次性分配）：**
```python
def read_all_channels(self) -> list:
    # 一次性分配 16 个元素的列表，峰值 RAM = 16 x 元素大小
    # 若每个元素是 bytearray(6)，峰值 RAM = 16 x 6 = 96 字节 + 列表开销
    results = []
    for ch in range(16):
        results.append(self._read_channel(ch))
    return results

# 调用方
driver = SensorDriver(...)
data = driver.read_all_channels()  # 峰值 RAM = 完整列表
for val in data:
    process(val)
```

**正确写法（生成器，峰值 RAM = 单个元素）：**
```python
def iter_channels(self):
    """
    逐通道产出读数（生成器）
    Yields:
        bytearray: 单通道原始读数（6 字节）
    Notes:
        - 峰值 RAM 仅为单个读数大小（6 字节），适合通道数 > 16 的场景
        - 调用方需逐个处理，不支持随机访问（如 results[5]）
    """
    for ch in range(16):
        yield self._read_channel(ch)

# 调用方
driver = SensorDriver(...)
for val in driver.iter_channels():  # 峰值 RAM = 单个元素（6 字节）
    process(val)
```

**兼容方案（保留原 API，新增生成器版本）：**
```python
class SensorDriver:
    def read_all_channels(self) -> list:
        """
        读取所有通道（返回列表，兼容旧代码）
        Returns:
            list: 所有通道读数
        Notes:
            - 峰值 RAM = 完整列表大小
            - 推荐使用 iter_channels() 生成器版本以降低内存占用
        """
        return list(self.iter_channels())
    
    def iter_channels(self):
        """
        逐通道产出读数（生成器，推荐）
        Yields:
            bytearray: 单通道原始读数
        Notes:
            - 峰值 RAM 仅为单个读数大小
        """
        for ch in range(16):
            yield self._read_channel(ch)
```

**规则细节：**
- 仅适用于调用方**逐个处理**的场景；若调用方需要随机访问（`results[5]`），不适用
- 生成器方法命名建议用 `iter_` 前缀，与返回列表的方法区分
- 若原方法名是公共 API，保留原方法（返回列表），新增 `iter_` 版本，在说明表中提示
- 生成器不支持 `len()`、索引访问、切片操作

**内存对比（16 通道，每通道 6 字节）：**

| 方法 | 峰值 RAM | 支持随机访问 | 适用场景 |
|---|---|---|---|
| 返回列表 | ~96 字节 + 列表开销 | 是 | 需要多次遍历、随机访问 |
| 生成器 | ~6 字节（单个元素） | 否 | 仅需单次遍历、内存受限 |

**生成器适用场景判断：**

| 场景 | 是否适用生成器 | 原因 |
|---|---|---|
| 16 通道 ADC 采样，逐个处理 | 是 | 峰值 RAM 降低 94% |
| 100 个传感器批量读取 | 是 | 峰值 RAM 从 O(N) 降为 O(1) |
| 需要随机访问 `data[5]` | 否 | 生成器不支持索引 |
| 需要多次遍历同一数据 | 否 | 生成器仅能遍历一次 |

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

## 输出格式

1. 输出完整优化后的 Python 文件内容（代码块预览）。
2. 附简短说明表：
   - **P0 执行情况**：列出全部 4 项，标注"已执行"或"不适用（原因）"
   - **P1 执行情况**：列出实际执行的 P1 项及判断依据（为何适用）
   - **P2 执行情况**：列出实际执行的 P2 项及判断依据
   - **与 upy-opt-driver 重叠说明**：若 P0#1 已由 `upy-opt-driver` 处理，在此标注
   - **RAM 节省估算**：根据优化项累计估算节省的 RAM 字节数
3. 询问用户："确认写入原文件吗？"，用户确认后将内容覆盖写入原文件。

**说明表示例：**

```
优化执行情况：

P0 必改项：
  ✓ P0#1 预分配缓冲区：已执行（3 个缓冲区，消除动态堆分配）
  ✓ P0#2 私有 _CONST：已执行（8 个常量改为私有，节省约 320 字节）
  ✓ P0#3 避免循环字符串 +：已执行（build_report 方法改用 .join()）
  ✓ P0#4 bytes 替代 list：已执行（_REG_TABLE 改为 bytes，节省约 56 字节）

P1 尽量改项：
  ✓ P1#5 gc.collect() 前置：已执行（batch_read 方法前添加）
  ✓ P1#7 struct.pack_into()：已执行（_build_cmd 方法改用预分配缓冲区）
  ✗ P1#6 gc.disable() 保护：不适用（无时序敏感的帧级操作）

P2 可选项：
  ✓ P2#8 __slots__：已执行（SensorDriver 类，节省约 150 字节/实例）
  ✗ P2#9 生成器：不适用（无大型列表返回方法）

与 upy-opt-driver 重叠：
  - P0#1 预分配缓冲区：本次执行（upy-opt-driver 未处理过此文件）

RAM 节省估算：
  - 私有常量：~320 字节
  - bytes 替代 list：~56 字节
  - __slots__：~150 字节/实例
  - 消除临时对象：峰值 RAM 降低约 40%
  - 总计：约 526 字节 + 峰值优化
```

---

## 完整规范参考

[内存优化指南（本地）](G:/GraftSense-Drivers-MicroPython#/MicroPython_Memory_Footprint_Minimization_Guide.md)

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