---
name: upy-deploy
description: 第五步——一键烧录运行。上传 firmware/ 到设备、软复位、持久会话采集输出、读取设备端日志、初判通过/失败。触发：upy-generate 完成后自动进入。
---

# 设备部署与运行 Skill

## 角色定位

给定 `project-manifest.json`（phase: generate），将 `firmware/` 上传到 MicroPython 设备、运行、采集输出、初判结果。**不做错误修复（那是 upy-autofix 的职责）。**

---

## 前置检查

```bash
python --version
mpremote --version
```

依赖：Python 3 标准库 + mpremote。

---

## 核心设计

### main.py 的 3 秒启动延时

upy-generate Phase 5 约束 #0 要求 main.py 第一行代码是 `time.sleep(3)`。这给了 deploy 软复位后足够的重连时间：

```
mpremote soft-reset
  → 设备重启，USB 断开
  → Windows 重新枚举 COM（1~3s）
  → mpremote 重连 + resume
  → main.py 恰好在 3s 延时窗口内，此时连上不会丢任何输出
```

没有这个延时，mpremote 连上时 main.py 可能已经跑了一半（日志头、I2C 扫描结果丢失）。

### print() + 轮转日志双通道

deploy 从两个来源获取设备输出：

| 来源 | 方式 | 特点 |
|------|------|------|
| REPL 实时输出 | mpremote 持久会话 | `print()` 即时可见，但 REPL 断开即丢失 |
| 设备端日志文件 | `mpremote fs cp :log/run_*.log` | 跨重启保留，REPL 断开仍可读取 |

deploy Phase 5 抓取日志文件作为补充——即使持久会话因断连遗漏了部分输出，日志文件能补全。

---

## 执行步骤

### Phase 1: 上传文件

**首选方案**：使用项目自带的 `tools/flash_device.py`（由 upy-scaffold 生成）：

```bash
# 上传 firmware/ 全部文件，--no-reset 让 deploy 自己控制复位时机
python tools/flash_device.py --upload --no-reset --port <COM>
```

`flash_device.py` 自动完成：递归遍历 firmware/、跳过 .gitkeep、创建远程目录、逐文件 cp、main.py 排到最后上传。

**降级方案**（`tools/flash_device.py` 不存在时，直接用 mpremote）：

```bash
cd firmware

# 1. 创建必要目录（先 ls 检查是否已存在）
mpremote connect <device> resume fs ls :log >/dev/null 2>&1 || \
    mpremote connect <device> resume fs mkdir :log
mpremote connect <device> resume fs ls :lib >/dev/null 2>&1 || \
    mpremote connect <device> resume fs mkdir :lib
mpremote connect <device> resume fs ls :drivers >/dev/null 2>&1 || \
    mpremote connect <device> resume fs mkdir :drivers
mpremote connect <device> resume fs ls :tasks >/dev/null 2>&1 || \
    mpremote connect <device> resume fs mkdir :tasks

# 2. 上传 lib/ 和 drivers/（先传依赖，后传入口）
for f in lib/**/*.py; do
    mpremote connect <device> resume fs cp "$f" ":$f"
    sleep 0.5
done
for f in drivers/**/*.py; do
    mpremote connect <device> resume fs cp "$f" ":$f"
    sleep 0.5
done

# 3. 上传配置和任务文件
mpremote connect <device> resume fs cp board.py :board.py
mpremote connect <device> resume fs cp conf.py :conf.py
mpremote connect <device> resume fs cp boot.py :boot.py
for f in tasks/*.py; do
    mpremote connect <device> resume fs cp "$f" ":$f"
    sleep 0.5
done

# 4. main.py 最后上传（它一旦存在，设备启动就会执行）
mpremote connect <device> resume fs cp main.py :main.py
```

**上传顺序**：lib/ → drivers/ → config → tasks → main.py（最后）。`flash_device.py` 通过排序保证此顺序。

**从 `firmware/` 目录执行**：`cd firmware` 后所有路径为相对路径，远程路径（`:` 前缀）与本地路径一致，避免多一层 `firmware/` 目录前缀。

**关于 `resume`**：降级方案中 fs cp 必须带 `resume`。`flash_device.py` 在 upload 阶段设备空闲，实测不加 resume 也可正常工作。

---

### Phase 2: 校验文件完整性

```bash
# 列出设备文件树
mpremote connect <device> resume fs tree

# 或逐目录对比
mpremote connect <device> resume fs ls :lib/
mpremote connect <device> resume fs ls :drivers/
```

对比本地文件列表，缺文件则重传。

---

### Phase 3: 软复位 + 等待重连

```bash
# 不使用 resume —— 就是要让设备重启
mpremote connect <device> soft-reset
```

调用 `wait_for_device(com, timeout=60)` —— 轮询直到设备应答：

```
每 2 秒:
  mpremote connect <com> resume exec "print(1)"
  → 成功（收到 "1"）: 设备就绪，main.py 正在 3s 延时窗口内
  → 失败（连接错误/无应答）: 继续等待
  → 超时 60s: 报 FAIL，终止
```

**注意**：`soft-reset` 后设备重启，Windows 可能换 COM 号。如果 `connect <com>` 持续失败，用 `mpremote connect list` 重新扫描 COM 口。

---

### Phase 4: 持久会话 + 采集输出

设备自动运行 main.py。建立持久会话捕获完整输出（60s 超时）。

**Windows（subprocess + pipe）**：

```python
import subprocess, threading, time

proc = subprocess.Popen(
    ["mpremote", "connect", com, "resume", "repl"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT, bufsize=0,
)

output_lines = []
def reader():
    for line in iter(proc.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace")
        output_lines.append(text)
        print(text, end="")  # 实时回显

t = threading.Thread(target=reader, daemon=True)
t.start()

# 等待 60s 或 scheduler 稳定运行标志
deadline = time.time() + 60
while time.time() < deadline:
    if any("starting scheduler" in l.lower() for l in output_lines):
        break  # 调度器启动 = 成功，提前结束
    time.sleep(1)

proc.terminate()
```

**Linux/macOS（PTY，参见 mpremote-live-session）**：

使用 `pty.openpty()` + `os.fork()` 建立真正的终端会话。比 pipe 更可靠，支持 Ctrl+C 转发。

**超时策略**：
- 看到 `"starting scheduler"` 或等效标志 → 提前判定 PASS，结束采集
- 60s 无关键标志但无错误 → PASS（可能只是没有打印标志）
- 输出 Traceback → FAIL

---

### Phase 5: 抓取设备端日志

持久会话可能因断连丢失部分输出。从设备文件系统补充读取。

**获取日志目录**：从 `firmware/conf.py` 读取 `LOG_DIR`，默认 `/log`：

```bash
LOG_DIR=$(python -c "import sys; sys.path.insert(0,'firmware'); from conf import LOG_DIR; print(LOG_DIR)" 2>/dev/null || echo "/log")
```

**5a. 即时分析（fs cat → pipe 到 log_report.py）**：

```bash
python tools/read_device_log.py --port <COM> --log-dir $LOG_DIR \
    | python tools/log_report.py --input > deploy_log_report.json
```

`read_device_log.py` 内部用 `fs ls :{log_dir}/` 动态发现所有 `run_*.log`，然后 `fs cat` 逐文件读取内容输出到 stdout。`log_report.py` 接收 stdin，输出结构化 JSON。

**5b. 下载原始文件（fs cp → 本地，供 autofix 用）**：

```bash
python tools/read_device_log.py --port <COM> --log-dir $LOG_DIR --download ./deploy_logs/
```

`fs cp` 下载每个 `run_*.log` 到本地 `deploy_logs/` 目录。这些原始 .log 文件在 FAIL 时传给 upy-autofix 的服务端 LLM 做深度分析。

**降级方案**（`tools/read_device_log.py` 不存在时）：

```bash
mpremote connect <device> resume fs ls :log/
mpremote connect <device> resume fs cp :log/run_0.log deploy_log_0.log
mpremote connect <device> resume fs cp :log/run_1.log deploy_log_1.log
# ... 按 fs ls 实际列出的文件逐一下载
python tools/log_report.py deploy_log_*.log
```

日志文件包含从 boot 到 crash 的完整记录（即使 REPL 断开也保留），是判断失败原因的关键数据源。

---

### Phase 6: 初判

**纯本地规则，不调服务端 AI。** 结合两个数据源做判定：

**数据源 1 — REPL 实时输出（grep 规则）：**

```
判定规则:
  output 含 "Traceback (most recent call last)" → FAIL (Python 异常)
  output 含 "rst cause:"                          → FAIL (硬件复位)
  output 含 "Guru Meditation Error"               → FAIL (ESP32 内核 panic)
  output 含 "MemoryError" / "ENOMEM"              → FAIL (内存不足)
  60s 内无任何输出                                  → FAIL (设备无响应)
  其他                                            → PASS ✓
```

**数据源 2 — `deploy_log_report.json`（log_report.py 结构化输出）：**

```bash
# 检查 JSON 中的 error_count
error_count=$(python -c "import json; print(json.load(open('deploy_log_report.json'))['error_count'])")
```

若 `error_count > 0` 且 REPL grep 未命中 → 仍判定 FAIL（日志中有错误，但 REPL 输出可能因断连丢失）。逐一检查 error level：P0 和 P1 级别直接 FAIL，P2 级别作为辅助信息。

```
输出结构:
  { status: "PASS" | "FAIL",
    com_port: "COM3",
    output: <采集的完整 REPL 输出>,
    log_report: <deploy_log_report.json 内容>,
    log_files: <deploy_logs/ 目录下的原始 .log 文件列表>,
    deployed_files: <fs tree 输出>,
    device_info: { firmware, flash_free, freq }
  }
```

PASS → 流程结束，展示运行结果。
FAIL → 将完整上下文（REPL 输出 + deploy_log_report.json + deploy_logs/*.log）传给 upy-autofix。

---

## 平台差异

| | Windows | macOS | Linux |
|------|------|------|------|
| 端口标识 | `COM3` | `/dev/tty.usbmodem*` | `/dev/serial/by-id/*` 或 `mpy-dev tty` |
| 持久会话 | subprocess + pipe | PTY | PTY |
| 端口变化处理 | `mpremote connect list` 重扫 | 路径稳定（USB 槽位不变） | `mpy-dev` 按设备名查找 |
| 重连等待 | 是（COM 号可能变） | 通常不需要 | 不需要（by-id 稳定） |

---

## 与 mpremote-* skill 的关系

| 步骤 | 首选工具 | 备用 skill | 说明 |
|------|---------|----------|------|
| 上传文件 | `tools/flash_device.py --upload --no-reset` | mpremote-file-transfer | 项目自带工具，递归上传 + 排序 main.py 最后 |
| 校验文件 | — | mpremote-device-interaction | `fs tree` / `fs ls` 对比本地文件列表 |
| 软复位 | — | mpremote-device-interaction | `soft-reset`（不用 resume） |
| 重连等待 | — | mpremote-device-interaction | `resume exec "print(1)"` 轮询 |
| 持久会话 | — | mpremote-live-session | PTY/pipe 采集完整 REPL 输出 |
| 抓日志 cat | `tools/read_device_log.py --port` | mpremote-file-transfer | `fs cat` 读内容 pipe 到 log_report.py |
| 抓日志 cp | `tools/read_device_log.py --download` | mpremote-file-transfer | `fs cp` 下载原始 .log 供 autofix |
| 日志解析 | `tools/log_report.py --input` | — | 结构化 JSON（P0~P2 分级 + MemoryError/ENOMEM） |

---

## 与其他 skill 的关系

- ← `upy-generate`：输入完整 firmware/ + manifest（phase: generate）
- → `upy-autofix`：FAIL 时传入错误上下文
- → `upy-wiring` / `upy-diagram`：并行生成可视化（不阻塞 deploy）

---

## 强约束

- **不调服务端 AI**：deploy 纯本地操作，快速闭环。错误分析留给 autofix
- **不修改代码**：只上传、运行、判定。修复是 autofix 的职责
- **main.py 必须最后上传**：它触发设备启动主逻辑，先传依赖再传入口
- **fs cp 必须带 resume**：不带 resume 的 fs cp 会先软复位，传输中间文件损坏
- **重连超时 60s**：覆盖 USB 重枚举 + main.py 3s 延时 + 启动初始化
- **日志双源采集**：持久会话 REPL 输出 + 设备端轮转日志文件，互补
