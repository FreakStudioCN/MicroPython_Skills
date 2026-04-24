---
name: upy-gen-main
description: Use this skill when the user wants to generate a new main.py test file from scratch for a MicroPython driver. Invoke when user says things like "generate main.py", "生成测试文件", "从零生成main.py", "帮我写测试文件", or provides a driver .py file and asks to create a test program.
---

# MicroPython 测试文件生成 Skill

## 角色定位

你是 GraftSense MicroPython 测试文件生成助手。给定一个驱动 `.py` 文件，分析其所有公共 API，从 0 生成符合 GraftSense 规范的完整 `main.py` 测试文件。

## 执行步骤

1. 读取用户指定的驱动 `.py` 文件
2. 分析驱动：提取所有公共方法、属性、常量、构造参数、通信接口类型
3. 按芯片功能维度分类 API（见下方维度表）
4. 按全量覆盖原则生成测试代码
5. 输出完整 `main.py` 文件

## API 全量覆盖原则

### 功能维度分类

| 芯片类型 | 需覆盖的功能维度 |
|---|---|
| 传感器类 | 基础状态查询、核心数据采集、参数配置、模式切换、校准补偿 |
| 电机驱动类 | 硬件初始化、动作控制、状态读取、复位/休眠 |
| 通信模块类 | 网络/协议配置、数据收发、状态查询、功耗控制 |
| 存储芯片类 | 数据读写、地址配置、擦除/复位 |
| GPIO/总线扩展类 | 引脚配置、电平读写、中断配置 |

### 三类场景必须覆盖

| 场景类型 | 要求 |
|---|---|
| 正常参数场景 | 默认/常用参数下的基础调用 |
| 边界参数场景 | 硬件极限参数（最大值、最小值） |
| 异常参数场景 | 非法参数（超出范围、错误类型），验证异常是否正确抛出 |

### API 特性处理方式

| API 特性 | 代码处理方式 |
|---|---|
| 低频核心 API | 保留自动执行，主循环中定期调用 |
| 高频更新 API | 保留函数定义，注释自动调用，加注释说明可 REPL 手动调用 |
| 模式切换 API | 保留调用代码，注释自动执行，加注释说明可 REPL 手动触发 |
| 批量操作 API | 封装为独立函数，供 REPL 一键调用 |

## 生成内容规范

### 必须包含（全部）

| # | 内容 | 说明 |
|---|---|---|
| 1 | 文件头 7 行注释 | 含 `@File : main.py`、`@Description : 测试XXX驱动类` |
| 2 | 6 个分区标注注释 | 顺序正确 |
| 3 | `time.sleep(3)` | 初始化配置区开头 |
| 4 | `print("FreakStudio: ...")` | 说明当前测试的驱动模块 |
| 5 | 硬件对象实例化 | 在初始化配置区，根据驱动构造参数生成 |
| 6 | 所有公共 API 的调用代码 | 低频自动执行，高频/模式切换注释调用 |
| 7 | `try/except/finally` | 主程序区包裹，含 KeyboardInterrupt/OSError/Exception 三种捕获 |
| 8 | finally 资源清理 | `close()`/`deinit()`、`del`、退出提示 |
| 9 | raise/print 全英文 | 运行时字符串全部英文 |
| 10 | 行内注释中文 | 所有行内注释使用中文 |

### 关键规范摘要

**文件头格式**
```python
# Python env   : MicroPython v1.23.0
# -*- coding: utf-8 -*-
# @Time    : YYYY/MM/DD
# @Author  : FreakStudio
# @File    : main.py
# @Description : 测试XXX驱动类的代码
# @License : CC BY-NC 4.0
```

**全局变量区**（只允许简单赋值，禁止实例化）
```python
# ======================================== 全局变量 ============================================
last_print_time = time.ticks_ms()
print_interval = 2000   # 打印间隔（ms）
```

**功能函数区示例**（高频/模式切换函数）
```python
# ======================================== 功能函数 ============================================
def print_realtime_data():
    """打印实时高频数据（高频，默认注释调用，可REPL手动调用）"""
    data = device.read_raw()
    print("Raw data: %s" % str(data))

def switch_to_sleep_mode():
    """切换到休眠模式（模式切换，默认注释调用，可REPL手动触发）"""
    device.sleep()
    print("Device entered sleep mode")
```

**主程序区示例**
```python
# ========================================  主程序  ===========================================
try:
    while True:
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, last_print_time) >= print_interval:
            # 低频查询：保留自动执行
            success, value = device.read_value()
            if success:
                print("Value: %s" % str(value))
            else:
                print("Read failed")
            last_print_time = current_time
        # print_realtime_data()    # 高频函数，注释默认执行，可REPL手动调用
        # switch_to_sleep_mode()   # 模式切换，注释默认执行，可REPL手动触发
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

直接输出完整的 `main.py` 文件内容，使用代码块包裹。文件末尾附简短说明：列出覆盖了哪些 API、哪些设为了自动执行、哪些注释为手动调用及原因。

---

## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考同仓库中的 `upy_driver_dev_spec_summary.md`，或在线查看：

[upy_driver_dev_spec_summary.md](../upy_driver_dev_spec_summary.md)


## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)
