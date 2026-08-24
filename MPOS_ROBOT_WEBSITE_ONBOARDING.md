# MPOS 六舵机语音机器人网站前后端交接说明

## 1. 文档目的

本文供后续网站前端、后端和设备接入工程师使用，说明 MPOS 六舵机语音机器人网站应包含的产品模块、技术边界、接口、数据、安全要求和第一版验收标准。

机器人 Skill 已独立实现：

```text
/home/leeqingshui/MicroPython_Skills/mpos-robot-app
```

网站由另一个项目和团队独立实现。网站只调用该 Skill，不修改 Skill，不依赖其他 MPOS Skill，也不依赖 `micropythonos-ai-app-builder` 的运行环境或 `mpos-ai-app/v1` 协议。

现有 Blockless-Make-APP 可作为产品和工程参考：

```text
/home/leeqingshui/micropythonos-ai-app-builder
```

可以参考其中的 Session、SSE、Permission、Artifact、WebSerial、WASM 和错误恢复设计，但不要直接复制其通用 App Builder 产品范围。

## 2. 产品定位

建议定位：

> 面向 Waveshare ESP32-S3-Touch-LCD-2 六舵机语音机器人的配置、生成、安装和调试工作台。

用户不需要理解 MicroPython、GPIO、PWM、I2S 或包管理。网站应带用户完成：

```text
准备设备
  -> 安装/检测 MicroPythonOS
  -> 检查接线
  -> 校准六路舵机
  -> 配置麦克风和扬声器
  -> 配置 Wi-Fi / ASR / LLM / TTS
  -> 设计人物和动作
  -> 生成机器人 App
  -> 安装依赖与 MPK
  -> 真机对话和动作测试
```

网站不是：

- 通用 MicroPythonOS App Builder。
- 多板卡选择和适配平台。
- ASR、LLM、TTS 的运行时代理。
- 任意 Python、Shell 或串口命令执行器。
- `micropythonos-ai-app-builder` 的页面换皮。

## 3. 固定硬件目标

唯一默认目标：

| 字段 | 值 |
| --- | --- |
| 厂商 | Waveshare / 微雪电子 |
| 型号 | ESP32-S3-Touch-LCD-2 |
| MicroPythonOS board ID | `waveshare_esp32_s3_touch_lcd_2` |
| MCU | ESP32-S3 |
| 显示 | ST7789，240×320，MPOS 默认横屏使用 |
| 触摸 | CST816S |
| IMU | QMI8658 |
| 摄像头 | 不使用，必须物理断开 |

不得与 Waveshare 2.1、2.8、2.8B 或 2.8C 混用。

官方资料：

- 支持板卡：https://docs.micropythonos.com/getting-started/supported-hardware/
- Waveshare 产品：https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-2
- MicroPythonOS 安装器：https://install.micropythonos.com/

## 4. 总体架构

```text
┌─────────────────────── Browser Frontend ───────────────────────┐
│ 品牌/教程 │ Robot Studio │ Session 工作台 │ Artifact │ 设备控制 │
└───────────────┬───────────────────────────────┬────────────────┘
                │ HTTPS + JSON + SSE            │ WebSerial
                ▼                               ▼
┌──────────────── Website Backend ─────────┐   Waveshare Robot
│ Session / Permission / Artifact / Runner │         │
│ mpos-robot-skill/v1 adapter              │         ├─ Wi-Fi -> ASR
│ uPyPI metadata resolver                  │         ├─ Wi-Fi -> LLM
└──────────────────┬───────────────────────┘         └─ Wi-Fi -> TTS
                   │
                   ▼
             mpos-robot-app Skill
```

三条链路必须分开：

1. 浏览器和后端：管理 Session、生成、日志、权限和 Artifact。
2. 浏览器和设备：通过 WebSerial 完成探测、配置、安装和诊断。
3. 机器人和云服务：机器人运行时直接通过 Wi-Fi 访问 ASR、LLM、TTS。

后端不能把自己变成机器人运行时的语音或 LLM 代理。

## 5. 前端信息架构

第一版可以做成一个主工作台加多个步骤页，也可以使用路由拆页。无论视觉结构如何，必须覆盖以下区域。

### 5.1 页头、品牌和赞助商

页头建议包含：

- 网站产品 Logo 和名称。
- MicroPythonOS Logo。
- 当前固定硬件标识：`Waveshare ESP32-S3-Touch-LCD-2`。
- 中英文切换。
- 当前 Session 状态。
- 登录用户和历史入口（如果网站支持多用户）。

硬件生态区域建议包含：

- Waveshare Logo 和板卡产品图。
- 硬件赞助商 Logo 条。
- 机器人外接麦克风、功放、舵机等套件图。
- “已验证硬件”“硬件赞助商”“兼容配件”“技术支持”使用不同标签。

商标和 Logo 规则：

- 只有真实赞助关系才能标为“硬件赞助商”。
- 兼容某产品不等于获得厂商赞助。
- 第三方 Logo、产品图和品牌名称上线前确认授权或品牌使用规则。
- 所有 Logo 提供 `alt`、`title`、官网链接和清晰背景版本。
- 不用一个静态图片拼接所有 Logo；使用结构化配置，便于上下线和调整顺序。

建议配置结构：

```json
{
  "id": "waveshare",
  "name": "Waveshare",
  "logo_url": "/sponsors/waveshare.png",
  "website_url": "https://www.waveshare.com/",
  "relationship": "target_hardware",
  "approved": true
}
```

### 5.2 首页和快速开始

首页首屏应直接回答：

- 这是什么机器人。
- 支持哪一块板卡。
- 用户最终能得到什么。
- 第一步应该做什么。

推荐主行动按钮：

- `连接我的机器人`
- `还没有安装 MicroPythonOS`
- `先查看接线和硬件清单`
- `恢复上次 Session`

不要让“输入 Prompt”成为唯一入口。对于第一次使用机器人套件的用户，设备和安全准备优先于代码生成。

### 5.3 设备准备与系统安装

设备准备区必须显示：

- 当前浏览器是否支持 WebSerial。
- 页面是否运行在安全上下文（HTTPS 或 localhost）。
- USB 是否连接。
- 检测到的 VID/PID。
- ESP32-S3 是否可响应。
- 是否可以 `import mpos`。
- MicroPythonOS 版本。
- 板级 ID 是否等于 `waveshare_esp32_s3_touch_lcd_2`。

第一版系统安装流程：

1. 展示“打开官方 MicroPythonOS 安装器”按钮。
2. 新标签页打开 `https://install.micropythonos.com/`。
3. 明确提示选择 ESP32-S3 固件。
4. 明确警告全新安装或擦除设备可能删除 App、Wi-Fi 和用户数据。
5. 用户安装完成并返回本网站后，重新请求连接并探测系统。

官方安装器只负责安装 MicroPythonOS，不会安装机器人 App、uPyPI 驱动、硬件 Profile 或云服务凭据。用户返回网站后仍需继续完成机器人安装流程。

第一版不要：

- 复制或镜像官方固件到网站后端。
- 在代码里硬编码当前最新固件版本。
- 在 iframe 中嵌入跨域安装器并假设 WebSerial 权限可复用。
- 未经确认自动擦除或烧录设备。

以后如果需要站内安装，可使用受控的 WebSerial/ESP Web Tools 流程，但必须读取官方 manifest、显示固件版本和校验信息，并为擦除操作增加单独的高风险权限确认。

### 5.4 硬件清单和接线

页面需要提供：

- Waveshare 板卡正反面图。
- 六路舵机编号、左右位置和关节名称。
- I2S 麦克风接线。
- I2S 功放和扬声器接线。
- 舵机独立供电和共地说明。
- 摄像头必须物理断开的醒目提示。
- 上电前检查清单。

安全要求：

- 不建议从板卡 3.3V 引脚直接给六个舵机供电。
- 外部舵机电源和 ESP32 必须共地。
- 校准前机械结构应留有活动空间。
- 首次测试一次只启用一路舵机。
- 页面常驻“紧急停止/回安全姿势”入口。

网站无法可靠地仅靠软件判断摄像头排线是否仍然连接。激活默认机器人 Profile 前，必须让用户完成接线确认并勾选“摄像头模块已经物理断开”；真机探测只能作为辅助证据，不能替代人工确认。

### 5.5 硬件 Profile 编辑器

默认配置来自：

```text
mpos-robot-app/assets/default_hardware_profile.json
```

必须展示并允许用户修改：

- `servo_id`
- 逻辑关节名称
- GPIO
- PWM 频率
- 最小/中位/最大脉宽
- 最小/最大/安全角度
- 反向设置
- 最大速度
- 麦克风和扬声器 GPIO
- I2S 采样率、位深、声道和缓冲区

保存流程必须分开：

```text
编辑 -> 保存候选配置 -> 校验 -> 用户确认 -> 激活 -> 真机探测 -> 设为 last-known-good
```

保存候选配置不能立即初始化 PWM 或 I2S。激活失败时必须恢复上一份 last-known-good。

前端应即时显示：

- GPIO 重复。
- 使用显示、触摸、IMU、电池、USB、Flash/PSRAM、Boot 或 UART 保留引脚。
- 摄像头仍连接。
- 脉宽、角度或速度范围不合法。
- 配置与默认配置的差异。

### 5.6 舵机校准和动作工作室

校准页：

- 一次选择一个舵机。
- 当前关节、GPIO、角度、脉宽和方向。
- 中位、最小、最大、安全角度按钮。
- 小步进 `-1°/+1°` 和较大步进。
- “保存候选校准值”和“激活”分开。
- 激活倒计时和紧急停止。

动作工作室：

- 六个逻辑关节滑块。
- 当前真实状态和目标状态。
- 姿势命名和保存。
- 姿势预览。
- 动作序列、持续时间和最大速度。
- 常用姿势：安全、站立、问候等。
- 删除、复制、导入和导出姿势。

页面只提交逻辑关节、角度和动作 Schema，不向 LLM 或后端暴露原始 PWM 占空比控制接口。

### 5.7 对话与人物配置

建议字段：

- 机器人名称。
- 人物设定和说话风格。
- 默认语言。
- 对话历史轮数。
- ASR Provider 和非秘密参数。
- LLM Endpoint、Model 和非秘密参数。
- TTS Provider、音色、语速、音量和音高。
- 允许使用的逻辑动作目录。
- 每轮最大动作数和超时。

凭据包括：

- Wi-Fi 密码。
- ASR APP ID、API Key、API Secret。
- LLM API Key。
- TTS 凭据。

凭据必须通过浏览器到设备的受控 WebSerial 通道写入设备。后端不接收、不记录、不回显凭据明文。

测试按钮：

- 测试麦克风采集。
- 测试 ASR。
- 测试 LLM。
- 测试扬声器和 TTS。
- 测试一个安全动作。
- 测试完整“录音 -> ASR -> LLM -> 动作 + TTS”流程。

每项测试独立显示状态、耗时、错误码和可重试入口。

### 5.8 Skill Session 工作台

网站调用 `mpos-robot-skill/v1`，其权威说明位于：

```text
mpos-robot-app/references/protocol.md
```

工作台至少包含：

- 用户需求和 AI 阶段摘要。
- 阶段时间线。
- 权限请求。
- 当前 Checkpoint。
- Resume、Retry、Cancel。
- 独立的 Timeout 状态。
- Warning、Blocked、Failed、Cancelled 分开展示。
- 用户日志和工程日志两个视图。
- Artifact 清单和下载。
- 同一 Session 的 Revision 历史。

建议阶段：

```text
analyze
prepare_deps
generate
test
package
deploy
publish_check（可选）
```

机器人网站可以把用户可见名称改成：

```text
理解需求
检查硬件与依赖
生成机器人 App
运行安全测试
打包
安装到机器人
交付检查
```

前端不能解析 AI 的自然语言最终回答来判断状态，必须使用结构化 Result、Checkpoint、Event 和 Error。

### 5.9 设备安装和诊断

设备安装顺序：

1. 探测设备和 MicroPythonOS。
2. 验证板级 ID。
3. 验证存储空间和运行内存。
4. 确认设备 Wi-Fi 已配置并可访问 uPyPI；凭据仍只写入设备。
5. 获取当前 Session 的 uPyPI 安装计划。
6. 请求 `dependency_install` 和 `device_write` 权限。
7. 通过设备端 MIP 安装版本化 uPyPI URL。
8. 探测 `fastb64`、`async_websocketclient`、`xfyun_asr`、`xfyun_tts`。
9. 安装机器人 MPK。
10. 启动 App。
11. 回写结构化 Device Result。

设备诊断应包含：

- WebSerial 连接和自动重连。
- PING 和内存探测。
- 文件系统剩余空间。
- MicroPythonOS 和板卡信息。
- 依赖导入和符号探测。
- 单路 PWM 测试。
- I2S RX/TX 测试。
- Wi-Fi、DNS、TLS 和云服务测试。
- 脱敏串口日志。

默认不提供任意 REPL 命令输入框。确实需要时放入明确标记的专家模式，并再次请求高风险权限。

### 5.10 Artifact 和历史

Artifact 页面至少显示：

- 文件角色和所属阶段。
- Session 相对路径。
- MIME。
- 大小。
- SHA-256。
- Revision。
- 下载按钮。

建议交付物：

- 需求分析结果。
- 依赖解析记录。
- 默认和用户硬件 Profile。
- App 源码。
- MPK。
- 测试结果。
- 设备部署结果。
- 脱敏日志。
- Session 导出包。

不要把 uPyPI 驱动源码或设备凭据放入 Skill Artifact。

## 6. 后端模块

### 6.1 SessionService

职责：

- 创建和读取 Session。
- 保存 Revision。
- 保存 Session 状态。
- 保存 Checkpoint 历史。
- 恢复中断流程。
- 防止同一 Session 同时运行两个主任务。

### 6.2 RobotSkillAdapter

职责：

- 只调用 `mpos-robot-app`。
- 构造和验证 `mpos-robot-skill/v1` Envelope。
- 将 Skill 输出转换成前端 Event。
- 不调用其他 MPOS Skill。
- 不复用 `micropythonos-ai-app-builder` 的内部协议。

### 6.3 RunnerController

职责：

- 启动阶段任务。
- 管理 retry、cancel 和 timeout。
- 定期检查取消请求。
- 保存失败现场。
- 维护 Idempotency Key。
- 阻止重复安装、重复写设备和重复打包。

### 6.4 EventService

建议第一版使用 SSE：

- 每条事件包含 `seq`、`ts`、`session_id`、`stage`、`status`。
- 支持 `Last-Event-ID` 或 `after` 游标。
- 前端断线重连后补发缺失事件。
- Event 先持久化，再向前端发送。

### 6.5 PermissionService

至少支持：

- `file_create`
- `file_overwrite`
- `script_run`
- `network_read`
- `dependency_install`
- `package_build`
- `serial_scan`
- `device_connect`
- `device_command`
- `device_write`
- `firmware_flash`
- `remote_upload`

每次权限请求绑定：

- `permission_id`
- `session_id`
- Stage
- Resource
- Risk
- Input Hash
- Idempotency Key
- Expiry

### 6.6 ArtifactService

职责：

- 生成 Artifact Manifest。
- 计算 Hash 和大小。
- 只接受 Session 相对路径。
- 用 Artifact ID 下载。
- 防止绝对路径、`..` 和跨 Session 读取。
- 过滤密钥和敏感日志。

### 6.7 DependencyService

职责：

- 调用 `https://upypi.net/api/search?q={package}`。
- 请求搜索结果的版本化 `package.json`。
- 解析 `deps` 和 `urls` 元数据。
- 输出版本化安装计划。
- 记录解析和安装回执。

禁止：

- 把驱动源码保存进 Skill。
- 建立驱动源码快照。
- 修改或修补 `micropython-embedded`。
- 离线时退回后端内置驱动。

### 6.8 DeviceResultService

浏览器拥有 WebSerial 连接，后端不能直接使用浏览器串口。

后端负责：

- 下发受控设备操作计划。
- 记录操作 ID 和预期 Marker。
- 接收浏览器回传的阶段结果。
- 校验 Session、Operation、Idempotency Key 和结果结构。
- 更新 Deploy Result、Checkpoint 和 Artifact。

后端不能相信前端一句 `success=true`。结果应包含操作类型、Marker、设备信息、时间、耗时、脱敏日志摘要和验证项。

### 6.9 SecretPolicy

后端必须阻止以下内容进入数据库、Session、Prompt、日志和 Artifact：

- Wi-Fi 密码。
- ASR/TTS/LLM API Key 和 Secret。
- 完整 Authorization Header。
- 设备普通文件系统中的凭据文件。

日志只保留 Provider、状态码、耗时、错误类型和脱敏消息。

## 7. 建议 API

以下只是网站传输层建议；权威业务状态仍由 `mpos-robot-skill/v1` 定义。

```text
GET  /api/capabilities

POST /api/sessions
GET  /api/sessions
GET  /api/sessions/{session_id}
GET  /api/sessions/{session_id}/events

POST /api/sessions/{session_id}/actions/run
POST /api/sessions/{session_id}/actions/analyze
POST /api/sessions/{session_id}/actions/prepare-deps
POST /api/sessions/{session_id}/actions/generate
POST /api/sessions/{session_id}/actions/test
POST /api/sessions/{session_id}/actions/package
POST /api/sessions/{session_id}/actions/deploy

POST /api/sessions/{session_id}/resume
POST /api/sessions/{session_id}/retry
POST /api/sessions/{session_id}/cancel

POST /api/sessions/{session_id}/hardware/validate
POST /api/sessions/{session_id}/dependencies/resolve
POST /api/sessions/{session_id}/device-results

GET  /api/sessions/{session_id}/artifacts
GET  /api/artifacts/{artifact_id}
GET  /api/sessions/{session_id}/export

POST /api/permissions/{permission_id}/decision
```

所有产生副作用的 POST 请求必须携带 Idempotency Key。

## 8. 建议数据结构

### 8.1 Session

```json
{
  "protocol_version": "mpos-robot-skill/v1",
  "session_id": "session_xxx",
  "revision_id": "r1",
  "checkpoint_id": "cp_generate_0003",
  "stage": "generate",
  "status": "running",
  "cancel_requested": false,
  "capabilities": {},
  "warnings": [],
  "last_error": null
}
```

### 8.2 Device Result

```json
{
  "operation_id": "device_install_001",
  "idempotency_key": "install-session-r1",
  "device": {
    "platform": "esp32",
    "board_id": "waveshare_esp32_s3_touch_lcd_2",
    "mpos_available": true,
    "mpos_version": "detected-at-runtime"
  },
  "checks": [
    {"name": "fastb64.b64encode_str", "status": "passed"},
    {"name": "xfyun_asr import", "status": "passed"}
  ],
  "status": "completed",
  "duration_ms": 12000,
  "log_excerpt": "redacted"
}
```

### 8.3 Structured Error

```json
{
  "code": "ROBOT_PIN_CONFLICT",
  "message": "GPIO 8 is assigned twice",
  "stage": "generate",
  "retryable": false,
  "owner": "skill",
  "details": {},
  "artifact_ids": [],
  "permission_id": null
}
```

## 9. 安全与权限

### 9.1 浏览器

- 使用 HTTPS。
- WebSerial 必须由用户点击触发。
- 不在 LocalStorage 保存凭据。
- 页面刷新后恢复 Session，但不自动重连未授权设备。
- 防止重复点击产生重复部署。
- 串口日志默认脱敏。

### 9.2 后端

- 每个 Session 隔离工作目录。
- 对所有 Session、Artifact 和 Permission 做用户所有权检查。
- 文件操作限制在 Session 工作区。
- Script 和 Device 操作使用白名单。
- 禁止把模型输出直接当 Shell、Python 或设备命令执行。
- API 限流、请求大小限制和超时。
- Artifact 下载防路径穿越。

### 9.3 设备

- 烧录、擦除和固件安装单独确认。
- 舵机校准一次只允许一路。
- 页面失联或操作超时后进入安全姿势。
- 取消操作时关闭功放、停止 I2S、停止运动插值。
- 不允许 LLM 直接控制 GPIO 或 PWM。

## 10. 不应照搬 Blockless-Make-APP 的部分

- 通用 App 类型和分类。
- 通用包名、Publisher、Version 表单作为首页核心。
- 15 款板卡展示和板卡能力选择器。
- 通用公开 App 库。
- 订阅、点数和人工充值。
- 默认 uPyStore 发布流程。
- 任意串口 REPL 命令框。
- 把 WASM 预览说成 PWM、I2S 或真机验证。
- `mpos-ai-app/v1`。
- `mpos-*-web` 多 Skill 流水线。

可复用的设计思想：

- 登录和用户隔离。
- Session、Revision 和恢复。
- SSE 事件流。
- Permission Host。
- Artifact Browser。
- WebSerial 自动重连、PING、内存检查和 MPK 安装。
- 结构化错误和从 Checkpoint Retry。
- 中英文 UI。

## 11. 分阶段实现

### 11.1 P0：第一版必须完成

- 产品首页、品牌和真实赞助商/硬件标识。
- 固定 Waveshare 板卡说明。
- 官方 MicroPythonOS 安装器入口。
- WebSerial 连接、重连和系统探测。
- 接线、安全说明和默认硬件 Profile。
- Profile 编辑、校验、保存、激活和回滚。
- 单路舵机校准和紧急停止。
- 人物、ASR、LLM、TTS 基础配置。
- `mpos-robot-skill/v1` Session 工作台。
- SSE、Checkpoint、Resume、Retry、Cancel、Timeout。
- Permission Prompt。
- uPyPI 依赖解析和设备端安装。
- MPK 安装、启动和基础真机诊断。
- Artifact、错误和历史 Session。
- 凭据不经过后端。

### 11.2 P1：尽快增加

- 可视化姿势和动作序列编辑器。
- ASR/LLM/TTS 分项诊断图表。
- Session 和设备诊断导出包。
- 配置导入、导出和共享。
- 机器人模板和人物模板。
- 可选 WASM UI 预览，并明确其硬件限制。
- 设备截图和运行日志增强。

### 11.3 P2：后续考虑

- 社区人物、姿势和动作库。
- uPyStore 发布准备。
- 多机器人设备管理。
- 团队协作、评论和课堂模式。
- OTA App 更新。
- 合规支付和订阅。

## 12. P0 验收标准

### 12.1 前端

- Chrome/Edge/Brave 可以连接目标设备。
- 不支持 WebSerial 时给出明确提示。
- 用户可从官网安装器返回并重新探测设备。
- 错误、等待授权、等待设备、取消和超时状态不会混为“失败”。
- 页面刷新后可恢复 Session 和事件游标。
- 相同 Permission ID 只能处理一次。
- GPIO 冲突在写设备前被阻止。
- 摄像头仍连接或启用时阻止默认机器人 Profile 激活。
- 凭据不会出现在浏览器日志、LocalStorage 或 API 请求中。

### 12.2 后端

- 通过 `mpos-robot-skill/v1` Schema 校验。
- 同一 Session 只运行一个主流程。
- Retry 不覆盖失败现场。
- Cancel 可以停止子进程并释放资源。
- Checkpoint 损坏返回结构化错误。
- 相同 Idempotency Key 和相同输入返回原结果。
- 相同 Idempotency Key 和不同输入返回冲突。
- uPyPI 不可用时不回退到驱动快照。
- Artifact 不暴露绝对路径或跨 Session 文件。
- 后端数据库、日志和对象存储不含设备凭据。

### 12.3 真机

- 正确识别 `waveshare_esp32_s3_touch_lcd_2`。
- 六路 PWM 分别可测试且无 GPIO 冲突。
- 麦克风采集和扬声器播放可分别测试。
- RX/TX 切换符合半双工要求。
- `fastb64`、ASR、TTS 和 WebSocket 依赖探测通过。
- 机器人可以直接连接 Wi-Fi 访问 ASR、LLM、TTS。
- LLM 非法动作不会进入舵机控制层。
- 断网、服务超时、页面刷新或流程中断后可以安全恢复。
- 紧急停止可以停止运动并进入安全状态。

## 13. 参考文件

机器人 Skill：

```text
/home/leeqingshui/MicroPython_Skills/mpos-robot-app/SKILL.md
/home/leeqingshui/MicroPython_Skills/mpos-robot-app/references/hardware.md
/home/leeqingshui/MicroPython_Skills/mpos-robot-app/references/protocol.md
/home/leeqingshui/MicroPython_Skills/mpos-robot-app/references/dependencies.md
/home/leeqingshui/MicroPython_Skills/mpos-robot-app/references/runtime-contract.md
```

现有网站参考：

```text
/home/leeqingshui/micropythonos-ai-app-builder/frontend/src/App.tsx
/home/leeqingshui/micropythonos-ai-app-builder/frontend/src/deviceSerial.ts
/home/leeqingshui/micropythonos-ai-app-builder/backend/app/main.py
/home/leeqingshui/micropythonos-ai-app-builder/backend/app/session_service.py
/home/leeqingshui/micropythonos-ai-app-builder/docs/architecture.md
```

已有分析：

```text
/home/leeqingshui/MicroPython_Skills/FRONTEND_BACKEND_ONBOARDING.md
/home/leeqingshui/MicroPython_Skills/mpos-conversational-skills-analysis.md
/home/leeqingshui/MicroPython_Skills/ROBOT_SKILL_SPEC.md
```
