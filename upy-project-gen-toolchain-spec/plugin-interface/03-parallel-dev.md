# 并行开发策略

## 核心原则

**协议先定，两边对协议开发，mock 独立测试，最后联调。**

Skill 维护者和插件工程师不需要彼此等待。定义好消息格式后，各自独立工作。

---

## 三线并行模型

```
         ┌── 协议定义（本文档集）──┐
         │  02-protocol.md        │
         │  skills/_template.md   │
         └─────────┬──────────────┘
                   │ 双方共同遵守
      ┌────────────┼────────────┐
      ▼            │            ▼
┌──────────┐       │     ┌──────────┐
│ Skill 端  │       │     │ 插件端    │
│ (嵌入式)  │       │     │ (前端)    │
├──────────┤       │     ├──────────┤
│ 修改      │       │     │ 实现      │
│ SKILL.md  │       │     │ 7种消息   │
│ 输出      │       │     │ 收发 +    │
│ 协议消息   │       │     │ UI 组件   │
│           │       │     │           │
│ 测试:     │       │     │ 测试:     │
│ mock插件  │       │     │ mock服务器 │
│ (简单脚本) │       │     │ (发假消息)  │
└──────────┘       │     └──────────┘
                   │
                   ▼
            ┌──────────┐
            │ 集成联调   │
            │ (真实对接) │
            └──────────┘
```

---

## 插件端独立开发指南

### 你需要做的

1. 实现 7 种 S→P 消息的接收和渲染（`02-protocol.md` 中有完整 JSON Schema）
2. 实现 5 种 P→S 消息的发送
3. 实现设备透传（mpremote spawn）
4. 实现脚本执行（child_process.spawn）

### 不需要服务器就能测试

用 mock 服务器发假消息。最简单的方式：写一个 Node.js 脚本，按顺序往 WebView 里推 JSON 消息：

```javascript
// mock-server.js — 插件端独立测试用
const messages = [
  { type: "status_update", payload: { level: "info", message: "正在分析需求...", progress: 0.1 } },
  { type: "status_update", payload: { level: "success", message: "✓ 提取到 3 个器件", progress: 0.3 } },
  { type: "approval_request", payload: { /* 器件确认卡片 */ } },
  // ... 模拟完整流程
];

// 每隔 1 秒发一条，模拟服务器响应
messages.forEach((msg, i) => {
  setTimeout(() => webview.postMessage(msg), i * 1000);
});
```

### 验收标准（独立测试）

- [ ] 能收到 `status_update` 并渲染为时间线
- [ ] 能收到 `approval_request` 并渲染为审批卡片，用户操作后能发出 `approval_response`
- [ ] 能收到 `device_command(action=exec)` 并 spawn mpremote，结果发回 `device_result`
- [ ] 能收到 `phase_complete` 并渲染结果面板（表格/文件树/markdown）
- [ ] 能收到 `stream` 并实时追加到终端面板

---

## Skill 端独立开发指南

Skill 端开发分两阶段：**先改逻辑（本地可测），再改通信（机械翻译）。** 不要把两个混在一起。

### Phase A — 逻辑先行（本地 Claude Code 直接跑）

**改什么：** SKILL.md 的流程逻辑 — 加步骤、修 bug、调顺序、加校验。

**不改什么：** 通信方式。保持 `Read`/`Bash`/`AskUserQuestion` 等本地工具，Claude Code 直接能执行。

**怎么测：** Claude Code 加载 SKILL.md，本地跑一遍。逻辑对不对、产物对不对，立刻知道。

```
例子：改 upy-gen-driver Step 5 之后加 Step 6（生成独立测试脚本）
  → SKILL.md 写 "Write firmware/drivers/sht30_driver/test_sht30.py"
  → Claude Code 写文件 ✓
  → 逻辑验证通过 ✓
```

**验收标准：**
- [ ] 本地 Claude Code 能完整跑通 skill，产物正确
- [ ] 流程步骤数、顺序、分支逻辑符合预期
- [ ] 不需要插件、不需要服务器、不需要 mock

### Phase B — 通信翻译（确认逻辑无误后执行）

Phase A 通过后，按对应接口文档的 **"四、SKILL.md 修改点"** 表，逐条机械翻译：

```
本地工具                          协议消息
Read                          →   file_operation(read)
Write / Edit                  →   file_operation(write)
Bash(python validate.py ...)  →   script_run(validate.py ...)
Bash(mpremote ...)            →   device_command(...)
AskUserQuestion               →   approval_request(...)
```

逻辑不变，只是 I/O 方式换了一套。这步不会引入新 bug。

**怎么测：** 用 `mock_plugin.py` 模拟插件应答，验证消息格式。

```python
# mock_plugin.py — Phase B 协议验证用
import json, sys

mock_device_state = {"i2c_scan": "[48, 60]"}
mock_user_choice = {"action": "confirm"}

for line in sys.stdin:
    msg = json.loads(line)
    t = msg["type"]
    
    if t == "approval_request":
        print(json.dumps({
            "type": "approval_response",
            "payload": {"approval_id": msg["payload"]["approval_id"], **mock_user_choice}
        }))
    elif t == "device_command":
        print(json.dumps({
            "type": "device_result",
            "payload": {"cmd_id": msg["payload"]["cmd_id"], "success": True,
                        "stdout": mock_device_state.get("i2c_scan", "")}
        }))
    elif t == "status_update":
        print(f"[UI] {msg['payload']['level']}: {msg['payload']['message']}")
    elif t == "phase_complete":
        print(f"[UI] Phase done: {msg['payload']['summary']}")
```

**验收标准：**
- [ ] 所有 I/O 点已按修改点表翻译为对应的协议消息
- [ ] mock_plugin.py 能走完一个 phase，消息序列符合预期
- [ ] 消息 JSON 符合 `02-protocol.md` 的 Schema

---

## 集成联调检查清单

两边独立测试通过后，联调按以下顺序逐个 phase 打通：

| 顺序 | Phase | 联调内容 | 预计耗时 |
|------|-------|---------|---------|
| 1 | upy-analyze | 意图拆解 → 器件确认卡片 → 驱动搜索进度 → 结果面板 | 30min |
| 2 | upy-select-hw | MCU 推荐卡片 / 用户自选板卡 → BOM+引脚表 | 20min |
| 3 | upy-scaffold | 调度模式选择 → 文件树预览 | 20min |
| 4 | upy-generate | 代码生成进度 → 文件写入 → lint 结果展示 | 60min |
| 5 | upy-deploy | 设备命令透传 → REPL 实时流 → 结果面板 | 60min |
| 6 | upy-simulate | 模拟脚本执行 → rich 输出流 | 30min |
| 7 | upy-autofix | 修复循环进度 → 多次 device_command 往还 | 45min |
| 8 | upy-wiring + upy-diagram | HTML 预览渲染 | 20min |

---

## 沟通机制建议

- Skill 维护者每填完一个 skill 的接口文档，通知插件端
- 插件端对照文档实现该 phase 的 UI 组件（可以并行做其他 phase）
- 每个 phase 完成后联调一次，不要等到 10 个 skill 全部写完才联调
