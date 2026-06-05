---
name: upy-autofix
description: 第六步——编排协调层。读取设备日志，解析错误，分级决策后委托上游 skill 修复（generate/select-hw/analyze），最多 3 次尝试。触发：upy-deploy 运行失败后自动进入。
---

# 自动化调试闭环 Skill

## 角色定位

**编排协调层，不是独立修复机。** 核心逻辑：读取工具结果、串口输出和原始日志 → 分级决策 → 委托上游 skill 修复 → 验证。

数据采集只提供事实，不做修复决策。所有判断由 LLM 完成。

---

## 前置条件

- `upy-deploy` Phase 6 判定 FAIL
- `deploy_logs/` 目录下有设备端原始日志文件（`run_*.log`）
- 上一轮工具结果、串口输出或部署日志可读

---

## 执行步骤

### Step 1: 采集结构化排查事实

读取部署日志、串口输出和上一轮工具结果，整理为结构化排查事实。

**每个字段都有默认值**——日志缺失或格式异常时用 `unknown` / `null`，并在 `warnings` 字段列出所有降级情况。

### Step 2: LLM 综合研判

LLM 同时读取两个信息源：

| 来源 | 作用 | 何时读 |
|------|------|--------|
| 结构化排查事实 | 快速定位：错误类型、P 级别、I2C 状态、attempt 计数 | 每次都读 |
| deploy_logs/*.log / 串口原始输出 | 深度理解：完整 traceback、print 时序、上下文 | 结构化事实不足以判断时 |

**研判顺序：**

1. 先看结构化事实的 `i2c_ok` 字段
   - `false` → 硬件问题，跳 Step 5（输出排查指引），**不修代码**
   - `true` 或 `null`（无 I2C 设备）→ 软件问题，继续

2. 看结构化事实的 `p_level` + `error_type`
   - P0 拼写/import → LLM 直接 Edit 文件（一行修复，不值得启动上游 skill）
   - P0 驱动 API 错误 → Step 3 委托 upy-generate
   - P1 引脚/地址冲突 → Step 3 委托 upy-select-hw
   - P1 看门狗/内存 → Step 3 委托 upy-generate
   - P2 传感器异常 → Step 3 委托 upy-generate
   - P3 死循环/无输出 → Step 3 委托 upy-generate
   - `unknown` → 读原始日志，LLM 独立判断错误类型后走对应路径

### Step 3: 委托上游 skill 修复

LLM 使用 `load_skill` 工具调用上游 skill，**打包 error context**：

**委托 upy-generate 时传入：**
- 原始 traceback（从 JSON 或原始日志提取）
- 报错文件路径 + 行号
- 涉及的驱动名称
- project-manifest.json 路径
- 前几次尝试的修改内容 + 失败原因（attempt > 1 时）

**委托 upy-select-hw 时传入：**
- 当前引脚冲突详情
- project-manifest.json 路径

**委托 upy-analyze 时传入：**
- 缺失的传感器/功能说明
- 用户原始需求描述

### Step 4: 验证修复结果

每次修复后的验证路径：

```
修复完成
  ↓
可选：加载 `upy-simulate` 做 PC 端快速验证（2-3s，省去串口烧录延迟）
  ↓
加载 `upy-deploy` 重新烧录运行
  ↓
重新读取工具结果、串口输出和日志
  ↓
读结构化事实：
  ├─ status="pass" → 成功，输出 PASS 摘要
  └─ status="fail" → 回到 Step 2 重新研判（可能升级回退层级）
```

**升级规则**：同一策略连续失败 → 向上一级回退（P0 直接改 → P0 委托 generate → P1 委托 select-hw → 需求层面 analyze）。

### Step 5: 硬件问题 — 输出排查指引

当 `i2c_ok: false`（已尝试 software I2C + 降速均无效）时，LLM 直接输出以下中文指引，**不修代码**：

```
I2C 总线扫描不到设备，已尝试 software I2C 和低速模式，均无响应。这是硬件连接问题，请按以下顺序排查：

1. 接线检查：
   - SDA/SCL/VCC/GND 每根线用万用表通断档确认导通
   - VCC 接 3.3V（不是 5V！）
   - GND 必须与 MCU 共地

2. 供电检查：
   - 模块电源指示灯是否亮？
   - VCC 引脚电压是否为 3.3V ± 0.1V？

3. 上拉电阻：
   - SDA/SCL 各需 4.7kΩ 上拉到 3.3V
   - 部分模块自带，部分没有——检查你的模块

4. 传感器本身：
   - 是否发热异常？
   - 替换另一块同型号传感器测试

5. 冲突检查：
   - 拔掉其他外设，只接这一个传感器测试

排查完成后发送"重新部署"重试。
```

### Step 6: 3 次全败 — 回滚 + 总结

然后 LLM 输出中文卡点报告：

```
自动修复 3 次未成功。

错误类型：{error_type}
3 次尝试：
  1. {strategy1} → {result1}
  2. {strategy2} → {result2}
  3. {strategy3} → {result3}

已保留修复前状态，建议从最后一次有效版本继续。

建议手动排查方向：{具体建议}
```

### Step 7: 错误数据记录

将每次修复的历史记录到 `logs/error_report.json`（追加模式，若项目存在该目录），包含：时间戳、MCU 型号、错误类型、traceback、每次尝试的策略和结果、使用的 skill 版本。

LLM 在 3 次全败时额外补充 `llm_analysis` 字段（根因分析 + 知识盲区标记）。

---

## 与其他 skill 的关系

```
upy-deploy FAIL
    ↓
upy-autofix (本 skill)
    ├── 工具结果 / 串口 / 日志 → 采集数据
    ├── LLM 研判
    ├── 委托 → upy-generate（代码修复）
    ├── 委托 → upy-select-hw（引脚/地址修复）
    ├── 委托 → upy-analyze（需求重新分析）
    ├── 可选验证 → upy-simulate（PC 快速验证）
    ├── 重新部署 → upy-deploy
    └── 失败回流 → CI/CD 反馈到各 skill SKILL.md
```

- ← `upy-deploy`：接收 FAIL 判定 + deploy_logs/ 日志
- ⇄ `upy-generate`：委托代码修复
- ⇄ `upy-select-hw`：委托引脚/地址重新分配
- ⇄ `upy-analyze`：委托需求重新分析
- ⇄ `upy-simulate`：可选 PC 验证
- ⇄ `upy-deploy`：修复后重新烧录

---

## 强约束

- **采集层不做修复决策**：只提供结构化事实，LLM 读事实 + 原始日志后独立判断
- **硬件检测必须最先做**：I2C 扫描为空 → 直接输出排查指引，不进入修复循环
- **每次修复前保留可回滚快照**：不要要求 LLM 执行版本控制提交
- **最多 3 次尝试**：3 次全败 → 停止自动修复 + 输出卡点报告
- **LLM 必须读原始日志**：结构化事实可能 `error_type: "unknown"`，此时 LLM 必须从原始日志独立判断
- **P0 拼写/import 由 LLM 直接 Edit**：不值得启动上游 skill 的开销
- **所有其他修复必须委托上游 skill**：autofix 自己不写修复代码
- **错误数据回流**：每次修复记录到 `error_report.json`，驱动 CI/CD 持续改进
