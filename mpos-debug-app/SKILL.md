---
name: mpos-debug-app
description: MicroPythonOS App 调试器。帮助排查 App 运行时问题（崩溃、UI 异常、逻辑错误）。掌握桌面模拟器、mpos_controller 自动化工具、print 诊断策略、常见 LVGL 坑位。触发：用户要调试 App、排查 bug、分析运行时行为。
---

# MicroPythonOS App 调试器

## 角色定位

你是 MicroPythonOS App 调试专家。你使用桌面模拟器、mpos_controller 和诊断打印来快速定位和修复运行时问题。

## 统一项目日志

调试单个 App 时，也要把关键诊断事件登记到项目状态目录，便于后续恢复和回看：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/leeqingshui/mp_env/bin/python \
  /home/leeqingshui/MicroPython_Skills/mpos-plan-app/scripts/update_plan_state.py record \
  --repo <repo-root> \
  --fullname <fullname> \
  --skill mpos-debug-app \
  --phase debug \
  --result <partial|failed|blocked|success> \
  --artifact app_test_result=<related_result_or_log.json> \
  --next-skill <next-skill-or-null> \
  --event "<short diagnostic summary>"
```

不要把长日志全文塞进 `activity_log.jsonl`；长输出保存在 `tmp/` 下，只在 event 里记录路径和摘要。

**基础知识**：本 skill 依赖 `mpos-dev` 提供的 LVGL 编程约定（常见 bug 的根源）、C 模块 API 和代码架构。调试前请确认已理解 mpos-dev 中的：
- LVGL 编程约定（逐条检查——大多数 UI bug 是违反约定导致的）
- C 模块 API 用法（尤其是 webcam/pdm_mic 的正确调用方式）
- 全局强约束

## 桌面模拟器

桌面端运行 MicroPythonOS，秒级迭代，无需烧录设备：

```bash
# 运行桌面模拟器（30 秒超时保护）
timeout -s 9 30 ./scripts/run_desktop.sh

# 手动运行（无超时，Ctrl+C 退出）
./scripts/run_desktop.sh
```

模拟器使用 `lvgl_micropy_unix` 二进制，16MB heap，SDL 渲染。行为与设备端高度一致。

### 进程管理

```bash
# 杀掉残留进程（桌面模拟器未正常退出时）
killall lvgl_micropy_unix run_desktop.sh
```

## mpos_controller.py（自动化控制）

`scripts/mpos_controller.py`（32KB）提供 PTY/aioREPL 和串口两种后端，用于：
- 向运行中的模拟器发送键盘/触摸事件
- 截图（视觉回归测试）
- 执行 REPL 命令

```bash
# PTY 模式（桌面模拟器）
python3 scripts/mpos_controller.py --backend pty

# 串口模式（物理设备）
python3 scripts/mpos_controller.py --backend serial --port /dev/ttyUSB0
```

## 诊断策略

### print() 诊断

MicroPythonOS 的 `print()` 输出到模拟器 stdout 或串口。调试时：
1. 在可疑代码路径加 `print(">>> reached X, value =", val)`
2. 运行桌面模拟器观察输出
3. 定位问题后移除调试打印

### 临时文件

写临时数据到 `tmp/` 目录（不是 `/tmp`）：

```python
with open("tmp/debug_log.txt", "w") as f:
    f.write(str(diagnostic_data))
```

## 常见 LVGL Bug 排查清单

逐条对照 mpos-dev 的 LVGL 约定排查：

| 症状 | 常见原因 | 检查 |
|------|---------|------|
| 设备死机/卡死 | `style_t()` 后忘调 `init()` | 搜 `lv.style_t()` 下一行是否有 `.init()` |
| label 显示多余的 "Text" | 新 label 默认文本 | 创建后立即 `label.set_text("")` |
| 事件回调不触发 | 事件名写错 | 检查是 `lv.EVENT.VALUE_CHANGED` 不是 `lv.EVENT_VALUE_CHANGED` |
| flag 操作无效 | 方法名写错 | `.add_flag()` / `.remove_flag()`，不是 `.set_hidden()` / `.clear_flag()` |
| buttonmatrix 值读取异常 | `set_map()` 异步触发事件 | 加时间防抖 `time.ticks_diff(now, last_ts) < 50` |
| buttonmatrix 文本改不了 | 不存在 `set_button_text()` | 需重建 map |
| 动画不生效 | API 名写错 | `lv.anim_t.path_ease_in_out` 不是 `lv.anim_path_ease_in_out` |
| 属性赋值报错 | LVGL 对象不支持 Python 属性 | 用闭包/lambda 或平行列表代替 `obj.myattr = x` |
| 隐藏对象快照有残影 | 主题样式泄漏 | 将 image 放 container，快照 container 而非直接快照 image |
| SDL 按键"按住不放"不工作 | SDL_KEYUP 被忽略 | 用超时机制模拟长按检测 |
| OPA 透明度值无效 | 用了不存在的枚举值 | `lv.OPA` 只有 TRANSP/_10/_20/.../_100/COVER |

## 构建系统

修复代码后需要重新编译 C 模块或重新生成绑定时：

```bash
# 桌面端构建
make build-mpos-unix

# 等价于
./scripts/build_mpos.sh unix
```

如果只改了 Python 文件（`internal_filesystem/` 下的 .py），不需要重新构建，直接运行模拟器即可。

## 设备端调试

```bash
# 安装 App 到设备
./scripts/install.sh com.micropythonos.<appname>

# 安装后刷新 App 注册表
# 在设备 REPL 中执行：
import mpos.content.app_manager as am
am.AppManager().refresh_apps()

# 部署单个更新文件
python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py \
  cp internal_filesystem/lib/mpos/ui/testing.py :/lib/mpos/ui/testing.py
```

## 强约束

- **必须用 killall 杀进程，不能用 pkill -f**
- **临时文件放 tmp/，不放 /tmp**
- **桌面运行必须加 timeout 保护**：`timeout -s 9 30 ./scripts/run_desktop.sh`
- **不修改 AGENTS.md 或 ruff.toml**
- **LVGL Bug 首先对照 mpos-dev 的约定排查**
