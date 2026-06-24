---
name: upy-analyze-plugin
description: 插件化工作流版 analyze。读取用户自然语言和插件上下文，完成需求解析、器件确认、驱动搜索、替代推荐或冷门驱动标记，并以 phase_complete + manifest_content 把结果交给下游。触发：插件 start_phase(analyze)。
---

# 插件化工作流版需求解析与驱动搜索 Skill

## 角色定位

这是 `upy-analyze` 的插件化工作流版本。

目标不是延续“本地多轮问答 + 直接写盘”的旧形态，而是改成：

```text
用户自然语言 + 插件上下文
-> 意图拆解
-> 器件确认
-> 按工作流搜索驱动
-> 替代推荐或冷门驱动标记
-> 输出 manifest_content
-> phase_complete(next_phase=select-hw, next_skill=/upy-select-hw-plugin)
```

本 skill 不覆盖原版 `G:\MicroPython_Skills\upy-analyze`，用于独立演进插件化工作流。

## 硬约束

- 输入固定为插件上下文字段，不再先问“小白/自定义”
- 主流程只保留 1 个主确认点：器件确认卡片
- `custom` 模式最多允许 1 张补充卡片
- `beginner` 模式如需补充场景/供电/性能/输出，也必须收敛成 1 张补充卡片
- `system_recommended` 且无驱动时允许替代推荐，最多 2 个候选
- `user_specified` 且无驱动时不自动替代，直接标记冷门驱动路径
- analyze 只负责 cold-driver 打标，不在本 phase 内生成驱动
- analyze 的完成标准是 `phase_complete`，不是本地 manifest 写盘
- 下游 phase 标准交接物是 `manifest_content`
- `next_phase` 当前固定为 `select-hw`
- `next_skill` 当前固定为 `/upy-select-hw-plugin`
- `next_phase` 表示工作流阶段名，不能改成插件名；调用入口由 `next_skill` 表示
- 在无真实插件宿主的 Claude Code 直测模式下，允许额外写入调试产物，但这些文件只是直测证据，不替代 `phase_complete.manifest_content`
- 在任何确认点，未收到用户明确确认前，不得自动继续到下一步
- 不允许模型替用户默认点击“确认”
- 不允许模型在同一条回复里同时“展示确认卡片”又“假定用户已确认并继续执行”

## 工作流目标

本 skill 的目标不是做多轮自由对话，而是产出一份稳定的入口阶段结果：

```text
输入上下文
-> 意图拆解
-> 器件确认
-> 可选需求补充
-> 驱动搜索
-> 替代推荐或冷门驱动标记
-> manifest 校验
-> phase_complete(next_phase=select-hw, next_skill=/upy-select-hw-plugin)
```

## 输入契约

本 skill 只接受以下输入字段：

- `user_description`
- `pre_selected_board`
- `preferences.mode`
- `preferences.locale`
- `existing_hardware`

### 输入解释

- `user_description`
  - 用户自然语言需求描述，是本 phase 的主输入
- `pre_selected_board`
  - 可为空
  - 为空时，只记录“未选板卡”，不在 analyze 内做最终选型
- `preferences.mode`
  - 影响是否需要补充卡片
- `preferences.locale`
  - 影响后续卡片文案和结果文案
- `existing_hardware`
  - 只作为器件清单补充信息，不在 analyze 内做复杂推导

### 输入缺失处理

- 若 `user_description` 缺失或为空：
  - 立即停止
  - 输出结构化错误，不进入后续步骤
- 若 `preferences` 缺失：
  - 使用默认值：
    - `mode = "beginner"`
    - `locale = "zh"`
- 若 `pre_selected_board` 缺失：
  - 视为 `null`
- 若 `existing_hardware` 缺失：
  - 视为空数组

## 执行步骤

### Step 1: 读取插件输入上下文

- 读取 `user_description`
- 读取 `pre_selected_board`
- 读取 `preferences.mode`
- 读取 `preferences.locale`
- 读取 `existing_hardware`

输出目标：

- 建立本次 analyze 的工作上下文
- 不在这一步追问用户
- 立即准备第一条进度消息：
  - `status_update(step_id="intent_extraction", level="info", message="正在分析需求...")`

### Step 2: 意图拆解

- 从自然语言中提取功能描述
- 提取用户明确指定的器件
- 补充系统推荐器件
- 区分 `user_specified` / `system_recommended`

必须完成的结构化产物：

- `project_name`
- `requirements.description`
- 初始 `devices[]`
- 每个器件的：
  - `name`
  - `type`
  - `interface`
  - `source`

工作要求：

- 不得在器件型号不明确时偷偷替用户锁定具体型号
- 用户明确指定的型号必须保留为 `user_specified`
- 用户对指定器件补充的行为/电平/触发语义必须保留在该器件上，不要只写入 `requirements.description`。例如“触摸按键用 TTP223，按下后为低电平”应输出 `devices[].notes`，并尽量结构化为 `devices[].behavior.active_level="low"`。
- 系统补充的器件必须标记为 `system_recommended`

完成本步骤后，必须输出：

- `status_update(step_id="intent_done", level="success", message="提取到 N 个器件 ...")`

### Step 3: 器件确认

- 发出器件确认卡片
- 用户可确认、删除、增加器件

这是主流程唯一必经确认点。

确认后必须得到：

- 最终器件清单
- 新增器件列表
- 删除器件列表
- 用户是否修改了系统推荐器件

如果用户中途补充说明：

- 将本次补充视为一次重新分析触发
- 保留当前上下文
- 回到 Step 2 重新拆解
- 然后重新生成器件确认卡片

不得只做局部字符串拼补。

本步骤的协议目标：

- 发出 `approval_request(device_confirm)`
- 插件返回 `approval_response`
- analyze 根据结果更新 devices 列表

强停点规则：

- 到达 `device_confirm` 后，必须停止并等待用户回复
- 用户未明确表达“确认 / 修改 / 补充”前，不得进入 Step 4 或 Step 5
- 若当前运行环境没有真实插件卡片 UI，也必须以对话形式停住等待用户输入
- 不得因为 `beginner` 模式就自动视为“用户已确认器件清单”

### Step 4: 可选补充卡片

- 仅在需要时启用
- beginner/custom 最多各允许 1 张补充卡片
- 不恢复成多轮问答

用途：

- 收集对后续 phase 明显有用，但在用户原始输入中缺失的重要信息
- 例如：
  - scene
  - power
  - output
  - sample_rate / precision 的粗粒度档位

要求：

- 只允许 1 张结构化卡片
- 不允许拆成多轮命令行追问
- 用户未填写时允许回落到默认值

本步骤的协议目标：

- 发出 1 张补充型 `approval_request`
- 插件返回 `approval_response`
- analyze 更新 requirements 中对应字段

强停点规则：

- 若发出 `requirement_supplement`，必须停止并等待用户选择
- 不得在同一条回复里一边展示补充卡片，一边默认采用推荐值继续执行
- 只有在用户明确确认后，才能进入驱动搜索

### Step 5: 驱动搜索

- 对每个器件执行驱动搜索
- 按结果写入 `driver` 状态
- 具体器件驱动搜索必须委托 `upy-pkg-guide` skill，不得由 analyze 自己伪造 upypi 包名或安装命令
- 本机 runner/mock 环境可以使用 `pkg_guide_adapter` 返回固定测试结果，但该 adapter 必须模拟 `upy-pkg-guide` 的输出语义

#### 5A. 驱动搜索总原则

Analyze 在做驱动搜索前，必须先区分两层：

1. `builtin_runtime`
2. 具体器件驱动来源

不要把“MCU/固件已提供底层外设 API”和“已经找到某个具体器件驱动包”混成同一种结果。

先回答两个问题：

1. 这个器件底层是否依赖 MicroPython 内置外设 API？
2. 这个具体器件是否存在现成 MicroPython 驱动包？

若第 2 个问题涉及具体器件驱动包，必须对该器件调用 `upy-pkg-guide`：

```text
for device in confirmed_devices:
  if device is builtin runtime only:
    mark builtin_runtime
  else:
    call upy-pkg-guide(device.name / aliases / chip model)
    normalize result into devices[].driver
```

`upy-pkg-guide` 的职责边界：

- 先查 `upypi`
- 无结果时 fallback 到 `awesome-micropython`
- 对可用包提取 `package_name`、`version`、`install_cmd`、`api_ref`、`repo_url`
- `api_ref` 应优先写成结构化对象，例如 `{"init": "...", "read": "...", "calibration": "..."}`；不要只写一段不可解析的字符串。若来源资料只能确认一句摘要，可先写入 `notes`，不要伪装成完整 API。
- 找不到可用 MicroPython 驱动时返回“无驱动”，由 analyze 决定替代推荐或 cold-driver 标记

#### 5B. builtin runtime 判定

`builtin_runtime` 只表示：

- MicroPython 固件已经提供底层运行时/外设 API
- 当前器件至少可以基于这些内置 API 做底层访问

典型例子：

- GPIO 输入输出
  - `machine.Pin`
- ADC 采样
  - `machine.ADC`
- I2C / SPI / UART 总线访问
  - `machine.I2C`
  - `machine.SPI`
  - `machine.UART`
- I2S 麦克风 / 功放 / 喇叭
  - `machine.I2S`
- WiFi 网络
  - `network`
- 蓝牙
  - `bluetooth`
- WS2812 / NeoPixel
  - `neopixel`

这类情况不应该报成“无驱动”，而应标记为：

- `driver.source = "builtin_runtime"`

并建议补充：

- `driver.module`
- `driver.notes`

但要注意：

- `builtin_runtime` 不等于“已经找到该具体器件的现成驱动包”
- 对于 `I2C / SPI / UART` 上的具体器件，Analyze 仍应继续优先检查 `upypi`

#### 5C. micropython-lib 判定

若能力不属于固件内置，但属于 MicroPython 官方生态通用库/中间件，则应单独标记为：

- `driver.source = "micropython_lib"`

这类来源不是“内置固件自带”，也不应被混同为普通第三方 GitHub 库。

在 analyze 阶段，`micropython_lib` 的定位是：

- 官方生态通用库
- 中间件
- 协议/能力扩展

典型例子：

- `aioble`

建议补充：

- `driver.package_name`
- `driver.install_cmd`
- `driver.repo_url`

硬约束：

- `micropython_lib` 不是温湿度、土壤、显示器、执行器等具体器件驱动的默认第一搜索源
- 若一个结果本质上是“具体器件驱动”，应先优先考虑 `upypi`

#### 5D. 具体器件驱动优先级

若目标是“具体器件驱动”，而不是“官方生态通用库/中间件”，则按以下顺序检查外部驱动来源：

1. `upypi`
2. `awesome-micropython`
3. `github`
4. 其他明确可验证的 MicroPython 兼容来源

执行要求：

- analyze 不直接用字符串拼接生成 `package_name` / `install_cmd`
- analyze 不直接把规则推断结果写成 `driver.source = "upypi"`
- `driver.source = "upypi" | "awesome-micropython" | "github"` 必须来自 `upy-pkg-guide` 或等价 adapter 的结构化结果
- 本机 mock adapter 返回的固定结果必须标记为 mock/test 数据，不得伪装成真实网络查询

硬约束：

- 不得把 Python `PyPI` 当成 MicroPython 驱动包主搜索入口
- 优先查 MicroPython 官方/兼容生态
- 若只发现普通 Python 包，不应直接当成可用 MicroPython 驱动
- analyze 阶段不应把“固件内置能力”写成 `local`
- analyze 阶段仅在非常明确存在本地私有驱动资产时，才允许使用 `local`
- 对于 `machine.*`、`network`、`bluetooth`、`neopixel` 这类能力，应统一写成 `builtin_runtime`
- 若器件本质上依赖 `machine.ADC`、`machine.Pin`、`machine.I2S`、`network`、`bluetooth` 等内置能力，却写成 `driver.source = "none"`，应视为 analyze 输出错误，而不是可接受的弱结果
- `driver.source = "none"` 只应用于以下两类情况：
  - 当前确实不是内置运行时能力
  - 且 `upypi / awesome-micropython / github / micropython_lib` 都没有可用现成驱动

对于“不是单一型号，而是一大类实现方案”的器件，必须先拆实现族，再做驱动搜索。

例如“土壤温湿度传感器”，至少可能拆成：

- `ADC` 电容式土壤湿度传感器
- `UART/RS485/Modbus` 土壤温湿度一体传感器
- `I2C/SPI` 数字土壤传感器
- “土壤湿度 + 独立温度探头”的组合方案

规则：

- 用户已明确协议/接口/型号时，按用户指定族搜索
- 用户未明确时，只能生成“系统推荐实现族”，不能伪装成已锁定具体型号

#### 5E. 无驱动与冷门驱动

只有在以下情况都不满足时，才进入“无现成驱动/冷门驱动”判断：

- 不是 `builtin_runtime`
- `upypi` 无可用结果
- `awesome-micropython / github / 其他可信 MicroPython 驱动源` 无可用结果
- 若属于官方生态通用能力库，`micropython_lib` 也无可用结果

每个器件都必须得到以下结果之一：

1. `driver.source = "builtin_runtime"`
2. `driver.source = "micropython_lib"`
3. `driver.source = "upypi"`
4. `driver.source = "awesome-micropython"`
5. `driver.source = "github"`
6. `driver.source = "none"`
7. `driver.source = "cold-driver"`

当前 analyze 阶段推荐的 `driver.source` 集合是：

- `builtin_runtime`
- `micropython_lib`
- `upypi`
- `awesome-micropython`
- `github`
- `none`
- `cold-driver`

说明：

- `local` 不是 analyze 阶段的默认常规选项
- 如果真的使用 `local`，必须能明确说明对应本地私有驱动资产来自哪里

必须持续输出进度：

- 开始搜索
- 每个器件搜索完成
- 命中驱动来源
- 无驱动结果

不得静默跑完整轮搜索后只给最终结论。

本步骤的协议目标：

- 搜索开始时：
  - `status_update(step_id="driver_search", level="info", message="正在搜索驱动... (1/N)")`
- 每个器件完成后，根据结果输出：
  - `driver_found`
  - `driver_fallback`
  - `driver_none`
  - `driver_cold`

补充说明：

- `builtin_runtime` 归入“可支持”范畴，但应在 message 中写清：
  - 例如 `OK INMP441 -> builtin_runtime (machine.I2S)`
  - 或 `OK 土壤湿度传感器 -> builtin_runtime (machine.ADC)`

### Step 6: 分流

- `system_recommended` 无驱动 -> 可替代推荐
- `user_specified` 无驱动 -> 直接 cold-driver 标记
- 用户拒绝替代并坚持原器件 -> cold-driver 标记

#### 6A. 替代推荐条件

只有以下条件同时成立时才允许替代推荐：

- 器件来源是 `system_recommended`
- 当前器件无现成驱动
- 能找到同类别、同接口、已有驱动的替代器件

替代候选也必须经过 `upy-pkg-guide` 验证：

- 先按类别生成候选芯片/模块关键词
- 对每个候选调用 `upy-pkg-guide`
- 只允许把 `upy-pkg-guide` 确认有可用 MicroPython 驱动的候选展示给用户

替代推荐约束：

- 最多给 2 个候选
- 不得给过长候选列表
- 用户确认替代后，器件清单必须更新

#### 6B. 冷门驱动路径条件

以下情况直接进入冷门路径标记：

- `user_specified` 且无驱动
- `system_recommended` 且无驱动，用户拒绝替代并坚持原器件

Analyze 在此仅做：

- manifest 中打标
- warnings 中说明后续将进入冷门驱动生成与验证

Analyze 不做：

- PDF 收集
- Arduino 收集
- 冷门驱动生成
- 冷门驱动验证

本步骤的协议目标：

- `system_recommended` 且无驱动时：
  - 发出 `approval_request(alternative_device)`
  - 插件返回 `approval_response`
  - analyze 根据用户选择更新 devices 列表
- `user_specified` 且无驱动时：
  - 不发替代推荐卡片
  - 直接在 manifest 中打冷门路径标记

### Step 7: 输出

- 生成 manifest 草稿
- 调用校验脚本校验 manifest
- 输出 `phase_complete`
- `next_phase` 固定为 `select-hw`
- `next_skill` 固定为 `/upy-select-hw-plugin`
- 若运行在 Claude Code 直测模式且用户提供了项目/测试目录，应额外写出调试产物

#### 7A. manifest 草稿要求

至少包含：

- `schema_version`
- `phase = "analyze"`
- `project_name`
- `requirements`
- `devices`

并保证：

- `requirements` 字段完整
- `devices[].source` 明确
- `devices[].driver.source` 明确

#### 7B. 校验要求

校验脚本职责是：

- 校验枚举值
- 补齐默认值
- 返回结构化校验结果

校验脚本不是 analyze 的完成标准。

Analyze 的完成标准是：

- 成功生成可被下游消费的 `manifest_content`
- 输出 `phase_complete`

#### 7C. 交给下游

Analyze 最终必须把以下内容交给下游：

- `manifest_content`
- `warnings`
- `errors`
- `next_phase = "select-hw"`
- `next_skill = "/upy-select-hw-plugin"`

不要把“本地写盘成功”作为本 phase 唯一事实源。

本步骤的协议目标：

- 调用 `init_manifest.py` 做校验
- 读取结构化校验结果
- 生成 `phase_complete`

#### 7D. Claude Code 直测模式调试产物

当没有真实插件宿主、也没有消息总线保存 `phase_complete` 时，Claude Code 直测很难从文件系统检查结果。因此允许额外写出调试产物。

触发条件：

- 当前运行环境是普通 Claude Code 对话/本地 skill 调用
- 用户提供了项目目录、测试目录，或当前工作目录明显是测试项目目录
- 例如用户在 `G:\test\test` 下测试本 skill

推荐写入文件：

```text
{project_dir}/manifest_draft.json
{project_dir}/manifest_validated.json
{project_dir}/phase_complete.analyze.json
{project_dir}/driver_search_log.md
```

写入内容：

- `manifest_draft.json`
  - 校验前的 manifest 草稿
  - 必须包含 `project_name`、`requirements`、`devices`
- `manifest_validated.json`
  - `init_manifest.py` 校验和规范化后的 manifest
  - 必须与最终 `phase_complete.manifest_content` 保持一致
  - 必须包含 `schema_version`、`phase`、`created_at`、`updated_at`、`final_status`
- `phase_complete.analyze.json`
  - 完整 `phase_complete` 消息载荷
  - 必须包含 `manifest_content`
  - 必须保持协议形状：`artifacts` 是数组，不允许写成 `{ "manifest_draft": "..." }` 这类路径映射对象
  - 若需要记录调试文件路径，使用 `file_list` artifact，例如：
    ```json
    {
      "type": "file_list",
      "title": "Claude Code 直测产物",
      "files": [
        { "path": "manifest_draft.json", "status": "created" },
        { "path": "manifest_validated.json", "status": "created" },
        { "path": "phase_complete.analyze.json", "status": "created" },
        { "path": "driver_search_log.md", "status": "created" }
      ]
    }
    ```
- `driver_search_log.md`
  - 每个器件的搜索关键词、调用 `upy-pkg-guide` 的结果、最终 `driver.source`

约束：

- 这些文件只用于 Claude Code 直测和人工排查
- 正式插件模式仍以 `phase_complete.manifest_content` 作为唯一阶段交接物
- 不得因为调试文件写入失败而把 analyze 判定为成功或失败；阶段结果仍由 manifest 校验和 `phase_complete` 决定
- 写入前应说明这是直测调试产物，不是最终项目代码
- 写出 `phase_complete.analyze.json` 后，必须用校验脚本的 phase_complete 模式验证：
  ```bash
  python {skill_dir}/scripts/init_manifest.py --validate-phase-complete --input {project_dir}/phase_complete.analyze.json
  ```
  若校验失败，必须修正 `phase_complete.analyze.json`，不得宣称 analyze 阶段成功。

## 标准消息序列

当前 analyze 插件化版本应遵循以下消息顺序：

```text
Step 1 输入上下文建立
  -> status_update(intent_extraction)

Step 2 意图拆解完成
  -> status_update(intent_done)

Step 3 器件确认
  -> approval_request(device_confirm)
  -> approval_response

Step 4 可选补充卡片（按需）
  -> approval_request(requirement_supplement)
  -> approval_response

Step 5 驱动搜索
  -> status_update(driver_search)
  -> status_update(driver_found / driver_fallback / driver_none / driver_cold)

Step 6 替代推荐（条件触发）
  -> approval_request(alternative_device)
  -> approval_response

Step 7 manifest 校验
  -> script_run(init_manifest.py)
  -> script_result

Step 8 阶段完成
  -> phase_complete(result=success, next_phase=select-hw, next_skill=/upy-select-hw-plugin)
```

## 消息定义要求

### approval_request #1: device_confirm

用途：

- 确认器件清单
- 展示项目名、功能摘要、板卡状态
- 允许增加/删除/确认器件

要求：

- 这是 analyze 主流程唯一必经确认点
- 必须支持：
  - `allow_add = true`
  - `allow_remove = true`
  - `multi_select = true`

建议载荷示例：

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "device_confirm",
    "header": "确认项目方案",
    "question": "请确认以下器件是否正确",
    "summary": {
      "project_name": "植物助手",
      "description": "读取土壤温湿度，支持触摸交互和语音对话",
      "board": {
        "status": "selected",
        "display_name": "ESP32-S3-DevKitC-1",
        "mcu": "ESP32-S3-WROOM-1"
      }
    },
    "items": [
      {
        "id": "d1",
        "name": "土壤湿度传感器",
        "subtitle": "ADC 土壤湿度传感器",
        "meta": "系统推荐",
        "selected": true
      },
      {
        "id": "d2",
        "name": "I2S 麦克风",
        "subtitle": "I2S 语音输入",
        "meta": "系统推荐",
        "selected": true
      }
    ],
    "allow_add": true,
    "allow_remove": true,
    "multi_select": true,
    "actions": [
      {
        "label": "确认，开始搜索驱动",
        "value": "confirm",
        "primary": true
      },
      {
        "label": "修改器件清单",
        "value": "modify"
      }
    ]
  }
}
```

字段约束：

- `summary.project_name` 必填
- `summary.description` 必填
- `summary.board.status` 只能是：
  - `selected`
  - `none`
- `items[].id/name/subtitle/meta/selected` 必填
- `actions` 至少包含 1 个主动作
- 若 `board.status = "none"`，则不要求 `display_name/mcu`

在无真实 UI 的对话环境中，展示本卡片后必须遵守：

- 回复在此结束
- 等待用户输入
- 不得在卡片下方继续输出“已确认，开始搜索驱动”
- 若运行环境的提问工具存在“选项数限制”，必须先压缩分组选项或改成文本确认格式，再停住等待用户回复；不得因为工具限制而跳过确认点

### approval_request #2: requirement_supplement

用途：

- 补充 beginner/custom 模式下缺失但重要的 requirements 字段

要求：

- 最多只允许 1 张
- 不得拆成多轮

建议载荷示例：

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "requirement_supplement",
    "header": "补充需求信息",
    "question": "请补充场景、供电、性能和输出要求",
    "summary": {
      "project_name": "植物助手"
    },
    "items": [
      {
        "id": "scene_indoor",
        "name": "室内桌面场景",
        "subtitle": "默认推荐",
        "meta": "scene=indoor",
        "selected": true
      },
      {
        "id": "power_usb",
        "name": "USB 供电",
        "subtitle": "默认推荐",
        "meta": "power=usb",
        "selected": true
      },
      {
        "id": "perf_normal",
        "name": "通用性能",
        "subtitle": "1Hz / 常规精度 / 1秒响应",
        "meta": "sample_rate=normal_1hz",
        "selected": true
      },
      {
        "id": "output_serial_oled",
        "name": "串口 + OLED 输出",
        "subtitle": "默认推荐",
        "meta": "output=serial,display_oled,buzzer",
        "selected": true
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": true,
    "actions": [
      {
        "label": "确认补充信息",
        "value": "confirm",
        "primary": true
      }
    ]
  }
}
```

### approval_request #3: alternative_device

用途：

- 当 `system_recommended` 器件无驱动时，给出最多 2 个替代器件

建议载荷示例：

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "alternative_device",
    "header": "传感器：推荐替代器件",
    "question": "当前器件无现成驱动，推荐以下替代器件",
    "items": [
      {
        "id": "alt1",
        "name": "HDC1080",
        "subtitle": "精度较高，已有 upypi 驱动",
        "meta": "推荐",
        "selected": false
      },
      {
        "id": "alt2",
        "name": "AHT20",
        "subtitle": "成本较低，已有 upypi 驱动",
        "meta": "备选",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      {
        "label": "用 HDC1080（推荐）",
        "value": "accept_alt1",
        "primary": true
      },
      {
        "label": "用 AHT20",
        "value": "accept_alt2"
      },
      {
        "label": "坚持原器件，走冷门驱动",
        "value": "cold_driver"
      }
    ]
  }
}
```

### status_update

Analyze 当前最少应定义以下进度消息：

- `intent_extraction`
- `intent_done`
- `driver_search`
- `driver_found`
- `driver_fallback`
- `driver_none`
- `driver_cold`

### phase_complete

Analyze 的 `phase_complete` 至少应包含：

- `phase = "analyze"`
- `result`
- `summary`
- `next_phase = "select-hw"`
- `next_skill = "/upy-select-hw-plugin"`
- `manifest_content`
- `artifacts`：必须是数组。调试文件路径用 `file_list` artifact 表达，不允许用对象映射代替数组。
- `warnings`
- `errors`

## 对话环境专用约束

若 analyze 运行在没有真实插件卡片宿主的环境中，例如普通聊天式 skill 调用，则必须遵守以下规则：

1. `approval_request(device_confirm)` 出现后，回复必须结束，等待用户输入
2. `approval_request(requirement_supplement)` 出现后，回复必须结束，等待用户输入
3. `approval_request(alternative_device)` 出现后，回复必须结束，等待用户输入
4. 不允许在没有用户回复的情况下自动推进到：
   - 驱动搜索
   - manifest 校验
   - phase_complete
5. 如果用户回复是“修改器件”或“补充需求”，必须基于用户新输入重新分析，不能假装还是旧清单

一句话要求：

**先停，再等用户；没有用户确认，就不能往后跑。**

## manifest_content 最低交付要求

Analyze 交给下游 `select-hw` 的 `manifest_content` 至少必须包含：

- `schema_version`
- `phase = "analyze"`
- `project_name`
- `requirements.description`
- `requirements.experience`
- `requirements.output`
- `requirements.existing_hardware`
- `requirements.mcu_specified`
- `devices`

其中每个 `devices[]` 至少必须包含：

- `name`
- `type`
- `interface`
- `source`
- `driver.source`

可选但应保留的器件级字段：

- `notes`：用户对该器件的自然语言补充，例如模块型号、触发方式、电平语义、安装方式
- `behavior`：可结构化的行为事实，例如 `role`、`event`、`active_level`、`idle_level`

当用户明确描述器件行为时，优先同时写入 `notes` 和 `behavior`。例如 TTP223 触摸按键“按下后为低电平”应保留为器件级事实，供 select-hw 和 generate 决定 GPIO 输入、上拉/下拉和触发条件。

如 `driver.source` 属于现成驱动来源，后续应继续补全：

- `package_name`
- `install_cmd`
- `version`
- `api_ref`：优先为对象；字符串形式只可作为临时弱结果，并应在校验警告中暴露

## boards 资产约束

`upy-analyze-plugin` 应自带独立的 `boards/` 目录资产。

用途：

- 承接 `pre_selected_board`
- 给本机交互模拟器提供板卡列表
- 作为插件端板卡选择器的基础数据源

原则：

- 不覆盖原 skill 的 `boards`
- 插件版独立维护自己的板卡数据副本

## 本机模拟测试入口

当前本地可用的测试入口包括：

- `python run_local_mock_session.py`
  - 双向桥接 runner 和 mock plugin
  - 适合验证最小 happy path
- `python interactive_local_session.py`
  - 终端交互式模拟用户输入
  - 可输入需求、选模式、选板卡、改需求、确认器件

## 当前状态

这是插件化 analyze 的第一版可演练工作流，并且当前已经具备：

- 插件输入边界
- 主确认卡片
- 可选补充卡片
- 替代推荐 / 冷门驱动分流
- `script_run(init_manifest.py)` 校验链路
- `phase_complete(next_phase=select-hw, next_skill=/upy-select-hw-plugin)` 交接链路

后续增强重点不再是补“有没有工作流”，而是补：

- 更严格的协议约束
- 更完整的板卡资产
- 更强的 manifest 校验
- 更真实的 analyze 引擎
