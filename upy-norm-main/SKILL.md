---
name: upy-norm-main
description: Use this skill when the user wants to normalize or standardize an existing MicroPython main.py test file according to the GraftSense coding spec. Invoke when user says things like "normalize this main.py", "规范化测试文件", "按规范改写main.py", or provides an existing main.py path and asks for standardization.
---

# MicroPython 测试文件规范化 Skill

## 角色定位

你是 GraftSense MicroPython 测试文件规范化助手。给定一个能用但不规范的 `main.py`，按照 GraftSense 编写规范进行改写，输出完整规范化后的文件内容。

## 类型判断（执行任何步骤前必须先完成）

读取对应驱动文件后，立即判断类型，后续步骤按类型走对应分支：

| 判断条件 | 类型 |
|---|---|
| 驱动位于 `middleware/` 子目录，或导入了 `network`/`urequests`/`AsyncWebsocketClient`/`asyncio` 且无 I2C/SPI/UART 硬件总线操作 | **中间件库** |
| 其他情况 | **硬件驱动** |

**中间件库跳过 #11 I2C 扫描+ID 验证，替换为以下三条规则：**
- **#11a** 功能函数区定义 `connect_wifi()` 函数，初始化配置区调用并打印 IP 地址
- **#11b** 全局变量区声明 `APP_ID`/`ACCESS_TOKEN` 等凭证常量（`UPPER_CASE`），不得硬编码在实例化语句中
- **#11c** 主程序区用 `tests = [...]` 列表驱动多场景测试，替代 `while True` 轮询结构；使用 `asyncio.run()` 作为入口

**中间件库敏感数据替换规则（#11d）**：
扫描文件中所有真实凭证值，统一替换为占位符，包括：
| 数据类型 | 替换为 |
|---|---|
| WiFi SSID | `"your_wifi_ssid"` |
| WiFi 密码 | `"your_wifi_password"` |
| App ID / appid | `"your_app_id"` |
| Access Token / token | `"your_access_token"` |
| API Key | `"your_api_key"` |
| 其他凭证字段 | `"your_<字段名>"` |

替换后在全局变量区对应常量上方加注释：`# 请替换为你的实际 XXX`

## 核心约束（不可违反）

- 不得修改测试的业务逻辑和 API 调用顺序
- 不得删除任何已有的功能函数或测试用例
- 不得修改硬件引脚配置（除非明显错误）

## 执行步骤

1. 读取用户指定的 `main.py` 文件；**必须重新读取文件的完整内容，不得使用会话缓存或跳过读取步骤**
2. 分析现有结构：识别导入、全局变量、函数、初始化、主循环
3. 按 P0→P1→P2 优先级逐项改写
4. 输出完整改写后的文件内容

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

| # | 改写项 | 说明 |
|---|---|---|
| 1 | 文件头 7 行注释 | 补全或修正（无需 `__version__` 等全局变量）；`@Author` 从原文件读取并沿用，若无则提示用户填写，不得使用占位符 |
| 2 | 6 个分区标注注释 | 顺序：导入相关模块→全局变量→功能函数→自定义类→初始化配置→主程序 |
| 3 | `time.sleep(3)` | 初始化配置区开头必须有，不可删除 |
| 4 | FreakStudio print | 初始化配置区必须有 `print("FreakStudio: ...")` 格式的打印 |
| 5 | 实例化位置 | 全局变量区禁止实例化（`I2C()`、`Pin()` 等），移至初始化配置区 |
| 6 | while 循环位置 | `while` 循环只允许出现在主程序区，其他区域不得有 |
| 7 | raise/print 英文 | 所有 `raise`/`print` 中的字符串改为英文 |
| 8 | try/except/finally | 主程序区的 while 循环用 `try/except KeyboardInterrupt/OSError/Exception/finally` 包裹 |
| 9 | finally 资源清理 | `finally` 中调用 `device.close()`/`deinit()`，`del` 硬件对象，打印退出提示 |
| 10 | 行内注释中文 | 所有行内注释改为中文；**注释必须写在对应代码行的上方（独立注释行），禁止写在代码行末尾（行尾 `#` 注释）** |
| 11 | I2C 设备扫描 + ID 验证 | 若驱动使用 I2C，初始化配置区必须包含完整扫描逻辑：① `i2c.scan()` 扫描总线，若列表为空则 `raise RuntimeError("No I2C device found")`；② 遍历设备列表，找到目标地址则记录，未找到则 `raise RuntimeError("Device not found at expected address")`；③ 读取芯片 ID 寄存器与期望值比对，打印 "Device found" 或 "Device not found"；设备 ID 寄存器地址、期望值声明为全局变量区常量（`UPPER_CASE`）；I2C 扫描所需的额外 `import` 必须放在导入区，不得在初始化配置区内 `import` |
| 11a | 中间件库：WiFi 连接函数 | 若驱动为中间件库（见 upy-norm-driver 类型判断规则），跳过 #11 I2C 扫描，替换为：功能函数区定义 `connect_wifi()` 函数，初始化配置区调用并打印 IP 地址 |
| 11b | 中间件库：凭证配置区 | 全局变量区声明 `APP_ID`/`ACCESS_TOKEN` 等凭证常量（`UPPER_CASE`），不得硬编码在实例化语句中 |
| 11c | 中间件库：场景列表结构 | 主程序区用 `tests = [...]` 列表驱动多场景测试，替代 `while True` 轮询结构；使用 `asyncio.run()` 作为入口 |

### P1 — 尽量改

| # | 改写项 | 说明 |
|---|---|---|
| 11 | 高频函数处理 | 高频更新/模式切换函数保留定义，注释掉主程序中的自动调用，加注释说明可 REPL 手动调用 |
| 12 | 三类测试场景覆盖检查 | 检查已有测试代码是否覆盖正常参数场景、边界参数场景（硬件极限值）、异常参数场景（非法值验证异常是否抛出），缺少的场景应补全调用代码 |
| 13 | 功能函数 docstring | 每个功能函数加简短中文 docstring |
| 14 | 全局变量命名 | 改为 `snake_case`，如 `print_interval`、`last_print_time` |

### P2 — 可选

| # | 改写项 | 适用条件 |
|---|---|---|
| 14 | 批量操作封装 | 有多个同类 API 调用时，封装为批量测试函数供 REPL 一键调用 |

## 关键规范摘要

### 文件头格式（main.py 版）
```python
# Python env   : MicroPython v1.23.0
# -*- coding: utf-8 -*-
# @Time    : YYYY/MM/DD HH:MM
# @Author  : 作者名
# @File    : main.py
# @Description : 测试XXX驱动类的代码
# @License : MIT
```

### 初始化配置区标准结构
```python
# ======================================== 初始化配置 ==========================================
time.sleep(3)
print("FreakStudio: Using XXX ...")
# 硬件对象实例化
uart = UART(0, baudrate=115200, tx=Pin(16), rx=Pin(17), timeout=0)
device = DriverClass(uart)
```

### 主程序区标准结构
```python
# ========================================  主程序  ===========================================
try:
    while True:
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, last_print_time) >= print_interval:
            # 低频查询保留自动执行
            ...
            last_print_time = current_time
        # print_high_freq_data()  # 高频函数，注释默认执行，可REPL手动调用
        time.sleep_ms(10)

except KeyboardInterrupt:
    print("Program interrupted by user")
except OSError as e:
    print("Hardware communication error: %s" % str(e))
except Exception as e:
    print("Unknown error: %s" % str(e))
finally:
    print("Cleaning up resources...")
    device.close()
    del device
    print("Program exited")
```

## 输出格式

1. 输出完整改写后的 Python 文件内容（代码块预览）。
2. 附简短说明，列出实际执行了哪些改写项。
3. 询问用户："确认写入原文件吗？"，用户确认后将内容覆盖写入原文件。


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-norm-main/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-norm-main/SKILL.md && git commit -m "skill(upy-norm-main): <规则描述>"`
