---
name: upy-wiring-plugin
description: 插件化 MicroPython 接线图生成阶段。用于收到 upy-generate-plugin success 的 optional_next_phases 选择后，读取生成后的 firmware 与 project-manifest.json，生成 docs/wiring.json，校验 schema，渲染 wiring.md/svg/png/html/wiring_pins.md，并输出 phase_complete；这是可选产物阶段，不覆盖主 deploy 链路。
---

# upy-wiring-plugin 插件化工作流

`upy-wiring-plugin` 是“一句话造硬件”流水线的可选接线图产物阶段。它迁移自旧 `G:\MicroPython_Skills\upy-wiring`，但必须把本地 I/O 改成插件协议：

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
  -> optional_next_phases includes upy-wiring-plugin
  -> user selects wiring artifacts
  -> upy-wiring-plugin
```

`upy-wiring-plugin` 不应改变主链路：

```text
upy-generate-plugin -> upy-deploy-plugin
```

也就是说，wiring 是可选附加产物阶段，`phase_complete.payload.next_phase` 默认必须是 `null`。

## 边界规则

- 不覆盖旧 `G:\MicroPython_Skills\upy-wiring`。
- 不覆盖或改名 `G:\MicroPython_Skills\upy-deploy`、`G:\MicroPython_Skills\upy-deploy-plugin`。
- 不在 wiring 阶段新增硬件、替换 MCU、改变 pinout 或修改 firmware 业务代码。
- 不执行 mpremote、烧录、串口调试或设备端测试。
- 不把 wiring 作为 deploy 的必经阶段。
- 不让插件端理解 MicroPython 硬件语义；LLM 负责理解，脚本负责校验和渲染。

## 数据权威顺序

生成 `docs/wiring.json` 时必须按以下优先级判断事实：

```text
firmware/ 实际代码 > project-manifest.json > LLM 推断
```

其中：

- `firmware/main.py` 的 `I2C(...)`、`SPI(...)`、`UART(...)`、`Pin(...)` 是最高优先级连接事实。
- `firmware/board.py` 的固定板载引脚、总线默认映射必须参与补全。
- `firmware/drivers/*/__init__.py` 的默认地址或 factory 参数用于确认 I2C 地址。
- `firmware/conf.py` 用于确认项目名、板卡名和配置常量。
- `firmware/tasks/*.py` 与 `firmware/lib/*.py` 用于补查额外引脚或硬编码地址。
- `project-manifest.json` 是设计意图和上游硬件选择记录，但与 firmware 冲突时以 firmware 为准并生成 alerts。Wiring 阶段只允许补充/更新 `wiring` 字段，不得修改根级 `updated_at`。

## start_phase 输入

正式模式必须从 `upy-generate-plugin` 的 success phase_complete 启动：

```json
{
  "protocol_version": "1.0",
  "type": "start_phase",
  "phase": "upy-wiring-plugin",
  "session_id": "uuid",
  "idempotency_key": "upy-wiring-plugin:<session_id>:full:v1",
  "payload": {
    "mode": "full",
    "source_phase": "upy-generate-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_generate_plugin.json",
    "runtime_context": {
      "session_root": "sessions/<session_id>",
      "project_root": "sessions/<session_id>/project",
      "file_operation_root": "sessions/<session_id>/project",
      "resource_root": "upy-wiring-plugin"
    },
    "invocation_mode": "plugin_protocol",
    "local_test": false,
    "capabilities": {
      "approval_request": true,
      "file_operation": true,
      "script_run": true,
      "checkpoint_resume": true,
      "cancellation": true,
      "retry": true,
      "timeout": true,
      "permission_prompt": true
    },
    "render_policy": {
      "formats": ["json", "md", "html", "pins", "svg", "png"],
      "network_rendering": "ask",
      "timeout_ms": 30000
    }
  }
}
```

迁移期允许 `mode=direct_test`，但必须记录 `source=test_only`。如果缺少完整 firmware 或 generate phase_complete，不能输出正式 success。

## 协议字段语义

这些字段必须按同一语义用于插件协议调用和本地 skill 调用测试：

| 字段 | 含义与约束 |
|---|---|
| `protocol_version` | 协议版本。当前只接受 `"1.0"`；不支持时输出 `PROTOCOL_UNSUPPORTED`，不得继续执行。 |
| `type` | 消息类型，如 `start_phase`、`status_update`、`approval_request`、`phase_complete`。插件按它路由。 |
| `phase` | 必须统一为 `upy-wiring-plugin`。不得混用 `wiring`、`upy-wiring`。 |
| `session_id` | 一次用户工作流的稳定 ID。checkpoint、resume、retry、artifact 归档和日志追踪都依赖它。 |
| `idempotency_key` | 幂等键。同一 session/phase/mode/attempt 的重试应保持稳定，避免重复写 artifact 或重复推进状态。 |
| `payload.mode` | `full` 是正式插件链路；`direct_test` 是本地 skill 测试链路，不能伪装成正式 success。 |
| `payload.invocation_mode` | `plugin_protocol` 表示文件/脚本/确认都走协议工具；`local_skill_test` 表示本地测试可直接读写项目根目录。 |
| `payload.source_phase` | 正式链路必须是 `upy-generate-plugin`；本地测试可为 `test_only`。 |
| `payload.source_phase_complete_path` | 上游 generate phase_complete 路径，用于证明 firmware 已生成且硬件事实来自 generate 输出。 |
| `payload.source_phase_complete` | 可选内联上游结果。若同时存在 path 和内联对象，必须以 path 读取结果为准并校验一致性。 |
| `runtime_context.session_root` | 当前 session 的状态、checkpoint、phase_complete、日志和临时结果根目录。 |
| `runtime_context.project_root` | 用户项目根目录。`project-manifest.json`、`firmware/`、`docs/` 都应在这里。 |
| `runtime_context.file_operation_root` | 插件允许读写的文件边界。任何 file write 都必须落在该目录内。 |
| `runtime_context.resource_root` | 插件资源根目录，例如 `upy-wiring-plugin`，用于定位脚本。 |
| `capabilities` | 能力协商结果。正式模式缺少 `file_operation`、`script_run` 或 `approval_request` 时不得继续。 |
| `render_policy.formats` | 请求产物格式。正式 success 必须包含 `json/md/html/pins/svg/png`。 |
| `render_policy.network_rendering` | 网络渲染策略：`ask`、`allow`、`deny`。`deny` 时必须先尝试本地 renderer。 |
| `render_policy.timeout_ms` | 单次 SVG/PNG 渲染超时，默认 30000ms。 |
| `checks` | 结构化校验结果。每个 check 建议包含 `ok`、`command`、`duration_ms`、`error_code`。 |
| `artifacts` | 面向 UI 和用户展示的产物列表。记录 type、path、required、sha256、bytes、generated_at。 |
| `file_manifest` | 面向恢复、验收和幂等去重的文件清单。比 artifacts 更偏文件系统证据。 |
| `errors` | 结构化错误数组。不得只写自然语言字符串。 |
| `warnings` | 非阻塞告警数组。SVG/PNG 缺失在正式模式不是 warning，应导致 partial。 |

## 插件调用与本地 skill 测试

`upy-wiring-plugin` 必须兼容两种调用方式，但不能分裂成两套业务规则：

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
    "source_phase": "test_only"
  }
}
```

## 执行步骤

1. 发送 `status_update(stage="start")`，说明正在校验上游 generate 输出。
2. 通过 `file_operation(read)` 读取 `source_phase_complete_path`。上游必须满足：
   - `type == "phase_complete"`
   - `phase == "upy-generate-plugin"`
   - `payload.result == "success"`
   - `payload.manifest_content.phase == "generate"`
3. 通过 `file_operation(read)` 读取 `{project_root}/project-manifest.json`。
4. 通过 `file_operation(list)` 枚举并读取：
   - `firmware/**/*.py`
   - `firmware/drivers/**/__init__.py`
   - `firmware/conf.py`
   - `firmware/board.py`
   - `firmware/main.py`
5. LLM 根据旧 `upy-wiring` 的规则生成 `{project_root}/docs/wiring.json`。必须包含 `meta`、`mcu`、`buses`、`standalone`、`power`、`alerts`。
6. 通过 `file_operation(write)` 写入 `docs/wiring.json`。
7. 运行确定性 topology 派生脚本，用 `project-manifest.json pinout` 补齐或覆盖 `components[]`、`connections[]`、`buses[]`：

```text
script_run(
  "python <resource_root>/scripts/derive_wiring_topology.py --wiring <project_root>/docs/wiring.json --manifest <project_root>/project-manifest.json --upstream <session_root>/phase_complete.upy_generate_plugin.json --output <project_root>/docs/wiring.json"
)
```

如果 manifest 中存在 I2S/SPI/I2C/UART 多线接口或任何非 middleware 硬件模块，这一步是强制步骤，不得跳过。LLM 可以生成初稿，但最终 `components[]`、`connections[]` 和 I2S `buses[]` 必须以 `project-manifest.json pinout` 为准。

8. 运行 schema 校验：

```text
script_run(
  "python G:/MicroPython_Skills/upy-project-gen-toolchain-spec/scripts/validate_json.py --schema G:/MicroPython_Skills/upy-project-gen-toolchain-spec/wiring.schema.json --json <project_root>/docs/wiring.json"
)
```

9. schema 失败时，修正 `docs/wiring.json` 后重复执行 topology 派生和 schema 校验。无法修正则输出 `phase_complete(result=partial,next_phase=null)`。
10. 渲染本地产物：

```text
script_run(
  "python <resource_root>/scripts/render_wiring_local.py --input <project_root>/docs/wiring.json --output <project_root>/docs/ --format all --network-rendering <ask|allow|deny> --timeout-ms <timeout_ms>"
)
```

正式 success 必须生成 `wiring.svg` 和 `wiring.png`。推荐渲染降级链：

```text
优先：本地 Mermaid CLI / mmdc / 可用本地 renderer
  -> 失败后：请求用户允许 mermaid.ink 网络渲染
  -> 仍失败：phase_complete(result=partial,next_phase=null)
```

如果 `render_policy.network_rendering=deny`，不能直接放弃图片产物，应先尝试本地 renderer。没有本地 renderer 且用户拒绝网络时，输出 `partial`，错误码 `WIRING_IMAGE_RENDER_PERMISSION_DENIED`。

11. 通过 `script_run` 或 `file_operation(list)` 收集实际生成文件。
12. 更新 `project-manifest.json` 的 `wiring` 字段，不改变 `mcu`、`board`、`devices`、`pinout`、`generate`、根级 `updated_at` 等上游事实；如需记录 wiring 生成时间，只写入 `wiring.generated_at` 或 phase_complete `timestamp`。
13. 运行本插件校验：

```text
script_run(
  "python <resource_root>/scripts/wiring_manifest.py --validate-phase-complete --input <session_root>/phase_complete.upy_wiring_plugin.json --artifact-root <project_root> --session-root <session_root>"
)
```

`--artifact-root` 必须指向项目根目录，用于核对 `file_manifest.files[]` 声明的文件是否真实存在、`bytes` 是否匹配、`sha256` 是否匹配。缺少 `--artifact-root` 时脚本只做协议结构校验，不能作为最终成功验收依据。

14. 输出 `phase_complete`。

## wiring.json 生成规则

`docs/wiring.json` 必须符合：

```text
G:/MicroPython_Skills/upy-project-gen-toolchain-spec/wiring.schema.json
```

接线图必须采用“元器件级、引脚级标注的电气接线拓扑图”（component-level pin-annotated wiring topology diagram）表达：

- MCU、音频放大器、麦克风、LED、按键、传感器等实际硬件模块必须渲染为独立组件框。
- 每一条真实信号线、电源线和地线都应作为独立连接边显示。
- 连接边必须标注 MCU GPIO、MCU 端信号角色、外设端引脚名和必要方向，例如 `GPIO14 / I2S1 BCK -> BCLK`。
- 主图不得把长文字直接放在 Mermaid edge label 上；必须使用中间 `net_*` 标签节点表达 `GPIO14 I2S1 BCK -> MAX98357.BCLK` 这类短标签，避免多条边文字互相遮挡。
- 主图不得渲染 `alerts_sg` 或注意事项子图；注意事项只放在 `wiring_pins.md` 或 HTML 说明区，不得挤占 `wiring.svg/png` 的接线主体。
- SVG/PNG 必须使用白色或浅色背景，不得依赖透明背景，否则在黑色查看器里连线和文字不可读。
- I2S、SPI、I2C、UART 等多线接口可以视觉分组为总线，但必须保留每根线的 pin-to-pin 映射。
- 不得把多引脚外设压缩成 `standalone.pin="14,32,33"` 这类逗号字符串；必须使用 `components[]` + `connections[]`，或在 `buses[]` 中提供设备侧 `pins[]` 映射。

关键字段：

- `meta.project`：项目名称。
- `meta.generated_at`：真实 ISO 8601 时间，不能用样例占位时间。
- `meta.source_phase`：正式链路使用 `generate`。
- `mcu.pins[]`：包括实际使用 GPIO、电源脚、地脚和板载固定引脚。
- `components[]`：元器件级节点。推荐包含 MCU、外设模块、LED、按键、电源相关模块。
- `connections[]`：真实电气连接。每项表示一根线，必须包含 `from.component/from.pin` 和 `to.component/to.pin`。
- `buses[]`：I2C/SPI/UART/OneWire/CAN/I2S 总线。用于协议分组和兼容旧渲染器，不得替代 `connections[]` 的 pin-to-pin 事实。
- 当 `project-manifest.json pinout` 中存在 `i2s_*` 记录时，success 必须包含对应 I2S 元器件组件、I2S bus，以及每根 `i2s_bck/i2s_ws/i2s_data_in/i2s_data_out` 的 MCU GPIO 到外设引脚连接；否则必须修正或输出 partial。
- `standalone[]`：LED、蜂鸣器、按钮、继电器等单引脚独立 GPIO 器件。只允许单引脚，不能用于 I2S 音频模块等多引脚元器件。
- `power[]`：3.3V、5V、Vin、GND 供电关系。
- `alerts[]`：冲突、安全、电源、上拉、限流等提示。

告警 `msg` 必须简短，建议不超过 60 个英文字符，避免接线图布局被撑开。

## phase_complete 输出

成功时必须输出：

```json
{
  "type": "phase_complete",
  "phase": "upy-wiring-plugin",
  "payload": {
    "phase": "upy-wiring-plugin",
    "result": "success",
    "next_phase": null,
    "source_phase": "upy-generate-plugin",
    "source_phase_complete_path": "sessions/<session_id>/phase_complete.upy_generate_plugin.json",
    "manifest_content": {
      "phase": "wiring",
      "wiring": {
        "json": "docs/wiring.json",
        "md": "docs/wiring.md",
        "html": "docs/wiring.html",
        "pins": "docs/wiring_pins.md",
        "svg": "docs/wiring.svg",
        "png": "docs/wiring.png"
      }
    },
    "artifacts": [
      {"type": "wiring_json", "path": "docs/wiring.json"},
      {"type": "wiring_markdown", "path": "docs/wiring.md"},
      {"type": "wiring_html", "path": "docs/wiring.html"},
      {"type": "wiring_pins", "path": "docs/wiring_pins.md"}
    ],
    "checks": {
      "wiring_schema": {"ok": true},
      "render_wiring": {"ok": true},
      "manifest_update": {"ok": true}
    },
    "render_result": {
      "json": {"ok": true, "path": "docs/wiring.json"},
      "md": {"ok": true, "path": "docs/wiring.md"},
      "html": {"ok": true, "path": "docs/wiring.html"},
      "pins": {"ok": true, "path": "docs/wiring_pins.md"},
      "svg": {"ok": true, "path": "docs/wiring.svg", "backend": "local_mermaid"},
      "png": {"ok": true, "path": "docs/wiring.png", "backend": "local_mermaid"}
    },
    "file_manifest": {
      "path": "sessions/<session_id>/wiring_file_manifest.json",
      "files": []
    },
    "session_state": {
      "path": "sessions/<session_id>/session_state.upy_wiring_plugin.json",
      "checkpoint": "phase_completed"
    },
    "warnings": [],
    "errors": []
  }
}
```

`result=success` 的硬门槛：

- `docs/wiring.json` 存在且 schema 校验通过。
- `docs/wiring.md` 存在。
- `docs/wiring.html` 存在。
- `docs/wiring_pins.md` 存在。
- `docs/wiring.svg` 存在。
- `docs/wiring.png` 存在。
- `payload.next_phase == null`。
- `payload.manifest_content.wiring` 记录已生成 artifact。
- `payload.artifacts[]` 覆盖成功生成的 wiring 输出。
- `payload.file_manifest.files[]` 覆盖所有必需 artifact，并记录 `required=true`、`sha256`、`bytes`、`source`、`checkpoint`。
- `payload.session_state.checkpoint == "phase_completed"`。

`result=partial` 的常见情况：

- 上游 generate phase_complete 缺失或不是 success。
- firmware 源码不完整。
- `wiring.json` 无法通过 schema。
- firmware 与 manifest 存在阻塞级冲突，需要用户确认。
- SVG/PNG 渲染失败、超时或被拒绝。

partial/failed 必须设置 `next_phase=null`，并写入 `errors` 或 `warnings`。

## 用户确认点

如需网络渲染 SVG/PNG，先发：

```text
approval_request(approval_id="wiring_network_render")
```

用户选项：

- `render_all`：允许 mermaid.ink/CDN，生成 md/html/pins/svg/png。
- `local_only`：只允许本地 renderer；若本地无法生成 SVG/PNG，输出 partial。
- `cancel`：停止 wiring，输出 partial。

如果 firmware 与 manifest 出现 GPIO、地址或电源冲突，应发：

```text
approval_request(approval_id="wiring_conflict_review")
```

用户确认前不得把冲突隐藏为 success。

## 脚本

- `scripts/render_wiring_local.py`：从旧 `upy-wiring` 迁移来的渲染器。输入 `docs/wiring.json`，输出 wiring Markdown、HTML、SVG、PNG 和 pin table。
- `scripts/derive_wiring_topology.py`：从 `project-manifest.json pinout` 派生元器件级 topology，强制生成 `components[]`、`connections[]` 和 I2S/I2C/SPI/UART bus 映射。
- `scripts/wiring_manifest.py`：校验 start_phase、上游 generate phase_complete、wiring phase_complete 和产物路径契约。

## Session、Checkpoint、Retry、Cancel 和 Timeout

每次运行都应写入：

```text
<session_root>/session_state.upy_wiring_plugin.json
<session_root>/wiring_file_manifest.json
```

推荐 checkpoint：

| checkpoint | 含义 | 可恢复动作 |
|---|---|---|
| `started` | start_phase 已接收 | 重新校验输入 |
| `upstream_validated` | generate phase_complete 已验证 | 继续读项目文件 |
| `inputs_read` | manifest 和 firmware 已读取 | 重新派生 wiring.json |
| `wiring_json_written` | wiring.json 已写入 | 继续 schema 校验 |
| `wiring_json_validated` | schema 已通过 | 继续渲染 |
| `artifacts_rendered` | wiring 产物已生成 | 继续 manifest 更新和 file manifest |
| `manifest_updated` | project-manifest wiring 字段已更新 | 继续 phase_complete |
| `phase_completed` | phase_complete 已输出 | 幂等返回已有结果 |
| `cancelled` | 用户取消 | 不自动继续 |
| `failed` | 阻塞失败 | retry 时从 last_ok_artifact 恢复 |

恢复规则：

- `checkpoint=phase_completed` 且 phase_complete 校验通过时，retry 直接返回已有结果。
- `docs/wiring.json` 存在且 schema 通过时，从渲染阶段恢复，不重新解析 firmware。
- SVG 已存在但 PNG 缺失时，只重试 PNG 渲染。
- retry 必须复用原 `session_id` 和稳定 `idempotency_key`，并增加 `attempt`。
- timeout 必须写入 `last_error` 和当前 checkpoint。
- cancellation 必须输出 `CANCELLED_BY_USER`，`next_phase=null`。

## Capability Negotiation 和权限提示

正式插件模式必须具备：

```json
{
  "capabilities": {
    "approval_request": true,
    "file_operation": true,
    "script_run": true,
    "checkpoint_resume": true,
    "cancellation": true,
    "retry": true,
    "timeout": true,
    "permission_prompt": true
  }
}
```

缺少能力时：

| 缺少能力 | 处理 |
|---|---|
| `file_operation` | 正式模式不能执行，输出 `CAPABILITY_UNAVAILABLE` |
| `script_run` | 不能校验或渲染，输出 `CAPABILITY_UNAVAILABLE` |
| `approval_request` | 不能请求网络渲染或冲突确认，默认保守 partial |
| `checkpoint_resume` | 可以 direct_test，但正式模式不建议 success |
| `cancellation` | 必须告知不可取消，长任务仍需 timeout |
| `permission_prompt` | 不能执行需要授权的写文件、脚本或网络操作 |

权限提示范围：

- `file_operation(read)`：读取 `project-manifest.json`、`firmware/**/*.py`、上游 phase_complete。
- `file_operation(write)`：写入 `docs/wiring.*`、`project-manifest.json` 的 wiring 字段、session_state、file_manifest；不得因 wiring 阶段改写 `project-manifest.json` 根级 `updated_at`。
- `script_run`：只允许白名单脚本 `validate_json.py`、`derive_wiring_topology.py`、`render_wiring_local.py`、`wiring_manifest.py`。
- `network_rendering`：生成 SVG/PNG 前必须明确是否访问 mermaid.ink 或 CDN。
- `device_command`：本 phase 不需要；如果收到设备命令请求，应拒绝。

## 结构化错误

错误对象统一使用：

```json
{
  "code": "WIRING_SCHEMA_INVALID",
  "severity": "blocking",
  "retryable": false,
  "message": "docs/wiring.json failed schema validation",
  "details": {
    "path": "docs/wiring.json",
    "validator": "wiring.schema.json"
  },
  "checkpoint": "wiring_json_written",
  "next_action": "fix wiring.json and rerun schema validation"
}
```

常用错误码：

| 错误码 | 场景 |
|---|---|
| `PROTOCOL_UNSUPPORTED` | `protocol_version` 不支持 |
| `CAPABILITY_UNAVAILABLE` | 缺少必要协议能力 |
| `UPSTREAM_PHASE_MISSING` | generate phase_complete 缺失 |
| `UPSTREAM_PHASE_INVALID` | 上游不是 success 或 manifest 不完整 |
| `PROJECT_MANIFEST_MISSING` | 项目 manifest 缺失 |
| `FIRMWARE_NOT_FOUND` | firmware 源码缺失 |
| `WIRING_SCHEMA_INVALID` | wiring.json schema 失败 |
| `WIRING_CONFLICT_REQUIRES_REVIEW` | firmware 与 manifest 冲突需用户确认 |
| `WIRING_IMAGE_RENDER_PERMISSION_DENIED` | 用户拒绝网络且无本地 renderer |
| `WIRING_IMAGE_RENDER_TIMEOUT` | SVG/PNG 渲染超时 |
| `WIRING_IMAGE_RENDER_FAILED` | SVG/PNG 渲染失败 |
| `FILE_PERMISSION_DENIED` | 文件读写权限被拒绝 |
| `SCRIPT_PERMISSION_DENIED` | 脚本执行权限被拒绝 |
| `CANCELLED_BY_USER` | 用户取消 |
| `IDEMPOTENCY_CONFLICT` | 同一 idempotency key 对应输入已变化 |

## 最终检查

输出最终 response 前，至少确认：

- 没有覆盖旧 `upy-wiring`。
- 没有覆盖 deploy 相关目录。
- `phase_complete.payload.next_phase` 是 `null`。
- 所有声明的 artifacts 均可解释为 wiring 产物。
- 若 success 声明了 SVG/PNG，则实际渲染成功或有明确证据。

