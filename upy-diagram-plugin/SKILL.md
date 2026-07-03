---
name: upy-diagram-plugin
description: 插件化 MicroPython 软件架构图生成阶段。用于收到 upy-generate-plugin success 的 optional_next_phases 选择后，读取生成后的 firmware 与 project-manifest.json，生成 docs/diagram.json，校验 diagram.schema.json，渲染 architecture/flowchart/data_flow 的 md/svg/png/html，并输出带 session/checkpoint/artifact manifest 的 phase_complete；兼容插件协议调用和本地 skill 直测，不覆盖原 upy-diagram。
---

# upy-diagram-plugin 插件化工作流

`upy-diagram-plugin` 是“一句话造硬件”流水线的可选软件架构图产物阶段。它迁移自旧 `G:\MicroPython_Skills\upy-diagram`，但必须把本地 I/O 改成插件协议：

```text
status_update(...)
approval_request(...)
file_operation(read/write/list)
script_run(...)
phase_complete(...)
```

正式链路：

```text
upy-generate-plugin success
  -> optional_next_phases includes upy-diagram-plugin
  -> user selects diagram artifacts
  -> upy-diagram-plugin
```

`upy-diagram-plugin` 不应改变主链路：

```text
upy-generate-plugin -> upy-deploy-plugin
```

也就是说，diagram 是可选附加产物阶段，`phase_complete.payload.next_phase` 默认必须是 `null`。

## 边界规则

- 不覆盖旧 `G:\MicroPython_Skills\upy-diagram`。
- 不覆盖或改名 `G:\MicroPython_Skills\upy-deploy`、`G:\MicroPython_Skills\upy-deploy-plugin`。
- 不在 diagram 阶段新增硬件、替换 MCU、改变 pinout 或修改 firmware 业务代码。
- 不执行 mpremote、烧录、串口调试或设备端测试。
- 不把 diagram 作为 deploy 的必经阶段。
- 不让插件端理解 MicroPython 软件架构语义；LLM 负责理解，脚本负责校验和渲染。

## 数据权威顺序

生成 `docs/diagram.json` 时必须按以下优先级判断事实：

```text
firmware/ 实际代码 > project-manifest.json > LLM 推断
```

其中：

- `firmware/main.py` 是执行流程、DI 装配、调度器注册和启动逻辑的最高优先级事实。
- `firmware/board.py` 表示板级 pin 常量映射，归入 `board` 层。
- `firmware/lib/**/*.py` 表示基础库，归入 `lib` 层。
- `firmware/drivers/**/__init__.py` 与 `mock.py` 表示驱动层，归入 `driver` 层。
- `firmware/tasks/*.py` 表示业务任务，归入 `task` 层。
- `test/pc/*.py`、`test/device/*.py` 表示测试层，存在时归入 `test` 层。
- `project-manifest.json` 是设计意图和上游生成记录，但与 firmware 冲突时以 firmware 为准并生成 warnings。
- Diagram 阶段只允许补充/更新 `diagrams` 字段，不得修改 `mcu`、`board`、`devices`、`pinout`、`generate` 或根级 `updated_at` 等上游事实。

## start_phase 输入

正式模式必须从 `upy-generate-plugin` 的 success phase_complete 启动：

```json
{
  "protocol_version": "1.0",
  "type": "start_phase",
  "phase": "upy-diagram-plugin",
  "session_id": "uuid",
  "msg_id": "uuid",
  "timestamp": "2026-07-02T00:00:00Z",
  "idempotency_key": "upy-diagram-plugin:<session_id>:full:v1",
  "payload": {
    "mode": "full",
    "invocation_mode": "plugin_protocol",
    "local_test": false,
    "source_phase": "upy-generate-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_generate_plugin.json",
    "complexity": null,
    "runtime_context": {
      "session_root": "sessions/<session_id>",
      "project_root": "sessions/<session_id>/project",
      "file_operation_root": "sessions/<session_id>/project",
      "resource_root": "upy-diagram-plugin"
    },
    "capabilities": {
      "protocol_versions": ["1.0"],
      "approval_request": true,
      "file_operation": true,
      "script_run": true,
      "checkpoint_resume": true,
      "cancellation": true,
      "retry": true,
      "timeout": true,
      "permission_prompt": true,
      "artifact_manifest": true,
      "network_access": {
        "allowed": true,
        "domains": ["mermaid.ink"]
      }
    },
    "render_policy": {
      "formats": ["json", "md", "html", "svg", "png"],
      "network_rendering": "ask",
      "timeout_ms": 90000
    }
  }
}
```

迁移期允许 `mode=direct_test`，但必须记录 `source_phase=test_only`。如果缺少完整 firmware 或 generate phase_complete，不能输出正式 success。

## 协议字段语义

这些字段必须按同一语义用于插件协议调用和本地 skill 调用测试：

| 字段 | 含义与约束 |
|---|---|
| `protocol_version` | 协议版本。当前只接受 `"1.0"`；不支持时输出 `DIAGRAM_PROTOCOL_UNSUPPORTED`，不得继续执行。 |
| `type` | 消息类型，如 `start_phase`、`status_update`、`approval_request`、`phase_complete`。插件按它路由。 |
| `phase` | 必须统一为 `upy-diagram-plugin`。不得混用 `diagram`、`upy-diagram`。 |
| `session_id` | 一次用户工作流的稳定 ID。checkpoint、resume、retry、artifact 归档和日志追踪都依赖它。 |
| `msg_id` | 单条消息 ID。重试时 `retry_of` 指向原 `msg_id` 或原 `idempotency_key`。 |
| `idempotency_key` | 幂等键。同一 session/phase/mode/attempt 的重试应保持稳定，避免重复写 artifact 或重复推进状态。 |
| `payload.mode` | `full` 是正式插件链路；`direct_test` 是本地 skill 测试链路，不能伪装成正式 success。 |
| `payload.invocation_mode` | `plugin_protocol` 表示文件/脚本/确认都走协议工具；`local_skill_test` 表示本地测试可直接读写项目根目录。 |
| `payload.source_phase` | 正式链路必须是 `upy-generate-plugin`；本地测试可为 `test_only`。 |
| `payload.source_phase_complete_path` | 上游 generate phase_complete 路径，用于证明 firmware 已生成且代码事实来自 generate 输出。 |
| `payload.source_phase_complete` | 可选内联上游结果。若同时存在 path 和内联对象，必须以 path 读取结果为准并校验一致性。 |
| `payload.complexity` | `simple`、`medium`、`full` 或 null。null 时需要 `approval_request(approval_id="diagram_complexity")`。 |
| `runtime_context.session_root` | 当前 session 的状态、checkpoint、phase_complete、日志和临时结果根目录。 |
| `runtime_context.project_root` | 用户项目根目录。`project-manifest.json`、`firmware/`、`docs/` 都应在这里。 |
| `runtime_context.file_operation_root` | 插件允许读写的文件边界。任何 file write 都必须落在该目录内。 |
| `runtime_context.resource_root` | 插件资源根目录，例如 `upy-diagram-plugin`，用于定位脚本。 |
| `capabilities` | 能力协商结果。正式模式缺少 `file_operation`、`script_run` 或必要 `approval_request` 时不得继续。 |
| `render_policy.formats` | 请求产物格式。正式 success 必须包含 `json/md/html/svg/png`。 |
| `render_policy.network_rendering` | 网络渲染策略：`ask`、`allow`、`deny`。`deny` 时只允许生成 JSON/MD/HTML 或本地 renderer 结果。 |
| `render_policy.timeout_ms` | 全量渲染超时，默认 90000ms。 |
| `checks` | 结构化校验结果。每个 check 建议包含 `ok`、`command`、`duration_ms`、`error_code`。 |
| `artifacts` | 面向 UI 和用户展示的产物列表。记录 type、path、required、sha256、bytes、generated_at。 |
| `file_manifest` | 面向恢复、验收和幂等去重的文件清单。比 artifacts 更偏文件系统证据。 |
| `errors` | 结构化错误数组。不得只写自然语言字符串。 |
| `warnings` | 非阻塞告警数组。SVG/PNG 缺失在正式模式不是 warning，应导致 partial。 |

## 插件调用与本地 skill 测试

`upy-diagram-plugin` 必须兼容两种调用方式，但不能分裂成两套业务规则：

```text
插件协议调用：
  所有文件读写经 file_operation
  所有脚本执行经 script_run
  用户确认经 approval_request

本地 skill 调用测试：
  允许直接读写 project_root
  仍生成同结构 phase_complete
  仍写 session_state/checkpoint
  仍运行 schema、artifact、file_manifest 校验
```

本地测试可使用：

```json
{
  "payload": {
    "mode": "direct_test",
    "invocation_mode": "local_skill_test",
    "local_test": true,
    "source_phase": "test_only",
    "complexity": "medium"
  }
}
```

本地测试写出的文件只是直测证据，不是正式流水线产物。正式完成标准只适用于 `mode=full`、`invocation_mode=plugin_protocol`、`source_phase=upy-generate-plugin` 的 `phase_complete.payload.manifest_content.diagrams`。

本地直测和正式插件调用必须严格隔离：

- `mode=direct_test`、`invocation_mode=local_skill_test` 或 `source_phase=test_only` 时，`phase_complete.payload.result` 必须写 `partial`，并在 `warnings` 中声明 `LOCAL_TEST_ONLY`；不得使用 `success` 或非协议枚举值。
- 本地直测不得写入正式 `project-manifest.json.diagrams`，也不得在 `phase_complete.payload.manifest_content.diagrams` 中伪装正式 diagrams。直测产物只写 `phase_complete.payload.artifacts`、`file_manifest`、`checkpoints/diagram/`，或写入测试专用字段 `project-manifest.json.test_artifacts.diagram`；如需在 `manifest_content` 里记录，只能使用 `manifest_content.test_artifacts.diagram.files`。
- 正式 `success` 必须来自 `mode=full`、`invocation_mode=plugin_protocol`、`source_phase=upy-generate-plugin`，并且必须有 `source_phase_complete_path` 指向成功的 `phase_complete.upy_generate_plugin.json`。
- 如果发现已有 `docs/diagram.json`、`docs/architecture.*`、`docs/flowchart.*`、`docs/data_flow.*` 来自 `direct_test/test_only`，正式运行前必须先清理或覆盖这些产物，并重建 `diagram_file_manifest.json` 与 checkpoint；不得复用旧直测产物作为正式成功。

## 执行步骤

1. 校验 `protocol_version == "1.0"`、`phase == "upy-diagram-plugin"`、`session_id` 非空。
   - 若目标项目存在 `.upy/scripts/render_diagram_local.py`，先确认其 SHA256 与 `<resource_root>/scripts/render_diagram_local.py` 一致；不一致时用 `<resource_root>` 的脚本覆盖项目 `.upy` 副本，或直接执行 `<resource_root>/scripts/render_diagram_local.py`，不得调用旧项目副本。
2. 发送 `status_update(stage="start")`，说明正在校验上游 generate 输出。
3. 通过 `file_operation(read)` 读取 `source_phase_complete_path`。上游必须满足：
   - `type == "phase_complete"`
   - `phase == "upy-generate-plugin"`
   - `payload.result == "success"`
   - `payload.manifest_content.phase == "generate"`
4. 读取 `project-manifest.json`。正式模式通过 `file_operation(read)`，本地直测可直接读。
5. 如果 `complexity` 为 null，发送 `approval_request(approval_id="diagram_complexity")`。未收到确认不得继续。
6. 枚举并读取：
   - `firmware/**/*.py`
   - `firmware/main.py`
   - `firmware/conf.py`
   - `firmware/board.py`
   - `firmware/lib/**/*.py`
   - `firmware/drivers/**/*.py`
   - `firmware/tasks/**/*.py`
   - `test/pc/**/*.py`、`test/device/**/*.py`（存在时）
7. 写 checkpoint `diagram:after_source_read`。
8. LLM 根据 `diagram.schema.json` 生成 `{project_root}/docs/diagram.json`。必须包含 `meta`、`architecture`、`flow`、`data_flow`，可包含 `task_registry`、`diagnostics`。
9. 通过 `file_operation(write)` 写入 `docs/diagram.json`。
10. 运行 schema 校验：

```text
script_run(
  "python G:/MicroPython_Skills/upy-project-gen-toolchain-spec/scripts/validate_json.py --schema G:/MicroPython_Skills/upy-project-gen-toolchain-spec/diagram.schema.json --json <project_root>/docs/diagram.json"
)
```

11. schema 失败时，修正 `docs/diagram.json` 后重复校验。最多 3 轮，超过后输出 `phase_complete(result="failed",next_phase=null)`。
12. 写 checkpoint `diagram:after_validate_pass`。
13. 如 `render_policy.network_rendering == "ask"` 且需要 SVG/PNG，发送网络权限请求：

```text
approval_request(approval_id="diagram_network_render")
```

14. 渲染本地产物：

```text
script_run(
  "python <resource_root>/scripts/render_diagram_local.py --input <project_root>/docs/diagram.json --output <project_root>/docs/ --format all --json-summary"
)
```

正式 success 必须生成 13 个文件：

```text
docs/diagram.json
docs/architecture.md
docs/architecture.svg
docs/architecture.png
docs/architecture.html
docs/flowchart.md
docs/flowchart.svg
docs/flowchart.png
docs/flowchart.html
docs/data_flow.md
docs/data_flow.svg
docs/data_flow.png
docs/data_flow.html
```

如果用户拒绝网络或网络失败：

- 允许降级时，保留 `diagram.json`、`.md`、`.html`，输出 `partial` 和 checkpoint。
- 不允许降级时，输出 `failed`，错误码 `DIAGRAM_RENDER_NETWORK_FAILED` 或 `DIAGRAM_IMAGE_RENDER_PERMISSION_DENIED`。

15. 通过 `script_run` 或 `file_operation(list)` 收集实际生成文件。
16. 更新 `project-manifest.json` 的 `diagrams` 字段，不改变上游事实；如需记录 diagram 生成时间，只写入 `diagrams.generated_at` 或 phase_complete `timestamp`。
17. 写 session 状态：

```text
<session_root>/checkpoints/diagram/session_state.upy_diagram_plugin.json
<session_root>/diagram_file_manifest.json
```

18. 运行本插件校验：

```text
script_run(
  "python <resource_root>/scripts/diagram_manifest.py --validate-phase-complete --input <session_root>/phase_complete.upy_diagram_plugin.json --artifact-root <project_root> --session-root <session_root>"
)
```

`--artifact-root` 必须指向项目根目录，用于核对 `file_manifest.files[]` 声明的文件是否真实存在、`bytes` 是否匹配、`sha256` 是否匹配。缺少 `--artifact-root` 时脚本只做协议结构校验，不能作为最终成功验收依据。

19. 输出 `phase_complete`。

## complexity 约束

`complexity` 控制图的可读性上限：

| 参数 | simple | medium 默认 | full |
|---|---:|---:|---:|
| `architecture` 总模块数 | 6 | 10 | 16 |
| 每层模块数 | 2 | 4 | 6 |
| `cross_layer_deps` 总边数 | 6 | 12 | 20 |
| `flow[]` 总步数 | 5 | 8 | 14 |
| `data_flow[]` 总边数 | 2 | 4 | 8 |

LLM 必须主动合并相近模块、步骤或数据流，避免超出约束。`diagnostics` 中要记录实际模块数、依赖边数、最大深度、循环依赖、孤立模块和 direct machine access。

`data_flow[].data` 和 `data_flow[].rate` 必须保持短标签，不要写完整表达式、长句或 Mermaid 敏感分隔符。避免在边标签里直接使用 ASCII `()`、`/`、`@`、`|`、`==`、箭头符号或代码片段；优先写成 `button press`、`poll 50ms`、`30ms chunk` 这类短文本。渲染脚本仍必须做最终转义、清洗和截断，防止 mermaid.ink 对 SVG/PNG 返回 400。

`diagnostics.total_modules` 必须等于 `architecture.layers[].modules` 的实际模块数量；如果为了可读性合并了模块，按合并后的图中模块计数，并在模块 `role` 或 `diagnostics` 说明合并依据。

## checkpoint / resume

每个可恢复边界都要定义 checkpoint：

| checkpoint | 生成时机 | resume 行为 |
|---|---|---|
| `input_loaded` | 读取上游 manifest 和 runtime_context 后 | 继续读取源码 |
| `source_read` | firmware 源码读取完成后 | 复用源码摘要，继续生成 diagram.json |
| `diagram_json_written` | `docs/diagram.json` 写入后 | 从校验开始 |
| `diagram_json_validated` | schema 校验通过后 | 从渲染开始 |
| `artifacts_rendered_partial` | 部分渲染成功后 | 只补跑缺失文件 |
| `manifest_updated` | manifest 写回后 | 直接输出 phase_complete |
| `phase_completed` | phase_complete 已输出 | 幂等返回已有结果 |

`partial`、`failed` 和 `cancelled` 结果必须包含 `payload.checkpoint_info`：

```json
{
  "checkpoint": {
    "checkpoint_id": "diagram_json_written",
    "resume_phase": "upy-diagram-plugin",
    "resume_step": "validate",
    "resume_label": "继续校验并渲染架构图",
    "resume_from": {
      "diagram_json": "docs/diagram.json",
      "project_root": "sessions/<session_id>/project"
    }
  }
}
```

恢复时必须优先使用 checkpoint 指向的 artifact，不能重新从自然语言或旧对话推断。

## cancellation / retry / timeout

- 用户取消时输出 `phase_complete(result="cancelled", next_phase=null)`。
- 取消发生在源码读取或 JSON 生成后时，保留已写产物，返回 `partial + checkpoint`。
- 同一 `idempotency_key` 的重复 `file_operation(write)` 应覆盖同一目标文件，不生成随机新文件。
- 同一 `idempotency_key` 的重复 `script_run(render)` 应识别已存在文件，并以 `--json-summary` 汇报实际文件状态。
- 校验修复最多 3 轮；超过后返回 structured error。
- 网络渲染失败最多重试 2 次；仍失败则 partial 或 failed。

建议 timeout：

| 动作 | timeout |
|---|---:|
| `file_operation(read firmware list)` | 10000 ms |
| `file_operation(read single file)` | 5000 ms |
| `file_operation(write diagram.json)` | 5000 ms |
| `script_run(validate_json.py)` | 15000 ms |
| `script_run(render_diagram_local.py --format all)` | 90000 ms |
| `file_operation(write project-manifest.json)` | 5000 ms |

## permission prompts

Diagram 阶段通常需要：

| 权限 | 是否需要 | 说明 |
|---|---|---|
| 文件读取 | 是 | 读取 manifest 和 firmware 源码 |
| 文件写入 | 是 | 写 docs 和 project-manifest.json |
| 脚本执行 | 是 | validate 和 render |
| 网络访问 | 条件需要 | mermaid.ink 渲染 SVG/PNG |
| 设备访问 | 否 | diagram 阶段不得发 `device_command` |

如果宿主要求显式授权，必须用 `permission_request` 或等价 `approval_request`，并把范围写清楚：

```text
读取：project-manifest.json, firmware/**/*.py
写入：docs/diagram.json, docs/architecture.*, docs/flowchart.*, docs/data_flow.*, project-manifest.json
脚本：scripts/diagram_manifest.py, scripts/render_diagram_local.py, validate_json.py
网络：mermaid.ink
```

## structured errors

`errors` 必须是对象数组：

```json
{
  "code": "DIAGRAM_RENDER_TIMEOUT",
  "message": "渲染 Mermaid 图超时",
  "step_id": "render",
  "severity": "error",
  "retryable": true,
  "recoverable": true,
  "idempotency_key": "upy-diagram-plugin:<session_id>:render:v1",
  "artifact_refs": ["docs/diagram.json"],
  "suggested_actions": ["重试渲染", "只保留 Markdown/HTML 输出", "稍后从 checkpoint 继续"]
}
```

必须覆盖这些错误码：

```text
DIAGRAM_INPUT_MISSING
DIAGRAM_PROTOCOL_UNSUPPORTED
DIAGRAM_CAPABILITY_MISSING
DIAGRAM_PERMISSION_DENIED
DIAGRAM_SOURCE_READ_FAILED
DIAGRAM_JSON_INVALID
DIAGRAM_VALIDATE_FAILED
DIAGRAM_RENDER_TIMEOUT
DIAGRAM_RENDER_NETWORK_FAILED
DIAGRAM_MANIFEST_UPDATE_FAILED
DIAGRAM_CANCELLED
DIAGRAM_IDEMPOTENCY_CONFLICT
```

## phase_complete 成功形态

成功输出必须满足：

- `type == "phase_complete"`
- `phase == "upy-diagram-plugin"`
- `payload.phase == "upy-diagram-plugin"`
- `payload.result == "success"`
- `payload.mode == "full"`
- `payload.invocation_mode == "plugin_protocol"`
- `payload.local_test != true`
- `payload.source_phase == "upy-generate-plugin"`
- `payload.source_phase_complete_path` 指向成功的 `phase_complete.upy_generate_plugin.json`
- `payload.next_phase == null`
- `payload.manifest_content.diagrams` 包含 13 个文件路径和 `generated_at`
- `payload.artifacts` 包含 13 个文件 artifact
- `payload.file_manifest.files[]` 声明 13 个文件，包含 `path`、`type`、`required`、`bytes`、`sha256`
- `payload.checks.diagram_schema.ok == true`
- `payload.checks.render_diagram.ok == true`
- `payload.session_state.checkpoint == "phase_completed"`
- `payload.errors == []`

## 脚本资源

本 skill 自带：

```text
scripts/render_diagram_local.py
scripts/diagram_manifest.py
```

`render_diagram_local.py` 从旧 `upy-diagram` 复制并补充 `--json-summary`。运行 `--format md` 或 `--format html` 不需要网络；运行 `--format svg/png/all` 可能访问 mermaid.ink。

`diagram_manifest.py` 用于本地测试和插件宿主校验：

```text
python scripts/diagram_manifest.py --validate-phase-complete --input <phase_complete.json> --artifact-root <project_root> --session-root <session_root>
python scripts/diagram_manifest.py --build-file-manifest --artifact-root <project_root> --output <session_root>/diagram_file_manifest.json
```

## 本地验收

实现或修改本 skill 后至少运行：

```text
python test/smoke_tests.py
```

测试必须覆盖：

- `SKILL.md` frontmatter 和关键协议文本。
- `.codex-plugin/plugin.json` 可验证。
- sample JSON 的 phase、result、checkpoint、errors、file_manifest 结构。
- `diagram.sample.json` 能通过 `diagram.schema.json`。
- `render_diagram_local.py --format md --json-summary` 能生成 Markdown 并输出 JSON 摘要。
- `diagram_manifest.py` 能校验 success、partial、cancelled、timeout、permission_denied、capability_unavailable 样例。
- `diagram_manifest.py` 必须拒绝直测 success、直测缺少 `LOCAL_TEST_ONLY`、直测使用正式 `manifest_content.diagrams`、非成功结果缺少 `checkpoint_info`、sidecar manifest 与 `payload.file_manifest` 不一致。
