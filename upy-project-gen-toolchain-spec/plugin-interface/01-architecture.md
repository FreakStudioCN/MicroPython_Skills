# 系统架构

## 一句话总结

**服务器端 LLM 执行完整 SKILL.md 做决策。插件是无脑执行层——渲染 UI + 透传本地 I/O。**

---

## 三组件职责边界

```
┌─────────────────────────────────────────────────┐
│                   VS Code 插件                    │
│  (TypeScript, 本地进程)                            │
│                                                   │
│  职责:                                             │
│  ✅ 渲染 UI（板卡画廊 / 审批卡片 / 进度时间线 / 结果面板）  │
│  ✅ 透传 mpremote 命令（扫描/烧录/REPL）              │
│  ✅ 透传文件读写（写 firmware/ 到工作区）              │
│  ✅ 透传脚本执行（flake8 / pylint / 渲染脚本）         │
│  ✅ 透传设备输出流（实时 REPL → 服务器）               │
│  ✅ 管理用户偏好（模式/语言/已有硬件）                  │
│                                                   │
│  不负责:                                           │
│  ❌ 不做任何业务决策                                │
│  ❌ 不解析设备输出含义                              │
│  ❌ 不生成代码                                    │
│  ❌ 不了解 skill / SKILL.md 的存在                  │
└─────────────┬───────────────────────────────────┘
              │ HTTP + SSE
              │ 协议: JSON（7 种消息类型）
              ▼
┌─────────────────────────────────────────────────┐
│                   服务器端                          │
│  (Python / LLM, 远程)                              │
│                                                   │
│  职责:                                             │
│  ✅ 加载完整的 SKILL.md 作为 LLM 系统指令             │
│  ✅ 执行 pipeline 决策（意图拆解 → 选型 → 生成 → ...）│
│  ✅ 调用 upypi / GitHub API 搜索驱动                │
│  ✅ 生成代码 / 测试 / wiring.json / diagram.json    │
│  ✅ 分析设备输出，判断 PASS/FAIL                     │
│  ✅ 错误分级决策 + 委托上游 skill                    │
│  ✅ 维护板卡数据库 + skill 版本                       │
│                                                   │
│  不负责:                                           │
│  ❌ 不直接操作 mpremote（无串口访问）                 │
│  ❌ 不写用户本地文件                                │
│  ❌ 不渲染 UI                                     │
└─────────────────────────────────────────────────┘
```

## 关键设计决策

| 决策 | 原因 |
|------|------|
| 插件不做决策 | 插件工程师不需要懂嵌入式/MicroPython/驱动。只实现 7 种消息的收发 |
| SKILL.md 完整保留在服务器端 | 避免 `mpy-hardware-extension` 的 phase_profile 消毒问题 |
| 本地 I/O 全部透传 | 插件不知道 mpremote 在做什么——服务器说 exec，它就 exec |
| 板卡数据库可本地可远程 | 本地测试阶段插件直接读 JSON 文件，生产阶段走 API |
| SKILL.md 不写死通信方式 | SKILL.md 描述业务逻辑，不绑定 I/O 机制。LLM 根据所在环境自动适配：本地用 Read/Bash/AskUserQuestion，服务器用 file_operation/device_command/approval_request。同一份 SKILL.md 两种环境都能跑 |

## 消息流向

```
插件 → 服务器 (7 种):
  start_phase          — 启动 skill
  approval_response    — 用户点击审批卡片的结果
  device_result        — mpremote 命令执行结果
  script_result        — 本地脚本执行结果
  file_result          — 文件操作结果
  user_intervention    — 排查中途用户干预（autofix 专用）
  error_lib_update     — 错误库增删改查（autofix 专用）
  stream_ack           — 流数据确认/终止

服务器 → 插件 (7 种):
  approval_request     — 需要用户审批（器件确认/替代选择/模式选择）
  status_update        — 进度更新（搜索中/生成中/编译中）
  device_command       — 透传 mpremote 命令
  file_operation       — 读写工作区文件
  script_run           — 执行本地脚本
  phase_complete       — 阶段完成，含结果数据
  stream               — 实时数据流（设备 REPL 输出）
```

## 一次完整的 Phase 交互示例

```
用户输入 "做一个温湿度监测仪"
  → 插件: 封装为消息 → 服务器

服务器 (upy-analyze):
  1. → status_update: "正在分析需求..."
  2. → approval_request: 器件确认卡片
  3. ← 插件: approval_response {confirmed: true, devices: [...]}
  4. → status_update: "正在搜索驱动... (1/3)"
  5. → status_update: "✓ SSD1306 → upypi"
  6. → phase_complete: {result: success, device_table: [...], ...}

服务器 (upy-select-hw):
  7. → approval_request: MCU 推荐卡片
  8. ← 插件: approval_response {selected_board: "esp32-devkit-v1"}
  9. → phase_complete: {result: success, bom: [...], pinout: [...]}

... (后续 phase 类似)
```

## 会话管理

- 每个项目一个 session_id（UUID，插件生成）
- 插件在第一条消息中发送 session_id
- 服务器维护 session 上下文（当前 phase + manifest 快照 + LLM 对话历史）
- 插件重启 → 新 session_id → 服务器重新开始
