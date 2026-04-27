---
name: upy-opt-driver
description: Use this skill when the user wants to optimize the performance of an existing MicroPython driver .py file (or all driver files in a directory) according to the GraftSense performance optimization guide. Invoke when user says things like "优化驱动性能", "optimize driver", "加速驱动", "对驱动做性能优化", or provides a driver .py file path or directory path and asks for performance improvement.
---

# MicroPython 驱动性能优化 Skill

## 角色定位

你是 GraftSense MicroPython 驱动性能优化助手。给定一个已规范化的驱动 `.py` 文件（或包含多个驱动文件的目录），按照 GraftSense 性能优化指南逐项检查并改写，输出完整优化后的文件内容。

## 核心约束（不可违反）

- 不得修改对外 API 名称（公共方法名、属性名）
- 不得修改方法签名语义（参数含义、返回值含义）
- 不得修改硬件通信时序（I2C/SPI/UART 读写顺序、延时）
- `@viper` 改写必须在 docstring Notes 中标注整数溢出风险和位宽限制
- `@native` 改写必须在 docstring Notes 中标注限制（无生成器、无关键字参数）
- SIO 寄存器操作必须标注"RP2040 专属，其他平台不可用"

## 执行步骤

### 单文件模式（用户提供 `.py` 路径）

1. 读取用户指定的驱动 `.py` 文件；**必须重新读取文件完整内容，不得使用会话缓存**
2. 分析文件：识别缓冲区分配方式、循环结构、常量声明、计算密集型方法、浮点运算、ISR 回调
3. 按 P0→P1→P2 优先级逐项检查并改写
4. 输出完整优化后的文件内容

### 多文件模式（用户提供目录路径）

1. 扫描目录下所有 `.py` 文件，排除 `main.py`
2. 列出所有驱动文件，询问用户："确认对全部文件执行优化，还是只选其中某个？"
3. 用户确认后，对每个文件依次执行单文件模式流程
4. 每个文件完成后暂停，显示：
   ```
   [文件 X/N — upy-opt-driver: xxx.py 完成]
   确认写入并继续下一个文件？还是需要修改？
   ```
5. 用户确认写入后继续下一个文件

---

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

#### P0#1 预分配缓冲区

**判断标准**：方法内有 `readfrom_mem()`、`read()`、`bytearray(n)` 动态创建——每次调用都触发堆分配。

**错误写法（禁止）：**
```python
def _read_reg(self, reg: int, nbytes: int) -> bytearray:
    # 每次调用都在堆上分配新对象
    data = self._i2c.readfrom_mem(self._addr, reg, nbytes)
    return data
```

**正确写法：**
```python
# 全局变量区声明复用缓冲区（按实际用到的最大字节数声明）
_BUF1 = bytearray(1)
_BUF2 = bytearray(2)
_BUF6 = bytearray(6)

class SensorDriver:
    def _read_reg(self, reg: int, nbytes: int) -> bytearray:
        # 使用预分配缓冲区，避免每次分配新对象
        if nbytes == 1:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF1)
            return _BUF1
        elif nbytes == 2:
            self._i2c.readfrom_mem_into(self._addr, reg, _BUF2)
            return _BUF2
        # 更多尺寸按需扩展
```

**规则细节：**
- 缓冲区命名 `_BUFn`（n 为字节数），声明在全局变量区
- `read()` 一律改为 `readinto()` 或 `readfrom_mem_into()`
- 多尺寸缓冲区分别声明，不用动态 `bytearray(nbytes)`

---

#### P0#2 `memoryview` 替代切片拷贝

**判断标准**：有 `buf[a:b]` 切片传递给函数，且切片长度 > 32 字节——切片会创建完整数据副本触发堆分配。

**错误写法（禁止）：**
```python
def process(self) -> None:
    # ba[30:2000] 创建 1970 字节的副本，触发堆分配
    self._parse(self._buf[30:2000])
```

**正确写法：**
```python
# 初始化时创建 memoryview（仅分配小对象，几十字节）
def __init__(self, ...) -> None:
    self._buf = bytearray(2048)
    self._mv = memoryview(self._buf)

def process(self) -> None:
    # memoryview 切片不复制数据，仅传递地址，零分配
    self._parse(self._mv[30:2000])
```

**规则细节：**
- `memoryview` 仅支持缓冲区协议对象（`bytearray`、`array`、`bytes`），不支持 `list`
- 在 `__init__` 中创建并存为 `self._mv`，不在方法内临时创建

---

#### P0#3 缓存对象引用

**判断标准**：循环体内出现 `self.xxx` 属性访问（每次访问都进行字典查找），或嵌套属性 `self.obj.buf`——循环次数 > 100 时效果显著。

**错误写法（禁止）：**
```python
def fill_buffer(self) -> None:
    for i in range(1000):
        # 每次循环都执行属性查找（字典操作，有开销）
        self._buf[i] = self._addr + i
```

**正确写法：**
```python
def fill_buffer(self) -> None:
    # 循环前缓存到局部变量，消除循环内属性查找
    buf = self._buf
    addr = self._addr
    for i in range(1000):
        buf[i] = addr + i
```

**规则细节：**
- 嵌套属性（如 `self._display.framebuffer`）效果更显著，必须缓存
- 仅在循环次数 > 100 的方法内执行，单次访问无需缓存

---

#### P0#4 `const()` 常量

**判断标准**：模块级变量是寄存器地址、位掩码、固定配置值，但未用 `micropython.const()` 包裹——运行时每次访问都需字典查找。

**错误写法（禁止）：**
```python
# 普通变量赋值，每次访问走字典查找
REG_CONFIG = 0x1A
REG_DATA = 0x00
MAX_RETRY = 3
```

**正确写法：**
```python
from micropython import const

# const() 在编译时替换为数值，运行时零开销
REG_CONFIG = const(0x1A)
REG_DATA   = const(0x00)
MAX_RETRY  = const(3)
# 位运算常量同样支持
PIN_MASK   = const(1 << 5)
```

**规则细节：**
- `const()` 的优化在预编译字节码（`.mpy`）或 `import` 执行时才完全生效，REPL 下差异极小
- 只对模块级常量有效，不适用于类属性（类属性访问走不同路径）

---

### P1 — 尽量改

#### P1#5 手动 GC 控制

**判断标准**：方法内有大量动态对象创建（字符串拼接、列表推导、临时 bytearray），或被高频循环调用。

**适用条件**：方法会动态创建对象，且对响应时间敏感。

```python
import gc

def batch_read(self) -> list:
    # 性能关键操作前手动触发 GC，避免操作过程中随机触发
    # 提前清理内存（耗时约 1ms），比操作中途被打断代价更小
    gc.collect()
    results = []
    for i in range(100):
        results.append(self._read_reg(i, 1)[0])
    return results
```

**规则细节：**
- 放在性能关键代码段**之前**，不是之后
- 不要在 ISR 回调中调用 `gc.collect()`
- 不要每次调用都加，只在批量操作或已知会创建大量对象的方法前加

---

#### P1#6 `@micropython.native` 装饰器

**判断标准**：方法有大量 Python 字节码执行（循环、条件判断、数值计算），且满足以下所有条件：
- 无生成器（无 `yield`）
- 无关键字参数调用（无 `func(key=val)`）
- 无需完全兼容 Python 语义

**提速效果**：约 2 倍，代码体积增大约 50%。

```python
@micropython.native
def _decode_data(self, raw: bytearray) -> tuple:
    """
    解码原始数据
    ...
    Notes:
        - ISR-safe: 否
        - native 优化：约 2 倍提速；限制：无生成器、无关键字参数
    """
    msb = raw[0]
    lsb = raw[1]
    value = (msb << 8) | lsb
    sign = (value >> 15) & 1
    if sign:
        value = value - 65536
    return value, sign
```

**native 的限制（必须检查）：**

| 限制 | 说明 |
|---|---|
| 不支持生成器 | 函数内不能有 `yield` |
| 不支持关键字参数 | 调用其他函数时不能用 `func(key=val)` 形式 |
| 代码体积增大 | 编译后比字节码更占 Flash 空间 |
| 不支持所有 Python 内置 | 部分高级语法可能不兼容 |

---

#### P1#7 `@micropython.viper` 装饰器

**判断标准**：方法以整数运算为主（位操作、累加、数组遍历计数），且满足以下所有条件：
- 无浮点运算（viper 对浮点无提速效果）
- 无默认参数（viper 编译器丢弃默认参数信息）
- 无生成器
- 计算量大（循环 > 1000 次效果才显著）

**提速效果**：整数运算最高 58 倍，大数组遍历约 23 倍。

```python
@micropython.viper
def _calc_checksum(self, data: bytearray) -> int:
    """
    计算数据校验和
    Args:
        data (bytearray): 数据缓冲区
    Returns:
        int: 校验和（低 8 位）
    Notes:
        - ISR-safe: 否
        - viper 优化：整数运算约 58 倍提速
        - 溢出风险：viper 使用 32 位机器字，运算以 2^32 取模；
          数据长度超过 2^24（16MB）时累加可能溢出，已用 & 0xFF 截断保证结果正确
    """
    buf = ptr8(data)
    total: int = 0
    n: int = len(data)
    for i in range(n):
        total += buf[i]
    return total & 0xFF
```

**viper 的限制（必须检查，逐项确认）：**

| 限制 | 说明 | 处理方式 |
|---|---|---|
| 不支持默认参数 | `def f(a: int = 0)` 调用 `f()` 会报 TypeError | 改为显式传参 |
| 浮点运算无优化 | 浮点运算仅约提速 15%，不值得改 | 浮点方法不加 `@viper` |
| 32 位整数溢出 | 32 位以 2^32 取模，大计算量会截断 | 分析最大值范围，在 docstring 中标注 |
| 不支持生成器 | 函数内不能有 `yield` | 改写为普通返回 |
| 类型需显式标注 | 参数和局部变量需标注 `int`/`uint` | 用 `: int` 标注 |
| ptr 转换放循环外 | 循环内做 `ptr8(buf)` 每次耗时几微秒，1万次循环累计 5 倍性能损失 | 转换语句必须在循环前 |

**viper 类型对照表：**

| 类型 | 说明 | 使用场景 |
|---|---|---|
| `int` | 有符号 32 位整数 | 普通整数运算 |
| `uint` | 无符号 32 位整数 | 位操作、地址计算 |
| `ptr8` | 字节指针 | 访问 `bytearray`、`bytes` |
| `ptr16` | 16 位整数指针 | 访问 `array('H')` |
| `ptr32` | 32 位整数指针 | 直接访问寄存器地址 |

---

#### P1#8 整数替代浮点

**判断标准**：循环内有浮点运算，且目标芯片无 FPU（RP2040、ESP8266 等无 FPU 芯片浮点运算极慢）。

**提速效果**：约 57% 提速（有 FPU 的芯片如 ESP32-S3 效果不明显）。

**错误写法（禁止，循环内浮点）：**
```python
def read_voltage(self) -> list:
    results = []
    for i in range(100):
        raw = self._read_raw(i)
        # 循环内浮点转换，每次触发浮点运算
        voltage = raw / 65535.0 * 3.3
        results.append(voltage)
    return results
```

**正确写法：**
```python
def read_voltage(self) -> list:
    # 循环内只做整数运算，循环外一次性转换
    raw_data = []
    for i in range(100):
        raw_data.append(self._read_raw(i))
    # 非性能关键路径再做浮点转换
    return [raw / 65535.0 * 3.3 for raw in raw_data]
```

**规则细节：**
- 仅对循环内的浮点运算优化，单次调用的浮点转换无需改写
- 有 FPU 的芯片（ESP32-S3、STM32F4 等）不需要此优化

---

### P2 — 可选

#### P2#9 `viper ptr8/ptr16/ptr32` 指针访问

**判断标准**：有对 `bytearray` 的大循环遍历（> 1000 次），普通 `buf[i]` 访问需经过边界检查和对象属性查找。

**提速效果**：约 23 倍（`ptr8` 直接计算内存地址，无任何额外开销）。

**关键规则：指针转换必须放在循环外**
```python
# 错误：循环内重复转换（每次耗时几微秒，1万次循环累计慢 5 倍）
@micropython.viper
def bad_fill(self, ba) -> None:
    for i in range(10000):
        buf = ptr8(ba)    # 错误：每次循环都转换
        buf[i] = i % 256

# 正确：循环外一次转换
@micropython.viper
def fill_buffer(self, src, dst) -> None:
    """
    填充缓冲区
    Notes:
        - ISR-safe: 否
        - viper ptr8 优化：约 23 倍提速；ptr 转换在循环外执行
    """
    # 一次性转换，放在循环外
    s = ptr8(src)
    d = ptr8(dst)
    n: int = len(src)
    for i in range(n):
        d[i] = s[i]
```

---

#### P2#10 SIO 寄存器直写 GPIO

**判断标准**：有高频 GPIO 翻转操作（> 1000 次/秒），且目标平台为 RP2040。

**提速效果**：约 48% 提速（跳过 `machine.Pin` 硬件抽象层）。

**⚠️ 平台限制：仅 RP2040 可用**

```python
from machine import mem32
from micropython import const

# RP2040 SIO 模块寄存器地址（RP2040 专属，其他平台不可用）
_SIO_BASE     = const(0xD0000000)
_GPIO_OUT_SET = const(0xD0000014)
_GPIO_OUT_CLR = const(0xD0000018)

class GPIODriver:
    def __init__(self, pin_num: int) -> None:
        self._mask = 1 << pin_num
        # 设置为输出模式
        mem32[_SIO_BASE + 0x024] = self._mask

    def fast_toggle(self, count: int) -> None:
        """
        高频 GPIO 翻转
        Notes:
            - ISR-safe: 否
            - RP2040 专属，其他平台不可用
            - SIO 寄存器直写，约比 machine.Pin 快 48%
        """
        # 缓存到局部变量，避免循环内全局查找
        set_reg = _GPIO_OUT_SET
        clr_reg = _GPIO_OUT_CLR
        mask = self._mask
        for _ in range(count):
            mem32[set_reg] = mask
            mem32[clr_reg] = mask
```

---

#### P2#11 `array` 替代 `list`

**判断标准**：有存储大量同类型数值的列表（如 ADC 采样、传感器批量读数），`list` 存储对象引用（内存不连续），动态增长触发堆分配。

```python
import array

class SensorDriver:
    def __init__(self, ...) -> None:
        # 用 array 替代 list，连续内存，预分配，无动态增长
        # 'h' = signed short (2 bytes), 'i' = signed int (4 bytes),
        # 'f' = float (4 bytes), 'B' = unsigned byte (1 byte)
        self._samples = array.array('h', [0] * 100)

    def batch_sample(self) -> array.array:
        # 复用预分配的 array，不创建新对象
        for i in range(100):
            self._samples[i] = self._read_raw()
        return self._samples
```

**array 类型码参考：**

| 类型码 | C 类型 | 字节数 | 使用场景 |
|---|---|---|---|
| `'B'` | unsigned char | 1 | 字节数据、寄存器值 |
| `'h'` | signed short | 2 | ADC 原始值、有符号 16 位 |
| `'H'` | unsigned short | 2 | 无符号 16 位 |
| `'i'` | signed int | 4 | 有符号 32 位 |
| `'f'` | float | 4 | 浮点数据（已转换后存储） |

---

## 优化效果参考（判断是否值得改写）

| 优化手段 | 典型场景 | 提速倍数 | 改写成本 |
|---|---|---|---|
| `@viper` 整数运算 | 100 万次累加 | **~58 倍** | 中（需类型标注） |
| `viper ptr8` 指针访问 | 1 万次 bytearray 遍历 | **~23 倍** | 中 |
| ptr 转换移到循环外 | 1 万次指针访问 | **~5 倍** | 低 |
| 整数替代浮点 | 100 次 ADC 采集 | **~57%** | 低 |
| SIO 寄存器直写 | 1000 次 GPIO 翻转 | **~48%** | 高（平台限制） |
| `memoryview` 替代切片 | 大缓冲区切片传递 | ~20% | 低 |
| 缓存对象引用 | 大循环内属性访问 | ~5-20% | 低 |
| 预分配缓冲区 | I2C/SPI 读写 | 消除 GC 抖动 | 低 |

---

## 输出格式

1. 输出完整优化后的 Python 文件内容（代码块预览）。
2. 附简短说明表：
   - **P0 执行情况**：列出全部 4 项，标注"已执行"或"不适用（原因）"
   - **P1 执行情况**：列出实际执行的 P1 项及判断依据（为何适用）
   - **P2 执行情况**：列出实际执行的 P2 项及判断依据
3. 询问用户："确认写入原文件吗？"，用户确认后将内容覆盖写入原文件。

---

## 完整规范参考

[性能优化指南（本地）](../MicroPython_Performance_Optimization_Guide.md)

[完整驱动规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-opt-driver/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-opt-driver/SKILL.md && git commit -m "skill(upy-opt-driver): <规则描述>"`
