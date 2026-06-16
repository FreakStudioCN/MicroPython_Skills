# [Skill 名称] 接口定义

> 状态：⚠ 待填写
> 
> 填写说明：按本模板的 6 个部分填写。填写完成后将状态改为 ✅ 已定稿。
> 本模板被 `skills/README.md` 引用，插件端和服务器端工程师都按此文档开发。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | [analyze / select-hw / scaffold / generate / simulate / deploy / autofix / wiring / diagram / cold-driver] |
| 上游 Skill | [哪个 skill 完成后自动进入，或用户手动触发] |
| 下游 Skill | [完成后进入哪个 skill] |
| 一句话职责 | [用一句话说清楚这个 skill 做什么] |

---

## 二、插件输入 → Skill（P→S）

即插件需要给这个 skill 提供什么数据。

| 输入项 | 类型 | 必填 | 来源 | 说明 |
|--------|------|------|------|------|
| user_description | string | 是 | 用户输入框 | 用户的项目描述 |
| pre_selected_board | object? | 否 | 板卡选择器 | 用户在插件中提前选好的板卡 |
| preferences.mode | string | 否 | 插件设置 | "beginner" / "custom" |
| ... | ... | ... | ... | ... |

**pre_selected_board 结构（当用户提前选了板卡时）：**
```json
{
  "id": "esp32-devkit-v1",
  "display_name": "ESP32 DevKit V1",
  "mcu": "ESP32-WROOM-32",
  "chip_family": "esp32",
  "firmware_url": "https://micropython.org/download/ESP32_GENERIC/"
}
```

---

## 三、Skill 输出 → 插件（S→P）

即这个 skill 会向插件发送哪些消息。

按执行步骤列出，每个步骤标注消息类型和关键内容。

### 步骤消息表

| 步骤 | 消息类型 | 触发条件 | 关键内容 |
|------|---------|---------|---------|
| Step X: xxx | status_update | 开始执行时 | message: "正在xxx..." |
| Step Y: xxx | approval_request | 需要用户确认时 | header: "xxx", items: [...] |
| ... | ... | ... | ... |
| 最后 | phase_complete | 阶段完成 | result: "success"/"failed", artifacts: [...] |

### approval_request 卡片设计

对每个审批卡片，画出插件的渲染效果（ASCII 示意图或描述）：

```
┌─────────────────────────────────────────┐
│  卡片标题                                │
│                                         │
│  [摘要信息区]                             │
│                                         │
│  ☑ 选项 1 — 说明                         │
│  ☑ 选项 2 — 说明                         │
│                                         │
│  [+ 添加]                                │
│                                         │
│  [确定按钮]  [取消按钮]                   │
└─────────────────────────────────────────┘
```

### status_update 列表

列出本 skill 会发出的所有进度消息文本：

| step_id | message | level | 触发时机 |
|---------|---------|-------|---------|
| ... | ... | ... | ... |

### phase_complete 产物

| artifact 类型 | 标题 | 内容说明 |
|-------------|------|---------|
| table | xxx | headers: [...], rows: [...] |
| file_tree | xxx | ... |
| ... | ... | ... |

---

## 四、SKILL.md 修改点

> **本节用于 Phase B 通信翻译。** Phase A 逻辑改动（流程增删、步骤调整、分支修正）应先在本地 Claude Code 跑通，确认逻辑无误后再按本节逐条机械翻译通信方式。逻辑改动和通信翻译不要混在一起。

列出需要修改的具体位置和内容。格式：

| 修改位置 | 当前行为 | 改为 | 原因 |
|---------|---------|------|------|
| Step 2A 分流 | AskUserQuestion(...) | approval_request(...) | 审批卡片代替命令行问答 |
| Step X: xxx | Bash(...) | device_command(...) | 透传给插件执行 |
| ... | ... | ... | ... |

---

## 五、插件端需要实现的 UI 组件

| 组件 | 用途 | 复用的协议消息 |
|------|------|-------------|
| 进度时间线 | 展示本 skill 的 status_update 序列 | status_update |
| XXX 审批卡片 | xxx | approval_request |
| ... | ... | ... |

---

## 六、独立测试场景

### 插件端测试（无服务器）

1. 手动构造本 skill 的 phase_complete 消息，确认结果面板渲染正确
2. 手动构造本 skill 的 approval_request 消息，确认卡片交互正确

### Skill 端测试（无插件）

1. 用 mock_plugin.py 模拟插件应答，跑通完整 skill 流程
2. 确认所有发出的消息 JSON 符合 02-protocol.md Schema
