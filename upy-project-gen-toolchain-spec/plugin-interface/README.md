# 插件接口文档

> 适用读者：
> - **插件端工程师**（TypeScript / VS Code Extension）— 实现 UI + 本地 I/O 透传
> - **服务器端工程师**（Python / LLM 集成）— 实现 skill 调度 + 协议消息生成
> - **Skill 维护者**（嵌入式背景）— 修改 SKILL.md 适配插件协议

---

## 目录结构

```
plugin-interface/
├── README.md                    ← 本文件，目录索引
├── 01-architecture.md           ← 系统架构：插件/服务器/skill 三者的职责边界
├── 02-protocol.md               ← 通信协议：7 种消息类型的完整 JSON Schema
├── 03-parallel-dev.md           ← 并行开发策略：两边如何独立开发 + mock 测试
│
├── skills/                      ← 每个 skill 的接口定义（逐个填充）
│   ├── README.md                ← skill 接口索引 + 填充状态
│   ├── _template.md             ← skill 接口文档模板（新 skill 按此填写）
│   ├── upy-analyze.md           ← [待填写] Phase 1 需求解析
│   ├── upy-select-hw.md         ← [待填写] Phase 2 硬件选型
│   ├── upy-scaffold.md          ← [待填写] Phase 3 项目骨架
│   ├── upy-generate.md          ← [待填写] Phase 4 代码生成
│   ├── upy-simulate.md          ← [待填写] Phase 4.5 PC 模拟
│   ├── upy-deploy.md            ← [待填写] Phase 5 烧录运行
│   ├── upy-autofix.md           ← [待填写] Phase 6 自动修复
│   ├── upy-wiring.md            ← [待填写] Phase 7a 接线图
│   ├── upy-diagram.md           ← [待填写] Phase 7b 架构图
│   ├── upy-gen-driver.md        ← [待填写] 异常路径 冷硬件驱动
│   └── upy-firmware-wrapper.md   ← [待填写] 固件 API Wrapper 包编写规范
│
└── mock-messages/               ← 各消息类型的 mock JSON 样本
    ├── README.md                ← mock 使用说明
    ├── approval-request.json
    ├── status-update.json
    ├── device-command.json
    ├── file-operation.json
    ├── script-run.json
    ├── phase-complete.json
    └── stream.json
```

## 阅读顺序

| 角色 | 先读 | 再读 | 最后 |
|------|------|------|------|
| 插件端工程师 | `01-architecture.md` → `02-protocol.md` | `03-parallel-dev.md`（插件端部分） | `mock-messages/README.md` |
| 服务器端工程师 | `01-architecture.md` → `02-protocol.md` | `skills/_template.md` | 具体 skill 文档 |
| Skill 维护者 | `01-architecture.md` | `skills/_template.md` | `02-protocol.md`（了解消息类型） |

## 当前状态

- `01-architecture.md` — 已填充
- `02-protocol.md` — 已填充
- `03-parallel-dev.md` — 已填充
- `skills/` — 部分已填写（10/12 已定稿，1 待填写，1 非 Phase）
- `mock-messages/` — 待填充

## 相关文件（不在本目录）

| 文件 | 位置 | 用途 |
|------|------|------|
| boards.json + 文档 | `../../upy-analyze/boards/` | 板卡数据库，插件画廊 + LLM 选型 |
| project-manifest.schema.json | `../project-manifest.schema.json` | 各 Phase 数据契约 |
| wiring.schema.json | `../wiring.schema.json` | 接线图数据契约 |
| diagram.schema.json | `../diagram.schema.json` | 架构图数据契约 |
