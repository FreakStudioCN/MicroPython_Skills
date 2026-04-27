---
name: upy-opt-driver
description: Use this skill when the user wants to optimize the performance of an existing MicroPython driver .py file according to the GraftSense performance optimization guide. Invoke when user says things like "优化驱动性能", "optimize driver", "加速驱动", "对驱动做性能优化", or provides a driver .py file path and asks for performance improvement.
---

# MicroPython 驱动性能优化 Skill

## 角色定位

你是 GraftSense MicroPython 驱动性能优化助手。给定一个已规范化的驱动 `.py` 文件，按照 GraftSense 性能优化指南逐项检查并改写，输出完整优化后的文件内容。

## 核心约束（不可违反）

- 不得修改对外 API 名称（公共方法名、属性名）
- 不得修改方法签名语义（参数含义、返回值含义）
- 不得修改硬件通信时序（I2C/SPI/UART 读写顺序、延时）
- `@viper` 改写必须在 docstring Notes 中标注整数溢出风险
- SIO 寄存器操作必须标注"RP2040 专属"

## 执行步骤

1. 读取用户指定的驱动 `.py` 文件；**必须重新读取文件完整内容，不得使用会话缓存**
2. 分析文件：识别缓冲区分配方式、循环结构、常量声明、计算密集型方法、浮点运算
3. 按 P0→P1→P2 优先级逐项检查并改写
4. 输出完整优化后的文件内容

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

| # | 优化项 | 说明 |
|---|---|---|
| 1 | 预分配缓冲区 | I2C/SPI/UART 读写缓冲区改为全局 `bytearray` 预分配，用 `readinto()` 替代 `read()`；缓冲区命名为 `_BUFn`（n 为字节数），声明在全局变量区 |
| 2 | `memoryview` 替代切片 | 传递大缓冲区切片时改用 `memoryview`，避免堆分配；适用于缓冲区 > 64 字节的切片传递场景 |
| 3 | 缓存对象引用 | 循环内频繁访问的 `self.xxx` 或嵌套属性缓存到局部变量，减少属性查找开销 |
| 4 | `const()` 常量 | 所有寄存器地址、固定参数、位掩码改用 `micropython.const()` 包裹，命名 `UPPER_CASE` |

### P1 — 尽量改

| # | 优化项 | 说明 | 适用条件 |
|---|---|---|---|
| 5 | 手动 GC 控制 | 性能关键循环前加 `gc.collect()`，避免随机触发 | 方法内有大量动态对象创建 |
| 6 | `@micropython.native` | 对计算密集型方法加 native 装饰器（约 2 倍提速） | 无生成器、无关键字参数的方法 |
| 7 | `@micropython.viper` | 整数密集型方法加 viper 装饰器（最高 58 倍提速）；在 docstring Notes 中标注"viper 优化：整数溢出风险（32 位截断）" | 纯整数运算方法，无浮点，无默认参数 |
| 8 | 整数替代浮点 | 循环内用整数运算（如 `value * 100` 代替 `value * 1.0`），循环外再转浮点 | 有浮点运算且目标芯片无 FPU（如 RP2040） |

### P2 — 可选

| # | 优化项 | 说明 | 适用条件 |
|---|---|---|---|
| 9 | `viper ptr8/ptr16/ptr32` | 大数组遍历改用指针直接访问（约 23 倍提速）；指针转换必须放在循环外 | 有 > 1000 次 bytearray 遍历的循环 |
| 10 | SIO 寄存器直写 | 高频 GPIO 操作绕过 `machine.Pin` 直接写 SIO 寄存器；必须在注释中标注"RP2040 专属" | RP2040 平台，高频 GPIO 翻转场景 |
| 11 | `array` 替代 `list` | 存储同类型数值改用 `array.array`，连续内存，无动态增长 | 有大量同类型数值存储的列表 |

## 关键规范摘要

### 预分配缓冲区（P0#1）
```python
# 全局变量区声明复用缓冲区
_BUF2 = bytearray(2)
_BUF6 = bytearray(6)

class SensorDriver:
    def _read_reg(self, reg: int, nbytes: int) -> bytearray:
        # 使用预分配缓冲区，避免每次分配新对象
        self._i2c.readfrom_mem_into(self._addr, reg, _BUF2)
        return _BUF2
```

### 缓存对象引用（P0#3）
```python
def process_data(self) -> None:
    # 缓存频繁访问的属性到局部变量
    buf = self._buf
    addr = self._addr
    for i in range(100):
        buf[i] = addr + i
```

### viper 整数优化（P1#7）
```python
@micropython.viper
def _calc_checksum(self, data) -> int:
    """
    计算校验和
    ...
    Notes:
        - ISR-safe: 否
        - viper 优化：整数溢出风险（32 位截断，数据长度需 < 2^27）
    """
    buf = ptr8(data)
    total: int = 0
    for i in range(len(data)):
        total += buf[i]
    return total & 0xFF
```

### ptr8 指针访问（P2#9）
```python
@micropython.viper
def _fill_buffer(self, src, dst) -> None:
    # 指针转换放在循环外（避免循环内重复转换的 5 倍性能损失）
    s = ptr8(src)
    d = ptr8(dst)
    for i in range(len(src)):
        d[i] = s[i]
```

## 输出格式

1. 输出完整优化后的 Python 文件内容（代码块预览）。
2. 附简短说明表：
   - **P0 执行情况**：列出所有 4 项，标注"已执行"或"不适用（原因）"
   - **P1 执行情况**：列出实际执行的 P1 项及判断依据
   - **P2 执行情况**：列出实际执行的 P2 项及判断依据
3. 询问用户："确认写入原文件吗？"，用户确认后将内容覆盖写入原文件。

## 完整规范参考

[性能优化指南](../MicroPython_Performance_Optimization_Guide.md)

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
