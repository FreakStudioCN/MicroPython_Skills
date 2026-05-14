---
name: upy-deploy-test
description: Use this skill after upy-norm-pkg completes to deploy normalized driver files to a MicroPython device and validate by running main.py. Invoke when user says things like "烧录测试", "deploy and test", "上传并运行", "验证设备", or after norm-pkg asks to proceed with device testing.
---

# MicroPython 设备部署与验证 Skill

## 角色定位

你是 GraftSense MicroPython 设备部署助手。给定一个已规范化的驱动包目录，将驱动文件和测试文件上传到 MicroPython 设备，运行 main.py，读取输出并验证功能是否正常。

## 执行步骤

### 第 0 步：确认 COM 端口

询问用户：
```
请确认当前测试 MCU 连接的 COM 端口（如 COM3、COM75）：
```

若用户不确定，执行以下命令列出可用端口：
```bash
mpremote connect list
```
输出结果供用户参考，等待用户确认端口号后继续。

### 第 1 步：扫描待上传文件

扫描目标目录（upy-norm-pkg 输出的 `code/` 子目录，若无则扫描驱动包根目录），列出所有待上传文件：
- 所有 `.py` 文件（驱动文件 + main.py）
- 子包目录（含 `__init__.py` 的子目录，递归上传）

输出扫描结果：
```
待上传文件（共 N 个）：
  driver.py
  main.py
  subpkg/  （子目录，将递归上传）
目标设备：<COM端口>
```

询问用户："确认上传以上文件吗？"

### 第 2 步：上传文件

对每个文件执行上传，使用 `resume` 避免软复位：

**单个文件：**
```bash
mpremote connect <COM> resume fs cp <local_file> :<remote_file>
```

**子目录（递归）：**
```bash
mpremote connect <COM> resume fs cp -r <local_dir>/ :<remote_dir>/
```

**中间件库注意**：若驱动为中间件库（含子包依赖目录），先上传子包目录，再上传驱动文件，最后上传 main.py。

上传每个文件后打印进度：
```
[1/N] 上传 driver.py ... 完成
[2/N] 上传 main.py ... 完成
```

若上传失败（端口占用、设备未连接等），输出错误原因并提示用户检查连接后重试。

### 第 3 步：验证文件完整性

上传完成后，列出设备根目录文件，确认所有文件已存在：
```bash
mpremote connect <COM> resume fs ls :
```

与待上传列表对比，若有缺失文件，提示用户并询问是否重新上传缺失文件。

### 第 4 步：运行 main.py 并读取输出

执行 main.py 并捕获输出：
```bash
mpremote connect <COM> resume run main.py
```

**中间件库注意**：若 main.py 使用 `asyncio.run()`，改用：
```bash
mpremote connect <COM> resume exec "exec(open('main.py').read())"
```

持续读取输出，直到：
- 程序正常退出（`Program exited` 出现）
- 用户按 Ctrl+C 中断
- 超时（默认 120 秒，可由用户调整）

### 第 5 步：输出分析与验证

分析捕获的输出，判断测试结果：

**成功标志：**
- 出现 `FreakStudio: ...` 初始化打印
- 无 `Traceback` 或 `Error` 字样
- 出现预期的数据输出或功能确认信息

**失败标志：**
- `Traceback (most recent call last)` — 运行时异常
- `ImportError` — 模块未找到（文件未上传或路径错误）
- `OSError` — 硬件通信失败（接线问题或设备未响应）
- `RuntimeError` — 初始化失败（I2C 扫描无设备、WiFi 连接失败等）

输出验证报告：
```
验证结果：✓ 通过 / ✗ 失败

输出摘要：
  初始化：✓ FreakStudio 打印正常
  功能测试：✓ / ✗ <具体描述>
  异常：无 / <异常类型和位置>
```

若失败，分析错误原因并给出修复建议：
- `ImportError: <module>` → 检查文件是否上传、子包目录是否完整
- `OSError: -110` → I2C 通信超时，检查接线和地址
- `RuntimeError: No I2C device found` → 检查硬件连接
- `RuntimeError: WiFi connection failed` → 检查 SSID/密码占位符是否已替换

## 中断与重试

- 用户在任意步骤回复"重试"：重新执行当前步骤
- 用户回复"换端口"：返回第 0 步重新确认端口
- 用户回复"重新上传"：返回第 2 步重新上传所有文件

## 输出格式

每步开始前显示进度：`[步骤 X/5 — 操作描述]`
每步完成后给出简短状态，不等待用户确认（第 0、1 步除外）。

## mpremote 工具参考

若 mpremote 工具产生问题或不确定如何使用，请参考：
- Skill `/mpremote-device-interaction` — 设备交互、连接、运行代码
- Skill `/mpremote-file-transfer` — 文件上传下载、目录操作
- Skill `/mpremote-live-session` — 持久连接、多命令交互
- [mpremote 官方文档](https://docs.micropython.org/en/latest/reference/mpremote.html)

## 完整规范参考

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `C:/Users/Administrator/.claude/skills/upy-deploy-test/SKILL.md`
