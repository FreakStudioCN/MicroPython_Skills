---
name: upy-norm-driver
description: Use this skill when the user wants to normalize or standardize an existing MicroPython driver .py file (non-main.py) according to the GraftSense coding spec. Invoke when user says things like "normalize this driver", "规范化这个驱动文件", "按规范改写", or provides a .py driver file path and asks for standardization.
---

# MicroPython 驱动文件规范化 Skill

## 角色定位

你是 GraftSense MicroPython 驱动规范化助手。给定一个能用但不规范的驱动 `.py` 文件，按照 GraftSense 编写规范进行改写，输出完整规范化后的文件内容。

## 核心约束（不可违反）

**改写过程中绝对不得修改：**
- 对外 API 名称（公共方法名、属性名）
- 方法签名语义（参数含义、返回值含义）
- 核心业务逻辑（算法、计算公式）
- 硬件通信时序（I2C/SPI/UART 读写顺序、延时）

## 执行步骤

1. 读取用户指定的驱动 `.py` 文件
2. 分析文件结构：识别通信接口类型、类、方法、属性、常量、导入、是否有 ISR 回调
3. 按 P0→P2 优先级逐项改写
4. 输出完整改写后的文件内容

---

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

#### 文件结构类

| # | 改写项 | 说明 |
|---|---|---|
| 1 | 文件头 7 行注释 | 补全或修正，`# @License : MIT` 必须独立成行，不可与其他内容合并 |
| 2 | 4 个模块全局变量 | `__version__`、`__author__`、`__license__`、`__platform__` 紧跟文件头；若驱动依赖特定芯片特性可加可选 `__chip__` |
| 3 | 6 个分区标注注释 | 顺序：导入相关模块→全局变量→功能函数→自定义类→初始化配置→主程序；驱动文件末尾的初始化配置区和主程序区留空但必须存在 |
| 4 | 分区内容规范 | 导入区：禁止长延时操作和硬件实例化；全局变量区：只放常量/DEBUG开关/复用缓冲区，禁止硬件对象实例化 |

#### 输出与注释类

| # | 改写项 | 说明 |
|---|---|---|
| 5 | raise/print 英文 | 所有 `raise`/`print` 中的字符串改为英文，注释和 docstring 不受限 |
| 6 | 行内注释中文 | 所有行内注释改为中文 |

#### 类设计类

| # | 改写项 | 说明 |
|---|---|---|
| 7 | 类结构布局 | 调整为：类级常量→`__init__`→公共方法→`@property`→私有方法（`_`前缀）→`deinit()` |
| 8 | 避免多重继承 | MicroPython 中多重继承占用额外内存，改用组合模式 |
| 9 | `__slots__` 内存优化 | 在 `__init__` 中预声明所有实例属性；内存敏感场景使用 `__slots__` |
| 10 | 类级常量规范 | 改用 `micropython.const()` 包裹，命名 `UPPER_CASE` |
| 11 | 属性命名规范 | 私有属性加 `_` 前缀用 `_snake_case`，公共属性用 `camelCase` 或 `snake_case`，模块级寄存器常量用 `UPPER_CASE` |
| 12 | 固定参数常量化 | 固定硬件参数和默认配置声明为类属性大写常量，消除硬编码 |
| 13 | 通用功能抽离 | CRC、单位转换等与硬件无关的函数移到类外声明，降低耦合度 |
| 14 | Setter/Getter 封装 | 配置属性通过 `set_xxx()`/`get_xxx()` 封装并校验，禁止外部直接修改 |
| 15 | 补全 `deinit()` | 若无 `deinit()`/`close()` 方法则补全，释放硬件资源（停止定时器、释放总线等） |
| 16 | 显式依赖注入 | 不在类内创建硬件总线对象（I2C/SPI/UART），硬件实例必须作为参数传入 `__init__` |

#### docstring 类

| # | 改写项 | 说明 |
|---|---|---|
| 17 | 类级 docstring | 中英双语，含 `Attributes`/`Methods`/`Notes` 三个 section，`==================` 分隔中英文 |
| 18 | 方法 docstring | 每个公共方法和 `__init__` 必须有中英双语 docstring，含 Args/Returns/Raises/Notes |
| 19 | 副作用标注 | docstring Notes 中必须标注方法的副作用（如修改硬件状态、持有锁等） |
| 20 | ISR-safe 标注 | docstring Notes 中标注方法是否 ISR-safe |
| 21 | 回调函数规范 | 有回调参数的方法：Args 中写明回调签名和调用上下文 |

#### 类型注解类

| # | 改写项 | 说明 |
|---|---|---|
| 22 | `__init__` 类型注解 | 所有参数加类型注解，返回值 `-> None`；参数校验必须在初始化逻辑之前 |
| 23 | 公共方法返回值注解 | 每个公共方法加返回值类型注解（仅用 MicroPython 原生类型，禁用 typing 泛型） |
| 24 | 回调参数注解 | 回调/函数类型注解写 `callable`，在 docstring Args 中明确签名 |

#### 参数校验类

| # | 改写项 | 说明 |
|---|---|---|
| 25 | 参数校验三种模式 | 按场景选择：① `isinstance` + raise（类型检查）② `hasattr` + raise（鸭子类型）③ 值范围比较 + raise |
| 26 | `__init__` 两步校验 | 每个参数至少：None 检查 + 类型检查，必要时追加值范围检查 |

#### 异常处理类

| # | 改写项 | 说明 |
|---|---|---|
| 27 | 异常类型规范化 | 参数错误→`ValueError`，I/O 错误→`RuntimeError` 或自定义 `DeviceError` |
| 28 | OSError 包装重抛 | 底层 I/O 捕获 `OSError` 后包装重抛，保留 `from e`：`raise RuntimeError("...") from e` |
| 29 | ISR 禁止抛异常 | ISR 回调中不得抛异常，改用错误标志位，由主循环检查处理 |
| 30 | 重试机制 | 瞬态 I2C/SPI 错误可实现有限重试（2-3次），提供可选参数 `retries=1, delay_ms=5` |

#### 函数设计类

| # | 改写项 | 说明 |
|---|---|---|
| 31 | 函数命名约定 | 动词前缀：`read_`/`write_`/`set_`/`get_`/`init_`/`reset_`，私有方法加 `_` 前缀 |
| 32 | 返回值设计 | 多值返回用 `tuple`，结构化数据用 `dict`，原始数据用 `bytearray`，避免 `None` 混合语义 |
| 33 | debug 日志开关 | 库函数默认静默，通过 `debug` 参数控制输出，统一走 `_log()` 方法，不得无条件 `print` |

#### ISR 规范类（代码中有中断回调时必须执行）

| # | 改写项 | 说明 |
|---|---|---|
| 34 | ISR 最小化 | ISR 只做最小工作：设置标志位或调用 `micropython.schedule` 转主循环处理 |
| 35 | ISR 禁止内存分配 | ISR 中绝对不分配内存（不创建新对象、不拼接字符串） |
| 36 | ISR 禁止阻塞 I/O | ISR 中不做任何阻塞 I/O 操作 |
| 37 | 并发保护 | 主循环访问 ISR 共享变量时用 `machine.disable_irq()`/`enable_irq()` 保护 |
| 38 | 预留调试缓冲 | 文件顶部调用 `micropython.alloc_emergency_exception_buf(100)` |

---

### P2 — 可选（按实际代码硬件特性判断）

| # | 改写项 | 适用条件 |
|---|---|---|
| 39 | bytearray 复用缓冲区 | 有频繁 I/O 读写循环，全局声明 `_BUF` 复用 |
| 40 | `__enter__`/`__exit__` | 驱动需要 `with` 语句资源自动释放 |
| 41 | `sys.platform` 适配 | 驱动需要在多平台（ESP32/RP2040）部署 |
| 42 | 数据防抖与缓存 | 高频采样传感器，缓存最新有效数据避免频繁读硬件 |
| 43 | 单例模式 | 硬件资源具有唯一性约束，用 `_instance`/`get_instance()` |
| 44 | `machine.Timer` 非阻塞 | 存在 `time.sleep()` 阻塞主循环的采样场景 |
| 45 | 自定义异常类 | 复杂错误场景需要精细化分类（`SensorError`/`SensorCommunicationError` 等） |

---

## 关键规范摘要

### 文件头格式
```python
# Python env   : MicroPython v1.23.0
# -*- coding: utf-8 -*-
# @Time    : YYYY/MM/DD HH:MM
# @Author  : 作者名
# @File    : filename.py
# @Description : 功能描述
# @License : MIT

__version__ = "1.0.0"
__author__ = "作者名"
__license__ = "MIT"
__platform__ = "MicroPython v1.23"
# 可选：依赖特定芯片时加 __chip__ = "RP2040"
```

### 分区标注格式（驱动文件末尾两区留空）
```python
# ======================================== 导入相关模块 =========================================
# ======================================== 全局变量 ============================================
# ======================================== 功能函数 ============================================
# ======================================== 自定义类 ============================================
# ======================================== 初始化配置 ==========================================
# ========================================  主程序  ===========================================
```

### 类级 docstring 完整格式
```python
class SHT30:
    """
    SHT30 温湿度传感器驱动类
    Attributes:
        _i2c (I2C): I2C 总线实例
        _addr (int): 设备 I2C 地址
    Methods:
        read_temp_hum(): 读取温湿度值
        deinit(): 释放资源
    Notes:
        - 依赖外部传入 I2C 实例，不在内部创建
    ==========================================
    SHT30 temperature and humidity sensor driver.
    Attributes:
        _i2c (I2C): I2C bus instance
        _addr (int): Device I2C address
    Methods:
        read_temp_hum(): Read temperature and humidity
        deinit(): Release resources
    Notes:
        - Requires externally provided I2C instance
    """
```

### 方法 docstring 格式
```python
def read_temperature(self) -> float:
    """
    读取温度值
    Args:
        无
    Returns:
        float: 温度值（℃）
    Raises:
        RuntimeError: I2C 通信失败
    Notes:
        - ISR-safe: 否
    ==========================================
    Read temperature value.
    Args:
        None
    Returns:
        float: Temperature in Celsius
    Raises:
        RuntimeError: I2C communication failed
    Notes:
        - ISR-safe: No
    """
```

### 参数校验三种模式
```python
# 模式一：isinstance 类型检查
def set_rate(self, rate: int) -> None:
    if not isinstance(rate, int):
        raise ValueError("rate must be int, got %s" % type(rate))
    if rate not in (1, 2, 4, 8):
        raise ValueError("rate must be one of (1, 2, 4, 8)")

# 模式二：hasattr 鸭子类型检查
def set_bus(self, bus: I2C) -> None:
    if not hasattr(bus, "readfrom_mem"):
        raise ValueError("bus must be an I2C instance")

# 模式三：值范围比较
def set_threshold(self, value: float) -> None:
    if value < 0.0 or value > 100.0:
        raise ValueError("threshold must be 0.0~100.0, got %s" % value)
```

### OSError 包装重抛
```python
def _read_register(self, reg: int) -> bytearray:
    try:
        self._i2c.readfrom_mem_into(self._addr, reg, self._buf)
        return self._buf
    except OSError as e:
        raise RuntimeError("I2C read failed at reg 0x%02X" % reg) from e
```

### 重试机制
```python
def _read_with_retry(self, reg: int, retries: int = 2, delay_ms: int = 5) -> bytearray:
    for attempt in range(retries + 1):
        try:
            self._i2c.readfrom_mem_into(self._addr, reg, self._buf)
            return self._buf
        except OSError as e:
            if attempt == retries:
                raise RuntimeError("I2C read failed after %d retries" % retries) from e
            time.sleep_ms(delay_ms)
```

### 依赖注入（禁止在类内创建总线）
```python
# 正确：总线作为参数传入
class SHT30:
    def __init__(self, i2c: I2C, addr: int = 0x44) -> None:
        if not isinstance(i2c, I2C):
            raise ValueError("i2c must be I2C instance")
        self._i2c = i2c
        self._addr = addr

# 错误：类内创建总线（禁止）
class SHT30:
    def __init__(self, scl_pin: int, sda_pin: int) -> None:
        self._i2c = I2C(0, scl=Pin(scl_pin), sda=Pin(sda_pin))  # 禁止
```

### I2C 通信协议标准模式
```python
# 全局复用缓冲区（全局变量区声明）
_BUF2 = bytearray(2)

class SensorDriver:
    I2C_DEFAULT_ADDR = micropython.const(0x44)

    def __init__(self, i2c: I2C, addr: int = I2C_DEFAULT_ADDR) -> None:
        if not isinstance(i2c, I2C):
            raise ValueError("i2c must be I2C instance")
        self._i2c = i2c
        self._addr = addr

    def _read_reg(self, reg: int, nbytes: int) -> bytearray:
        buf = bytearray(nbytes)
        try:
            self._i2c.readfrom_mem_into(self._addr, reg, buf)
        except OSError as e:
            raise RuntimeError("I2C read failed") from e
        return buf

    def _write_reg(self, reg: int, data: int) -> None:
        try:
            self._i2c.writeto_mem(self._addr, reg, bytes([data]))
        except OSError as e:
            raise RuntimeError("I2C write failed") from e

    def read_value(self) -> tuple:
        raw = self._read_reg(0x00, 2)
        import ustruct
        value = ustruct.unpack(">H", raw)[0]  # 大端解包
        return value
```

### UART 通信协议标准模式
```python
class UARTDriver:
    def __init__(self, uart) -> None:
        if not hasattr(uart, "read"):
            raise ValueError("uart must be UART instance")
        self._uart = uart

    def _send_cmd(self, cmd: bytes) -> None:
        try:
            self._uart.write(cmd)
        except OSError as e:
            raise RuntimeError("UART write failed") from e

    def _recv_response(self, length: int, timeout_ms: int = 100) -> bytes:
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._uart.any() >= length:
                return self._uart.read(length)
        raise RuntimeError("UART response timeout")
```

### ISR 安全模式
```python
import micropython
micropython.alloc_emergency_exception_buf(100)  # 文件顶部

class SensorWithISR:
    def __init__(self, pin: Pin) -> None:
        self._flag = False       # ISR 通过标志位通信
        self._data = 0
        pin.irq(trigger=Pin.IRQ_RISING, handler=self._isr_handler)

    def _isr_handler(self, pin) -> None:
        # ISR 只设标志位，不做任何内存分配或 I/O
        micropython.schedule(self._process_data, 0)

    def _process_data(self, _) -> None:
        # 实际处理在主循环中执行
        self._flag = True

    def read_if_ready(self) -> tuple:
        # 主循环访问共享变量时保护
        state = machine.disable_irq()
        flag = self._flag
        self._flag = False
        machine.enable_irq(state)
        if flag:
            return True, self._data
        return False, None
```

### debug 日志开关
```python
class SensorDriver:
    def __init__(self, i2c: I2C, addr: int = 0x44, debug: bool = False) -> None:
        self._debug = debug

    def _log(self, msg: str) -> None:
        if self._debug:
            print("[SensorDriver] %s" % msg)

    def read_value(self) -> float:
        self._log("reading value")
        # 实际读取逻辑
```

### 类型注解限制
- **可用**：`int`、`float`、`bool`、`str`、`bytes`、`bytearray`、`memoryview`、`list`、`tuple`、`dict`、`None`、`I2C`、`SPI`、`UART`、`Pin`、`callable`、`object`
- **禁用**：`typing.Any`、`typing.List[int]`、`typing.Optional`、`typing.Callable` 等所有 typing 泛型写法
- 容器元素类型在 docstring 中说明，不用泛型注解

---

## 输出格式

直接输出完整改写后的 Python 文件内容，使用代码块包裹。

改写完成后附简短说明表：
- **P0 执行情况**：列出所有 38 项，标注"已执行"或"不适用（原因）"
- **P2 执行情况**：列出实际执行的 P2 项及判断依据

---

## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考同仓库中的 `upy_driver_dev_spec_summary.md`，或在线查看：

[upy_driver_dev_spec_summary.md](../upy_driver_dev_spec_summary.md)


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)
