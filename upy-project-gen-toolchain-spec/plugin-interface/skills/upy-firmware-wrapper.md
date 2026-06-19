# 固件 API Wrapper 包编写规范

> 状态：⚠ 待填写
>
> 本文件不是 skill 接口文档（无 Phase 执行流程），而是**固件 API Wrapper 包的编写规范**。
> 面向嵌入式工程师：当你发现某款 MicroPython 硬件的 API 已经在固件中用 C 实现并暴露为 Python 类/方法/函数时，
> 按本规范编写一个薄封装 .py 包上传 upypi，让整个流水线无需做任何特殊处理即可正常使用。

---

## 一、概念说明

### 问题

很多 MicroPython 硬件产品自带定制固件，C 语言实现的驱动程序已编译到固件中，
直接暴露为 Python 接口，例如：

```python
# 固件内置 C API——无需 import 任何 .py 文件即可调用
sht30 = SHT30(i2c)
temp, hum = sht30.measure()
```

当前流水线的驱动搜索（upy-analyze → upy-pkg-guide）只查 upypi / GitHub 的 `.py` 驱动包。
固件内置 API 不在 upypi 中 → 被标记为"无驱动" → 走入冷硬件路径（gen-driver），
系统会试图从零生成一个新驱动——显然多余且错误。

### 方案

为每个固件内置 API 编写一个 **Wrapper 包**，上传 upypi：

- **真设备上**：`import` 到固件内置类，原封不动透传
- **PC 模拟时**：暴露 stub 类（只有 type hints + docstring），供 LLM 理解 API、生成代码、静态检查

从此流水线无需感知"API 是固件里的还是 .py 文件里的"——一律从 upypi 查，查到就用。

---

## 二、Wrapper .py 文件规范

### 2.1 核心模式：try/except 双态

```python
"""
SHT30 温湿度传感器驱动（固件 Wrapper）。

固件内置: Yes (厂商定制固件 v2.1+)
I2C 地址: 0x44
"""

# ---------- 真设备：透传固件内置类 ----------
try:
    from sht30 import SHT30 as _FirmwareSHT30

    class SHT30(_FirmwareSHT30):
        """
        SHT30 温湿度传感器。

        硬件: I2C 接口，默认地址 0x44
        精度: 温度 ±0.3°C，湿度 ±2%RH
        供电: 2.4V – 5.5V
        """
        def __init__(self, i2c, addr: int = 0x44):
            super().__init__(i2c, addr)

        def measure(self) -> tuple[float, float]:
            """
            执行一次温湿度测量。

            Returns:
                (temperature_celsius, relative_humidity_pct)

            Example:
                >>> sht30 = SHT30(i2c)
                >>> temp, hum = sht30.measure()
                >>> print(f"{temp:.1f}°C, {hum:.1f}%")
            """
            return super().measure()

        def read_temp(self) -> float:
            """只读温度 (°C)"""
            return self.measure()[0]

        def read_humidity(self) -> float:
            """只读湿度 (%RH)"""
            return self.measure()[1]

# ---------- PC 端：纯 stub（供 LLM 自动补全 + 静态检查）----------
except ImportError:

    class SHT30:
        """
        [STUB] SHT30 温湿度传感器 — 固件内置 API 的 PC 端占位类。

        仅在 PC 模拟 / IDE 自动补全时生效。
        真设备上由固件内 C 实现取代本类。
        """

        def __init__(self, i2c, addr: int = 0x44) -> None: ...
        def measure(self) -> tuple[float, float]: ...
        def read_temp(self) -> float: ...
        def read_humidity(self) -> float: ...
```

### 2.2 规范要点

| # | 规范 | 说明 |
|---|------|------|
| 1 | **类名不变** | Wrapper 类名与固件内置类名一致（此处为 `SHT30`） |
| 2 | **继承透传** | 真设备分支继承固件内置类，每个方法 `super().xxx()` 透传 |
| 3 | **stub 用 `...`** | PC stub 方法体用 `...`（Ellipsis），不要 `pass`。IDE 识别为抽象方法 |
| 4 | **完整 type hints** | 所有参数和返回值标注类型，供 LLM 生成代码时参考 |
| 5 | **完整 docstring** | 每个类和方法写 docstring，含硬件约束（电压/地址/时序）和调用示例 |
| 6 | **stub 类也写 docstring** | `__init__` 的 docstring 写接口要求（I2C/SPI/UART 等） |
| 7 | **使用 `[STUB]` 标记** | PC stub 的类级 docstring 以 `[STUB]` 开头，方便搜索区分 |
| 8 | **单文件** | 一个 wrapper 包通常只有一个 .py 文件。复杂器件可拆分为包 |

### 2.3 不实现的内容

Wrapper 包**不做**任何业务计算：
- 不实现 I2C 通信协议
- 不实现寄存器读写
- 不实现数据解析/校准算法

这些已在固件 C 代码中完成。Wrapper 只负责"声明接口 + 透传调用"。

---

## 三、包目录结构

```
sht30_firmware_wrapper/           # 包根目录
├── package.json                  # 元数据（必填）
├── sht30.py                      # Wrapper 模块（必填，与器件名一致）
├── README.md                     # 使用说明（必填）
└── example.py                    # 调用示例（推荐）
```

---

## 四、package.json 元数据

### 4.1 必填字段

```json
{
  "name": "sht30_firmware_wrapper",
  "version": "1.0.0",
  "type": "driver",
  "driver_type": "wrapper",
  "wrapper_of": "firmware_builtin",
  "chip_model": "SHT30",
  "description": "SHT30 温湿度传感器固件 API Wrapper。真设备透传固件内置 C 实现，PC 端提供 stub 供代码补全。",
  "author": "",
  "license": "MIT",
  "keywords": ["sht30", "temperature", "humidity", "i2c"],
  "upy": {
    "bus": ["i2c"],
    "i2c_addr": ["0x44"],
    "firmware": {
      "required_modules": ["sht30"],
      "min_version": "2.1.0",
      "vendor_firmware": true
    }
  }
}
```

### 4.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 包名，建议 `{chip_lower}_firmware_wrapper` |
| `version` | string | 是 | 语义版本。固件 API 不变时不升 |
| `type` | string | 是 | 固定 `"driver"` |
| `driver_type` | string | 是 | 固定 `"wrapper"`。区分于普通驱动 `"native"` |
| `wrapper_of` | string | 是 | 固定 `"firmware_builtin"` |
| `chip_model` | string | 是 | 芯片型号，与 boards.json 和 manifest 一致 |
| `description` | string | 是 | 一句话说明 |
| `author` | string | 否 | 编写者 |
| `license` | string | 是 | 建议 MIT |
| `keywords` | string[] | 是 | 用于 upypi 搜索 |
| `upy.bus` | string[] | 是 | 所需总线枚举：`i2c` / `spi` / `uart` / `gpio` / `analog` / `pwm` |
| `upy.i2c_addr` | string[] | 否 | I2C 器件时必填，列出可能地址 |
| `upy.firmware.required_modules` | string[] | 是 | 固件必须内置的模块名列表 |
| `upy.firmware.min_version` | string | 否 | 固件最低版本要求 |
| `upy.firmware.vendor_firmware` | boolean | 是 | `true` = 厂商定制固件，`false` = 标准 MPY 固件模块（如 `machine.I2C`） |

### 4.3 与普通 driver 包的区分

```
普通 driver 包（driver_type: "native" 或缺失）:
  sht30.py → 完整 Python 实现，含 I2C 寄存器读写
  package.json.upy.firmware → 不存在或为空

Wrapper 包（driver_type: "wrapper"）:
  sht30.py → 继承固件内置类 + PC stub
  package.json.upy.firmware.required_modules → 必填
```

---

## 五、与流水线的协议交互

### 5.1 消息视角

Wrapper 包**不产生任何特殊协议消息**。它被 upy-analyze → upy-pkg-guide 搜索到后，
和普通 upypi 驱动包行为完全一致：

```
analyze:  搜索到 sht30_firmware_wrapper → devices[].driver.source = "upypi"
generate: 下载 sht30.py → LLM 读 API → 生成 factory + Mock → 生成 task
deploy:   上传 sht30.py 到板子 → import 时自动走固件内置 C 实现
```

pipeline 无需知道这是个 wrapper——对流水线而言它就是个普通的 upypi driver。

### 5.2 manifest 中的体现

在 `project-manifest.json` 中，wrapper 包对应的 driver 记录建议增加：

```json
{
  "devices": [
    {
      "name": "SHT30",
      "driver": {
        "source": "upypi",
        "package_name": "sht30_firmware_wrapper",
        "version": "1.0.0",
        "driver_type": "wrapper",
        "wrapper_of": "firmware_builtin",
        "required_firmware_modules": ["sht30"],
        "vendor_firmware": true
      }
    }
  ]
}
```

| 新增字段 | 用途 |
|---------|------|
| `driver_type` | 告诉下游"这不是自己实现的驱动，是固件透传" |
| `wrapper_of` | `"firmware_builtin"` 区别于未来可能的其他 wrapper 类型 |
| `required_firmware_modules` | deploy 阶段 pre-flight 检查时会用到 |
| `vendor_firmware` | `true` 时 select-hw 阶段额外提示"需要厂商定制固件" |

### 5.3 upy-deploy pre-flight 检查

这是流水线中**唯一**需要感知 wrapper 的地方——烧录前需确认固件包含所需模块：

```
Step 0 pre-flight:
  → 读 manifest，找到所有 driver_type = "wrapper" 的器件
  → device_command: mpremote exec "help('modules')"
  → 交叉对比 required_firmware_modules
  → 缺失时 approval_request 警告用户：
     "SHT30 需要厂商定制固件（含内置 sht30 模块），当前固件未检测到该模块"
```

---

## 六、何时用 Wrapper vs 冷硬件路径 vs 普通驱动

| 情况 | 走哪条路径 | 产出 |
|------|-----------|------|
| 固件内置 C API，已有 wrapper 在 upypi 上 | 正常路径（upy-analyze → 下载使用） | 无 |
| 固件内置 C API，upypi 上无 wrapper | **嵌入式工程师按本规范编写 wrapper → upy-publish 上传 upypi** | Wrapper 包 |
| 有外部 .py 驱动包（upypi / GitHub） | 正常路径（upy-analyze → 下载使用） | 无 |
| 没有固件 API，也没有外部驱动 | 冷硬件路径（gen-driver） | 从零生成驱动 |
| 标准 MPY 模块（machine.Pin / machine.I2C / network.WLAN 等） | 无需任何包，pipeline 直接硬编码使用 | 无 |

---

## 七、完整示例

### 示例 1：I2C 传感器（有厂商定制固件）

`bme280_firmware_wrapper/bme280.py`：

```python
"""
BME280 环境传感器驱动（固件 Wrapper）。

固件内置: Yes (Bosch BME280 定制固件 v1.3+)
I2C 地址: 0x76 / 0x77
"""

try:
    from bme280 import BME280 as _FirmwareBME280

    class BME280(_FirmwareBME280):
        """BME280 温度/湿度/气压三合一传感器。"""
        def __init__(self, i2c, addr: int = 0x76):
            super().__init__(i2c, addr)

        def read_all(self) -> tuple[float, float, float]:
            """一次读取全部数据。Returns: (temp_c, humidity_pct, pressure_hpa)"""
            return super().read_all()

        def temperature(self) -> float:
            """温度 (°C)"""
            return self.read_all()[0]

        def humidity(self) -> float:
            """湿度 (%RH)"""
            return self.read_all()[1]

        def pressure(self) -> float:
            """气压 (hPa)"""
            return self.read_all()[2]

except ImportError:

    class BME280:
        """[STUB] BME280 — 固件内置 API 的 PC 端占位类。"""
        def __init__(self, i2c, addr: int = 0x76) -> None: ...
        def read_all(self) -> tuple[float, float, float]: ...
        def temperature(self) -> float: ...
        def humidity(self) -> float: ...
        def pressure(self) -> float: ...
```

### 示例 2：标准固件模块（非 vendor，以 machine.PWM 为例）

标准 MPY 固件模块（`machine`、`network`、`bluetooth` 等）**不需要** wrapper。
它们被假设在所有标准固件中存在，pipeline 直接硬编码使用。

只有当器件的 API 是**厂商定制固件**提供的私有模块时，才需要编写 wrapper。

---

## 八、与 upy-publish 的关系

嵌入式工程师编写完 wrapper 包后，使用 `upy-publish` skill 完成：

1. 生成 README.md — 从 package.json 自动填充
2. 生成 LICENSE
3. 打包为标准 upypi 目录结构
4. 上传 upypi（用户确认后）

`driver_type: "wrapper"` 的包在 publish 时，README 模板中会额外包含：

```markdown
## 固件要求

本驱动是固件内置 API 的 Wrapper，**不做任何硬件通信实现**。

- 需要的固件内置模块: `sht30`
- 固件最低版本: v2.1.0
- 固件类型: 厂商定制固件

请确认你的 MicroPython 设备已烧录包含上述模块的固件。
```

---

## 九、验收清单

嵌入式工程师提交 wrapper 包前检查：

```
[ ] try 分支正确透传固件内置类
[ ] except ImportError 分支有完整 stub 类
[ ] 所有方法有 type hints
[ ] 所有类和方法有 docstring
[ ] package.json 填写完整（尤其 upy.firmware 字段）
[ ] driver_type = "wrapper"
[ ] required_firmware_modules 正确列出
[ ] example.py 可在真设备上运行
[ ] 包已通过 upy-publish 上传 upypi
```
