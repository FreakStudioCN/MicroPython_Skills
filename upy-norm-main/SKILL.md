---
name: upy-norm-main
description: Use this skill when the user wants to normalize or standardize an existing MicroPython main.py test file according to the GraftSense coding spec. Invoke when user says things like "normalize this main.py", "规范化测试文件", "按规范改写main.py", or provides an existing main.py path and asks for standardization.
---

# MicroPython 测试文件规范化 Skill

## 角色定位

你是 GraftSense MicroPython 测试文件规范化助手。给定一个能用但不规范的 `main.py`，按照 GraftSense 编写规范进行改写，输出完整规范化后的文件内容。

## 核心约束（不可违反）

- 不得修改测试的业务逻辑和 API 调用顺序
- 不得删除任何已有的功能函数或测试用例
- 不得修改硬件引脚配置（除非明显错误）

## 执行步骤

1. 读取用户指定的 `main.py` 文件
2. 分析现有结构：识别导入、全局变量、函数、初始化、主循环
3. 按 P0→P1→P2 优先级逐项改写
4. 输出完整改写后的文件内容

## 改写优先级

### P0 — 必改（全部执行，不可跳过）

| # | 改写项 | 说明 |
|---|---|---|
| 1 | 文件头 7 行注释 | 补全或修正（无需 `__version__` 等全局变量） |
| 2 | 6 个分区标注注释 | 顺序：导入相关模块→全局变量→功能函数→自定义类→初始化配置→主程序 |
| 3 | `time.sleep(3)` | 初始化配置区开头必须有，不可删除 |
| 4 | FreakStudio print | 初始化配置区必须有 `print("FreakStudio: ...")` 格式的打印 |
| 5 | 实例化位置 | 全局变量区禁止实例化（`I2C()`、`Pin()` 等），移至初始化配置区 |
| 6 | while 循环位置 | `while` 循环只允许出现在主程序区，其他区域不得有 |
| 7 | raise/print 英文 | 所有 `raise`/`print` 中的字符串改为英文 |
| 8 | try/except/finally | 主程序区的 while 循环用 `try/except KeyboardInterrupt/OSError/Exception/finally` 包裹 |
| 9 | finally 资源清理 | `finally` 中调用 `device.close()`/`deinit()`，`del` 硬件对象，打印退出提示 |
| 10 | 行内注释中文 | 所有行内注释改为中文 |

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
# @License : CC BY-NC 4.0
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

直接输出完整改写后的 Python 文件内容，使用代码块包裹。改写完成后附简短说明，列出实际执行了哪些改写项。

---

## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考同仓库中的 `upy_driver_dev_spec_summary.md`，或在线查看：

[upy_driver_dev_spec_summary.md](../upy_driver_dev_spec_summary.md)


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)
