# MPOS 六舵机语音机器人 Skill 规范

## 1. 目标

提供一个独立的机器人 Skill，用于生成、配置、测试和部署无摄像头、六路直连 PWM 舵机、I2S 麦克风与扬声器、机器人自主联网访问 ASR、LLM、TTS 的 MicroPythonOS App。

本规范同时覆盖两种调用方式：

- 本地直接调用 Skill 进行生成、测试、打包和设备验证。
- 浏览器由其他项目实现的网站调用本 Skill 协议；本 Skill 不包含前端或后端代码。

两种入口必须共享同一套模板、校验脚本、结果 Schema、Session、Checkpoint、Artifact Manifest 和结构化错误语义。不得分别维护两套机器人实现。

本 Skill 与其他 MPOS Skill、mpos-*-web Skill 及 micropythonos-ai-app-builder 没有调用、协议或部署依赖。

## 2. 非目标

- 不修改 MicroPythonOS 通用硬件 API 以适配单一机器人。
- 不复用或扩展 micropythonos-ai-app-builder。
- 不要求安装或调用其他 MPOS 相关 Skill。
- 不开放任意生成 App 直接访问 machine.Pin、machine.PWM 或 machine.I2S。
- 不使用摄像头，也不生成摄像头相关功能。
- 不让 LLM 返回或执行任意 Python、GPIO 编号、PWM 占空比。
- 不把浏览器或 AI App Builder 后端作为机器人运行时的 ASR、LLM、TTS 代理。
- 不在构建产物、Artifact、日志或后端 Session 中保存 Wi-Fi、ASR、TTS、LLM 密钥。

## 3. 总体架构

    本地 Skill Runner ─────┐
                           ├─ 独立协议与 Session 服务 ─→ 共用机器人核心脚本与模板
    外部网站及其后端 ─────┘

    机器人运行时：
    麦克风 → Wi-Fi ASR → Wi-Fi LLM → 动作校验 → 舵机动作 + Wi-Fi TTS → 扬声器

### 3.1 本地调用

本地 Runner 负责理解需求、创建或恢复 Session、调用共用脚本、请求权限、生成阶段结果并运行本地测试。

### 3.2 浏览器调用

网站及其后端由其他项目实现。它们可以提供 Session 创建、状态查询、事件流、Resume、Retry、Cancel、权限决策、Artifact 下载和受控设备操作接口，但不属于本 Skill 的交付范围。

外部网站与本地 Runner 必须调用同一个协议模型。文件、脚本、依赖、串口和设备副作用由调用方的受控 Runner 或经过授权的浏览器设备桥执行。

## 4. Skill 组织

建议作为一个独立 Skill 项目实现：

    mpos-robot-app/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    ├── assets/
    │   └── six-servo-voice-robot/
    │       ├── default_hardware_profile.json
    │       └── robot_runtime/
    │           ├── servo_controller.py
    │           ├── motion_planner.py
    │           ├── audio_session.py
    │           ├── i2s_mic_codec.py
    │           ├── i2s_speaker.py
    │           ├── xfyun_asr_adapter.py
    │           ├── xfyun_tts_adapter.py
    │           ├── llm_adapter.py
    │           ├── conversation_orchestrator.py
    │           ├── action_executor.py
    │           └── safety_guard.py
    ├── references/
    │   ├── hardware-profile.md
    │   ├── conversation-protocol.md
    │   ├── action-schema.md
    │   ├── dependencies.md
    │   └── session-protocol.md
    └── scripts/
        ├── instantiate_template.py
        ├── validate_hardware_profile.py
        ├── validate_action_plan.py
        ├── validate_artifacts.py
        ├── validate_protocol.py
        ├── resolve_upypi_dependencies.py
        ├── install_mip_dependencies.py
        └── run_local_pipeline.py

不要创建额外的 README、快速入门或安装指南。核心流程放在 SKILL.md，详细协议放在 references，项目自有的固定输出代码放在 assets，确定性操作放在 scripts。第三方驱动源码不得放入 assets、模板或 Skill 快照。

## 5. SKILL.md 核心要求

SKILL.md 应保持简短，使用指令式语句，至少明确：

1. 识别六舵机语音机器人需求。
2. 读取调用模式、协议输入、硬件配置和能力集合。
3. 复制固定机器人模板，禁止重新生成底层硬件实现。
4. 仅生成 UI、人物设定、姿势、动作组合和业务行为。
5. 校验硬件配置、依赖、动作 Schema、凭据隔离和 MicroPython 兼容性。
6. 在每个阶段提交 Result、Checkpoint 和 Artifact Manifest。
7. 在文件、脚本、依赖和设备操作前进入权限流程。
8. 支持恢复、重试、取消、超时和结构化错误上报。
9. 输出可供外部网站或本地 Runner 使用的同一协议对象，不生成网站代码。
10. 通过 uPyPI 接口解析外部驱动，并在部署时使用 MIP 安装，不复制驱动源码。

建议 Frontmatter：

    ---
    name: mpos-robot-app
    description: Generate, configure, test, package, and deploy MicroPythonOS apps for a camera-free six-servo voice robot using direct PWM, I2S audio, device-side Wi-Fi ASR/LLM/TTS, persistent hardware profiles, structured robot actions, uPyPI runtime dependencies, and resumable standalone sessions. Use for local invocation or calls relayed by an independently implemented website host.
    ---

## 6. 生成权限边界

| 内容 | 处理方式 |
| --- | --- |
| 舵机 PWM、运动插值、安全限制 | 固定模板，不允许模型重写 |
| 音频资源仲裁、I2S 收发 | 固定模板，不允许模型重写 |
| ASR、TTS、LLM 适配器 | 项目自有适配层固定；第三方驱动通过 uPyPI 安装 |
| GPIO、校准、反向、速度 | 用户配置，保存前校验 |
| 姿势、动作组合、人物设定 | 允许模型生成 |
| LVGL 页面和业务功能 | 允许模型生成 |
| 任意 Python、原始 GPIO/PWM 动作 | 禁止 LLM 返回和执行 |

生成结束后必须验证项目自有 robot_runtime 文件哈希，发现修改时返回 ROBOT_TEMPLATE_MODIFIED。该哈希范围不得包含 uPyPI 驱动文件、驱动下载缓存或驱动源码副本。

## 7. 默认硬件 Profile

唯一默认目标板为 Waveshare ESP32-S3-Touch-LCD-2，MicroPythonOS 板级 ID 为 `waveshare_esp32_s3_touch_lcd_2`，显示器为 ST7789 240×320、触摸为 CST816S。不得与 Waveshare 2.1、2.8、2.8B 或 2.8C 混用。

默认 Profile 名称为 no_camera_six_servo_voice。

### 7.1 默认舵机映射

| 舵机编号 | 逻辑关节 | 默认 GPIO |
| --- | --- | ---: |
| 1 | left_arm | 8 |
| 2 | right_arm | 9 |
| 3 | left_leg_upper | 7 |
| 4 | right_leg_upper | 14 |
| 5 | left_leg_lower | 10 |
| 6 | right_leg_lower | 15 |

### 7.2 默认音频映射

扬声器：

- BCLK：GPIO 2
- LRCLK：GPIO 4
- DIN：GPIO 6
- GAIN：GPIO 16
- SD：GPIO 17

麦克风：

- SCK：GPIO 12
- WS：GPIO 11
- SD：GPIO 13

### 7.3 配置字段

每路舵机至少保存：

- servo_id
- joint
- pin
- frequency_hz
- min_us
- center_us
- max_us
- inverted
- safe_angle
- max_speed_deg_s

音频至少保存麦克风和扬声器引脚、采样率、位深、声道数、功放使能极性和 I2S 缓冲大小。

### 7.4 持久化和回滚

使用 App 自己的 SharedPreferences 保存：

- 内置默认配置
- 当前用户配置
- last_known_good
- Profile Schema 版本
- 配置 Revision 和 SHA-256

未通过验证时不得初始化 PWM。应用新配置失败时自动恢复 last_known_good。

### 7.5 GPIO 校验

- GPIO 47/48 永久保留给触摸和 IMU。
- 仅在 no_camera Profile 下允许回收摄像头 GPIO。
- 禁止舵机、音频、显示、触摸、电池采样之间重复占用 GPIO。
- 首次启动使用中位姿势和保守脉宽。
- 校准界面一次只允许测试一路舵机。
- 配置保存与配置激活必须分成两个步骤。

## 8. 机器人对话运行时

### 8.1 状态机

    IDLE
      → LISTENING
      → ASR
      → THINKING
      → SPEAKING_AND_ACTING
      → COOLDOWN
      → IDLE

异常进入 ERROR，取消进入安全清理流程。

### 8.2 半双工音频

- TTS 播放期间关闭麦克风，避免机器人识别自己的声音。
- 从录音切换到播放时释放 I2S RX，再初始化 I2S TX。
- 从播放切换到录音时关闭功放、释放 I2S TX、清空麦克风积压数据，再初始化 I2S RX。
- 第一版使用触摸或按钮打断，不实现语音打断和 AEC。
- 舵机硬件 PWM 可在 TTS 播放期间继续运行。

### 8.3 ASR

优先使用新版 xfyun_asr.recognize_mic(codec)，边录边上传，并使用驱动提供的 VAD、底噪估算、前置缓冲和静音收尾。

固定 I2SMicCodecAdapter 应向 ASR 驱动提供 start、any、read、clear 和 stop。

### 8.4 LLM

机器人通过 Wi-Fi 直接访问 OpenAI 兼容 LLM API。LLM 上下文只包含人物设定、最近若干轮对话、逻辑动作目录、当前逻辑关节状态、上一轮动作执行结果和必要设备状态。

上下文不得包含 GPIO、PWM、Wi-Fi 密码和云服务密钥。

### 8.5 结构化响应

LLM 返回 reply_text、emotion、actions、requires_confirmation 和 operation_id。不得执行尚未完整接收和验证的动作计划。

### 8.6 TTS

使用 xfyun_tts.synthesize_streaming(text, on_chunk)。异步 on_chunk 将有界 PCM 块写入 I2SSpeakerAdapter，并在块之间让出事件循环。

## 9. 驱动依赖

### 9.1 uPyPI 解析接口

Skill 不保存、快照、内置或改写第三方驱动。每个新 Session 在依赖准备阶段实时解析 uPyPI：

1. 调用 `GET https://upypi.net/api/search?q={query}`。
2. 从返回的 `results[].url` 获取精确版本包地址。
3. 请求 `{package_url}/package.json`。
4. 读取 `name`、`version`、`chips`、`fw`、`deps` 和 `urls`。
5. 递归校验 `deps`，但把实际依赖安装交给 MIP。

截至 2026-08-24，搜索接口返回：

- `xfyun_asr` → `https://upypi.net/pkgs/xfyun_asr/1.0.2`
- `xfyun_tts` → `https://upypi.net/pkgs/xfyun_tts/1.2.1`
- `async_websocket_client` → `https://upypi.net/pkgs/async_websocket_client/1.0.2`

这些版本只是当前解析结果，不得硬编码为 Skill 的永久依赖快照。新 Session 重新解析；Resume、Retry 和同一 Idempotency Key 复用该 Session 已保存的精确包 URL。

### 9.2 部署落地

- Skill 和 MPK 不包含第三方驱动源码。
- `dependency_resolution.json` 只记录包名、版本化 URL、声明的依赖关系、解析时间和安装状态，不保存驱动文件内容。
- 获得 `network_read`、`dependency_install` 和 `device_write` 权限后，部署阶段执行 `mpremote mip install --target=<app-lib> <versioned-package-url>`。
- `<app-lib>` 应是 App 私有且已加入 `sys.path` 的目录，避免修改其他 App 的共享依赖；只有用户明确选择共享安装时才使用 `/lib`。
- 设备自行联网安装时使用 `mip.install(<versioned-package-url>, target=<app-lib>)`。
- MIP 根据 `package.json` 的 `urls` 安装文件并递归安装 `deps`。
- 安装后依次执行模块导入探测和实际 API 符号探测。
- 离线、uPyPI 不可达或依赖安装失败时返回可恢复的结构化错误，不得退回内置驱动副本。

### 9.3 fastb64 与目标固件能力

不修改 `micropython-embedded`、`xfyun_asr` 或 `xfyun_tts`。这些驱动已经在实际 MicroPython 目标上验证可用，Skill 以真机结果为准。

MicroPython 官方文档中的 `binascii.a2b_base64` 和 `binascii.b2a_base64` 是标准库能力；这不等于目标固件不能额外提供 `fastb64`。Skill 在部署前探测 `fastb64.b64encode_str` 和 `fastb64.b64decode`：存在则继续，不存在则返回 `RUNTIME_CAPABILITY_MISSING`，不得自动重写驱动或发布所谓修正版。

### 9.4 目标依赖

- 由 uPyPI 当前搜索结果解析的 `xfyun_asr`
- 由 uPyPI 当前搜索结果解析的 `xfyun_tts`
- 上述包通过 `deps` 声明的 `async_websocket_client`
- 经目标 MicroPython 验证的异步 OpenAI 兼容 HTTP/SSE 客户端

## 10. 协议兼容

本 Skill 定义并维护自己的 `mpos-robot-skill/v1` 协议。该协议以本 Skill 的 `references/session-protocol.md` 和 JSON Schema 为唯一权威，不继承 `mpos-ai-app/v1`，也不依赖其他 MPOS Skill 的协议。

外部网站后端可通过 HTTP API 和可恢复事件流调用该协议；本地 Runner 通过命令行或标准输入输出调用同一协议对象。传输方式可以不同，Session 状态机、请求 Envelope、结果、错误、权限和 Artifact Schema 必须相同。

### 10.1 请求 Envelope

每次操作至少包含：

- protocol_version
- session_id
- checkpoint_id
- idempotency_key
- operation
- status
- stage
- capabilities
- input

`input` 直接包含机器人需求、硬件 Profile、功能配置和已授予能力，不使用 AI App Builder 的 `app_profile` 路由。

### 10.2 Canonical Stages

- analyze
- prepare_deps
- generate
- test
- package
- deploy
- publish_check

### 10.3 状态

- created
- running
- blocked
- waiting_preview
- waiting_device
- partial
- completed
- failed
- cancelled
- timeout

## 11. Session 与 Checkpoint

### 11.1 Session 目录

本地模式默认使用 Skill 工作目录内 `tmp/robot-sessions/session_id`。外部网站模式由其后端管理 Session 目录。两者内部结构一致：

    session/
    ├── session_state.json
    ├── activity_log.jsonl
    ├── artifact_manifest.json
    ├── operation_ledger.jsonl
    ├── checkpoints/
    │   └── cp_generate_001.json
    ├── results/
    │   ├── analysis_result.json
    │   ├── dependency_resolution.json
    │   └── generation_result.json
    └── project/

### 11.2 Checkpoint 提交规则

- 每个阶段都必须输出 Result JSON、phase_complete JSON、Checkpoint 和更新后的 Artifact Manifest。
- Result 和 Manifest 必须先完成原子写入并通过 Schema 校验，然后才能提交 Checkpoint。
- Checkpoint 保存协议版本、输入哈希、Skill 版本、项目自有模板哈希、产物哈希、阶段、结果和下一阶段。它不得保存第三方驱动源码快照。
- Checkpoint 只能指向已完整持久化的安全边界。
- Resume 时必须重新校验所有哈希。
- 已完成阶段直接复用；未完成阶段从最近安全边界重做。
- Checkpoint 损坏或版本不兼容时返回结构化错误，不得静默从头执行。

## 12. 恢复、重试、取消和超时

### 12.1 Resume

- 沿用原 session_id。
- 接收最后有效 checkpoint_id。
- 校验协议、输入、Skill、模板和 Artifact 哈希。
- 从下一未完成阶段继续。

### 12.2 Retry

- 保留原错误、日志和尝试次数。
- 只自动重试 retryable=true 的错误。
- 显式重试使用新的 Idempotency Key，并记录 retry_of。
- 已成功的前置阶段不得重复执行。

### 12.3 Cancellation

- 持久化 cancel_requested。
- 网络等待、测试循环和脚本执行必须周期检查取消状态。
- 清理进程、串口、设备会话和临时资源。
- 返回 cancelled，保留最后有效 Checkpoint。
- 不在固件写入等不可安全中断的临界区强制终止。

### 12.4 Timeout

分别设置阶段、网络调用、设备等待、脚本执行和整体 Session 超时。

超时必须返回 timeout，同时保存 Checkpoint、日志和结构化错误，不能笼统返回 failed。

## 13. 幂等性

幂等作用域：

    session_id + operation + idempotency_key

规则：

- 相同 Key 且输入哈希一致时返回已保存结果。
- 相同 Key 但输入哈希不一致时返回 IDEMPOTENCY_CONFLICT。
- 文件写入、依赖安装、打包、串口连接和设备写入必须记录 Operation Receipt。
- 浏览器刷新、网络重发或本地命令重跑不得造成重复安装、重复刷写或重复发布。

## 14. Capability Negotiation

建议能力：

- desktop_preview
- web_preview
- physical_device
- mpremote
- network_read
- file_write
- script_run
- device_serial
- final_artifacts_only
- batch_mode
- robot_direct_pwm
- robot_i2s_audio
- robot_wifi_conversation

规则：

- 能力必须来自实际探测或调用方声明，不得伪造。
- 无真机时不得声称硬件测试成功。
- 无串口时 Deploy 返回 waiting_device 或 blocked。
- 无网络权限时 Prepare Dependencies 返回 Permission Request。
- 桌面和浏览器预览只验证模拟 HAL，不替代 PWM/I2S 真机测试。
- 未识别的布尔能力应按协议规则向前兼容。

## 15. 结构化错误

错误至少包含：

- code
- message
- stage
- phase
- retryable
- owner
- details
- logs
- artifact_ids
- permission_id（适用时）

建议错误码：

- ROBOT_PROFILE_INVALID
- ROBOT_PIN_CONFLICT
- ROBOT_TEMPLATE_MODIFIED
- DEPENDENCY_UNAVAILABLE
- AUDIO_ADAPTER_UNSUPPORTED
- CHECKPOINT_INCOMPATIBLE
- CHECKPOINT_CORRUPTED
- IDEMPOTENCY_CONFLICT
- DEVICE_NOT_FOUND
- PERMISSION_DENIED
- OPERATION_CANCELLED
- STAGE_TIMEOUT
- EXTERNAL_ASR_ERROR
- EXTERNAL_LLM_ERROR
- EXTERNAL_TTS_ERROR

错误必须标明责任方：app、skill、backend、frontend、toolchain、micropythonos、device、external 或 user。

## 16. Artifact Manifest

每个 Artifact 记录：

- Artifact ID
- Kind
- Role
- 相对路径
- MIME
- SHA-256
- 文件大小
- 所属 Stage
- Revision
- 创建时间

至少登记 Analysis Result、Dependency Resolution、Generation Result、App Source、默认硬件 Profile、App Test Result、Package Result、MPK、Deploy Result、Publish Result、Activity Log 和 Session State。Dependency Resolution 是解析和安装回执，不是驱动源码 Artifact。

所有路径必须为 Session 内相对路径，禁止绝对路径和父目录跳转。Artifact Manifest 不得包含任何密钥值。

## 17. 权限请求

以下操作必须请求权限：

- file_create
- file_write
- file_overwrite
- script_run
- dependency_install
- package_build
- serial_scan
- device_connect
- device_write
- device_command
- firmware_flash
- publish_prepare
- remote_upload
- open_external_url

外部网站调用时，Skill 返回标准 Permission Request 并进入 blocked；网站如何展示和收集决策不属于本 Skill。直接本地调用时通过调用环境向用户请求授权。

Permission Request 和 Decision 必须持久化并绑定 permission_id、session_id、Stage、Resource、Risk、Idempotency Key 和有效期。

Resume 后不得对已经批准且输入未变化的同一操作重复询问。权限过期、资源变化或输入哈希变化时必须重新请求。

## 18. 凭据处理

- Wi-Fi 使用 MicroPythonOS 现有网络设置，不写入 App 模板。
- ASR、TTS、LLM 凭据与硬件 Profile 分开保存。
- 外部网站若参与凭据配置，应通过其设备桥直接写入设备；具体网站和设备桥不属于本 Skill。
- 本地模式通过设备设置或受控部署输入凭据。
- 凭据不得进入 Prompt、Result、Checkpoint、Artifact、日志、截图和测试 Fixture。
- 日志只记录 Provider 名称、状态码、耗时和脱敏错误。
- 物理访问设备仍可能读取普通文件系统；硬件安全存储不属于第一版范围。

## 19. 测试要求

### 19.1 共用核心测试

- 默认 Profile Schema。
- GPIO 重复、保留和冲突检测。
- 舵机角度、速度、持续时间限制。
- 非法 LLM Action Plan。
- 半双工音频状态切换。
- ASR、LLM、TTS 超时和取消。
- 网络断开与重连。
- 配置损坏和 last_known_good 回滚。
- 受保护模板哈希。
- 凭据泄漏扫描。

### 19.2 本地模式测试

- 创建新 Session。
- 从 Checkpoint Resume。
- 本地进程退出后 Resume。
- 权限允许、拒绝和过期。
- 脚本取消和超时。
- 模拟 HAL 桌面测试。

### 19.3 外部调用兼容性测试

- 使用协议 Envelope 创建 Session。
- Resume、Retry 和 Cancel。
- 重复 Idempotency Key。
- Permission Decision。
- waiting_device 恢复。
- 调用方断线后通过原 Session ID 恢复。

不测试或实现网站 API、SSE、WebSocket、页面刷新、前端状态管理或后端存储。

### 19.4 跨模式一致性

相同标准化输入、Skill 版本和模板版本，在排除 Session ID、时间戳等动态字段后，应产生相同核心 Artifact 哈希。

必须测试 Checkpoint 损坏、Artifact 被篡改、协议版本不兼容、能力不足、相同 Key 不同输入、阶段中途崩溃和 Device Write 前后重试。

## 20. 完成标准

只有同时满足以下条件，机器人 Skill 才视为完成：

1. 本地调用和外部网站转发调用共享模板、协议与校验器。
2. 所有阶段输出通过 mpos-robot-skill/v1 Schema 校验。
3. Resume、Retry、Cancel、Timeout 和 Idempotency 均有自动化测试。
4. 文件、脚本、依赖和设备副作用均经过权限流程。
5. Artifact Manifest 可验证所有输出文件。
6. 凭据未进入任何构建或会话 Artifact。
7. 桌面模拟测试通过。
8. 六路 PWM、I2S 麦克风、I2S 扬声器和设备直连云服务完成真机验证。
9. 断网、服务超时、配置损坏和流程中断后能安全恢复。
10. LLM 无法绕过 Action Schema 和 Safety Guard 直接控制 GPIO/PWM。
