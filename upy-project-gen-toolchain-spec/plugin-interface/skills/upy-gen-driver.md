# upy-gen-driver 接口定义

> 状态：✅ 已定稿
>
> 异常路径 — 冷门硬件驱动生成。当 upypi 和 GitHub 均无驱动时触发。从 PDF 数据手册/Arduino 代码/芯片照片/GitHub URL/芯片型号生成规范化 MicroPython 驱动。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | gen-driver |
| 上游 Skill | upy-analyze（搜不到驱动时调用）、upy-autofix（诊断为缺驱动时调用）或用户直接触发 |
| 下游 Skill | upy-generate（使用生成好的驱动继续主流程） |
| 一句话职责 | 输入源材料 → 预处理 → LLM 生成调试版 → 硬件验证循环(≤10轮) → 脱调试 → P0规范化 → 独立验证材料 → 可选上电测试 → 生产版驱动 |

**核心约束：**
- Step 3 硬件验证为硬性约束，禁止在 SELF_TEST_PASS 前进入 Step 4/5
- 无设备时暂停等待用户确认，不得以"当前无设备"为由跳过
- extract_pdf.py / convert_arduino.py 只做提取+映射，理解由 LLM 完成
- Arduino 翻译不能机械逐行，必须理解原逻辑后用 MPY 惯用写法重写
- 依赖注入是硬要求：I2C/SPI/UART 实例必须外部传入
- 禁止无限轮询：所有等待/轮询循环必须带 timeout

---

## 二、插件输入 → Skill（P→S）

```json
{
  "type": "start_phase",
  "phase": "gen-driver",
  "session_id": "uuid-xxx",
  "payload": {
    "manifest": { },
    "source": null
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `manifest` | object? | 否 | 已有 manifest（来自上游 analyze），无则为 null |
| `source` | object? | 否 | 插件端预填的输入材料。null 时触发 approval_request 让用户上传 |

### source 结构（插件端预填时）

```json
{
  "source": {
    "type": "pdf",
    "files": [
      {
        "name": "sht30_datasheet.pdf",
        "mime_type": "application/pdf",
        "size": 245760,
        "local_path": "/tmp/uploads/sht30_datasheet.pdf",
        "content": "(提取的文本内容...)",
        "thumbnail_base64": "data:image/png;base64,iVBOR..."
      },
      {
        "name": "chip_silkscreen.jpg",
        "mime_type": "image/jpeg",
        "size": 98304,
        "content_base64": "/9j/4AAQSkZJRg...",
        "thumbnail_base64": "data:image/jpeg;base64,/9j/4AAQ..."
      }
    ],
    "url": "https://github.com/adafruit/Adafruit_SHT31",
    "chip_model": "SHT30"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 输入类型：`pdf` / `arduino` / `image` / `github_url` / `chip_model` |
| `files` | array? | 视类型 | PDF/Arduino/图片源文件列表。上限 5 个文件，每文件 ≤10MB |
| `files[].name` | string | 是 | 原始文件名 |
| `files[].mime_type` | string | 是 | MIME 类型 |
| `files[].size` | int | 是 | 文件大小（字节） |
| `files[].local_path` | string | 否 | 插件端本地路径（供 script_run 引用） |
| `files[].content` | string? | 否 | PDF/Arduino 类：预处理后的文本内容（插件提前执行 extract_pdf/convert_arduino） |
| `files[].content_base64` | string? | 否 | 图片类：base64 编码的原始图片（服务器 LLM 多模态识别） |
| `files[].thumbnail_base64` | string? | 否 | data URI 缩略图（150×150），插件端生成 |
| `url` | string? | 否 | GitHub 仓库 URL，type=github_url 时必填 |
| `chip_model` | string? | 否 | 仅芯片型号，type=chip_model 时必填 |

**插件端预处理规则：**
- PDF：插件先执行 `extract_pdf.py`，文本填入 `content`。若未预处理（content 为空），服务器发 `script_run`
- Arduino：插件先执行 `convert_arduino.py`，映射结果填入 `content`。若未预处理，服务器发 `script_run`
- 图片：传 `content_base64`，不做预处理，服务器 LLM 多模态识别芯片型号/丝印
- 缩略图：插件端生成 150×150。PDF→第1页渲染，图片→缩放，代码→文件类型图标+文件名

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Step 0: 输入判断 (source=null 或 source.files 为空时)
  → approval_request: gen_driver_input 卡片

Step 1: 预处理 (按 source.type 分支)
  ├─ pdf:
  │   (若 content 已填充 → 跳过脚本，直接 LLM 分析)
  │   (若 content 为空) → script_run(extract_pdf.py --input {local_path} --output docs/driver_extracted.json --json-summary)
  │   → file_operation(read) → docs/driver_extracted.json
  │   → status_update "正在分析数据手册..."
  │   → LLM 生成 understanding.json → file_operation(write) → docs/driver_understanding.json
  │   → status_update "芯片: {chip}, 协议: {I2C/SPI/UART}, 地址: 0xXX, ID寄存器: {有/无}"
  │
  ├─ arduino:
  │   (若 content 已填充 → 跳过脚本)
  │   (若 content 为空) → script_run(convert_arduino.py --input {local_path} --output docs/driver_mapping.json --json-summary)
  │   → file_operation(read) → docs/driver_mapping.json
  │   → LLM 同时读取原始源码 + 映射 JSON → 理解逻辑 → 翻译为 MPY
  │
  ├─ image:
  │   → (content_base64 已在 payload 中) → LLM 多模态识别芯片型号/丝印
  │   → 识别出芯片 → WebSearch datasheet → (找到 PDF URL → approval_request 通知用户下载 → 回到 pdf 路径)
  │   → 无法识别 → approval_request 告知用户，请求补充信息
  │
  ├─ github_url:
  │   → WebFetch 拉取仓库源码
  │   → status_update "正在拉取 GitHub 源码..."
  │   → (拉取成功 → LLM 分析源码结构 → 翻译为 MPY)
  │   → (拉取失败 → approval_request 告知用户，请求手动提供代码)
  │
  └─ chip_model:
      → WebSearch "{chip_model} datasheet PDF"
      → (找到 PDF URL) → approval_request 通知用户下载 PDF → 回到 pdf 路径
      → (找不到) → approval_request 告知用户，请求手动上传

Step 2: 生成调试版驱动
  → status_update "正在生成调试版驱动..."
  → file_operation(write) → firmware/drivers/{chip}_driver/{chip}_debug.py
  → status_update "✓ 调试版驱动已生成 (含 N 项自检)"

Step 3: 硬件验证循环 (≤10 轮)
  → device_command(devs)
  → (无设备) → approval_request: gen_driver_no_device 卡片
     ├─ 重新检测 → 回到 device_command(devs)
     ├─ 跳过 → 进 Step 4（标注 ⚠️ 未经硬件验证）
     └─ 稍后 → phase_complete(result=partial)，可随时继续
  → (有设备) → 进入循环:
     ┌─ script_run(run_on_device.py --com {COM} --file {debug_py} --capture)
     ├─ file_operation(read) → logs/driver_verify_round{N}.log
     ├─ LLM 分析输出
     ├─ status_update 每轮结果 (PASS/FAIL + 错误摘要)
     ├─ SELF_TEST_PASS → 退出循环，进 Step 4
     ├─ 失败 → Edit + file_operation(write) → 下一轮
     └─ 10 轮耗尽 → phase_complete(result=partial, errors)

Step 4: 脱调试 → 生产版驱动
  → (前置条件检查: Step 3 已执行 + SELF_TEST_PASS + debug 版文件存在)
  → (条件不满足 → 回 Step 3)
  → status_update "正在生成生产版驱动..."
  → file_operation(write) → firmware/drivers/{chip}_driver/{chip}.py
  → status_update "✓ 生产版驱动已生成"

Step 5: 规范化
  → file_operation(read) → {chip}.py
  → (LLM 按 upy-norm-driver P0 规则逐条改写)
  → (中间件库跳过 #16/#16a/#16b/#16c/#29/#34-#38)
  → file_operation(write) → {chip}.py (覆盖)
  → status_update "✓ 规范化完成 (N 条 P0 规则已执行)"

Step 6: 生成独立验证材料 (必有，不论 gen-driver 从哪里触发)
  → (LLM 从 understanding.json 提取引脚/总线/地址/电源要求)
  → file_operation(write) → firmware/drivers/{chip}_driver/test_{chip}.py
     (极简脚本: import 驱动 → 初始化 → 读一次数据 → print → deinit，不依赖 manifest/其他模块)
  → file_operation(write) → firmware/drivers/{chip}_driver/wiring_{chip}.md
     (单芯片接线表: 芯片引脚→MCU引脚 + 电源要求 + 上拉/限流提醒)
  → status_update "✓ 独立测试脚本 + 接线参考已生成"

Step 7: 独立上电测试 (approval_request，可选)
  → approval_request: gen_driver_standalone_test 卡片
     (展示接线表 + 电源要求 + 上拉电阻提醒)
     ├─ "已接线，开始测试" → script_run(run_on_device.py --file test_{chip}.py --capture)
     │   → file_operation(read) → logs/driver_standalone_test.log
     │   → PASS → status_update "✓ {chip} 独立测试通过"
     │   → FAIL → status_update "✗ {chip} 独立测试失败" → 回到 Step 3 排查
     └─ "稍后手动测试" → 跳过，文件已生成，随时可测

Step 8: 更新 manifest (条件执行)
  → (仅当 manifest 存在时执行 — gen-driver 从 analyze/autofix 调进来)
  → (独立触发时 skip)
  → file_operation(read) → project-manifest.json
  → (服务端修改 drivers 字段，追加新驱动)
  → file_operation(write) → project-manifest.json

Step 9: 下一步选择 (必有)
  → approval_request: gen_driver_next_step 卡片
     ├─ "规范打包 + 发布到 upypi" → phase_complete(next_phase="publish")
     ├─ "集成到项目继续开发" → phase_complete(next_phase="generate")
     └─ "结束" → phase_complete(next_phase=null)

输出
  → phase_complete(file_list + diagnostics table + next_phase)
```

### approval_request — 文件上传卡片（gen_driver_input）

条件触发：`source` 为 null 或 source.files 为空。

```
┌──────────────────────────────────────────────┐
│  生成驱动 — 提供数据手册或参考代码              │
│                                              │
│  请提供以下任一材料：                          │
│                                              │
│  📄 上传文件 (PDF / .ino / .cpp / 图片)       │
│  ┌──────────────────────────────────────┐    │
│  │  点击或拖拽上传                        │    │
│  │  支持 PDF / .ino / .cpp / .jpg / .png │    │
│  │  最多 5 个文件，每文件 ≤10MB           │    │
│  └──────────────────────────────────────┘    │
│                                              │
│  [已上传文件缩略图列表...]                     │
│                                              │
│  ── 或者 ──                                  │
│  GitHub URL: [https://github.com/...    ]     │
│                                              │
│  ── 或者 ──                                  │
│  芯片型号:   [SHT30                      ]    │
│                                              │
│  [确认，开始生成]                              │
└──────────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "gen_driver_input",
    "header": "生成驱动 — 提供数据手册或参考代码",
    "question": "请上传 PDF 数据手册、Arduino/C++ 参考代码、芯片照片，或输入 GitHub URL / 芯片型号",
    "summary": {},
    "items": [],
    "allow_add": true,
    "allow_remove": true,
    "multi_select": true,
    "file_upload": {
      "enabled": true,
      "accept": [".pdf", ".ino", ".cpp", ".c", ".h", ".jpg", ".jpeg", ".png"],
      "max_files": 5,
      "max_size_mb": 10,
      "generate_thumbnails": true,
      "thumbnail_size": [150, 150],
      "preprocess": {
        ".pdf": "python .upy/scripts/extract_pdf.py --input {path} --output docs/driver_extracted.json --json-summary",
        ".ino": "python .upy/scripts/convert_arduino.py --input {path} --output docs/driver_mapping.json --json-summary",
        ".cpp": "python .upy/scripts/convert_arduino.py --input {path} --output docs/driver_mapping.json --json-summary",
        ".jpg": "none",
        ".jpeg": "none",
        ".png": "none"
      }
    },
    "text_inputs": [
      {
        "id": "github_url",
        "label": "GitHub 仓库 URL",
        "placeholder": "https://github.com/adafruit/...",
        "type": "url"
      },
      {
        "id": "chip_model",
        "label": "芯片型号",
        "placeholder": "例如: SHT30, MPU6050, ADS1115",
        "type": "text"
      }
    ],
    "actions": [
      { "label": "确认，开始生成", "value": "confirm", "primary": true }
    ]
  }
}
```

**`file_upload` 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `enabled` | bool | 是否启用文件上传 |
| `accept` | string[] | 允许的文件扩展名 |
| `max_files` | int | 最大文件数 |
| `max_size_mb` | int | 单文件最大大小 (MB) |
| `generate_thumbnails` | bool | 是否生成缩略图 base64 |
| `thumbnail_size` | [int, int] | 缩略图尺寸 [宽, 高] |
| `preprocess` | object | 按扩展名的预处理脚本。"none" = 不需要预处理。插件端可提前执行并在 content 中填入结果，或让服务器控制 script_run |

### approval_request — 无设备卡片（gen_driver_no_device）

条件触发：Step 3 `device_command(devs)` 返回空设备列表。

```
┌──────────────────────────────────────────────┐
│  未检测到 MicroPython 设备                     │
│                                              │
│  硬件验证需要连接设备。请选择：                  │
│                                              │
│  ○ 我已连接设备，重新检测                       │
│  ○ 跳过硬件验证（生成未经测试的驱动，⚠️ 不推荐）  │
│  ○ 保存进度，稍后继续                          │
│                                              │
│  [确认]                                       │
└──────────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "gen_driver_no_device",
    "header": "未检测到 MicroPython 设备",
    "question": "硬件验证需要连接设备，请选择：",
    "items": [
      {
        "id": "retry",
        "name": "重新检测",
        "subtitle": "我已连接设备",
        "meta": "再次扫描 COM 口",
        "selected": true
      },
      {
        "id": "skip",
        "name": "跳过硬件验证",
        "subtitle": "生成未经测试的驱动",
        "meta": "⚠️ 不推荐，最终输出将标注'未经硬件验证'",
        "selected": false
      },
      {
        "id": "save",
        "name": "稍后继续",
        "subtitle": "保存当前进度",
        "meta": "调试版驱动已生成，可随时继续验证",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "确认", "value": "confirm", "primary": true }
    ]
  }
}
```

### approval_request — 独立测试卡片（gen_driver_standalone_test）

条件触发：Step 6 完成，驱动就绪。不论是独立触发还是从 pipeline 调进来，都弹出此卡片。

```
┌──────────────────────────────────────────────┐
│  驱动已生成 — 是否立即上电独立测试？            │
│                                              │
│  请按以下接线连接芯片（单独测试，不接其他器件）：  │
│                                              │
│  SHT30 接线参考：                              │
│  ┌──────────┬──────────┬────────┐            │
│  │ 芯片引脚  │ MCU 引脚  │ 备注    │            │
│  ├──────────┼──────────┼────────┤            │
│  │ VCC      │ 3.3V     │        │            │
│  │ GND      │ GND      │        │            │
│  │ SDA      │ GPIO21   │ 需上拉  │            │
│  │ SCL      │ GPIO22   │ 需上拉  │            │
│  │ ADDR     │ GND      │ 地址=0x44│           │
│  └──────────┴──────────┴────────┘            │
│  ⚠ 确认 SDA/SCL 已接 4.7kΩ 上拉电阻到 3.3V    │
│  ⚠ I2C 地址 0x44（ADDR 接地）                  │
│                                              │
│  ○ 已接线，开始测试                            │
│  ○ 稍后手动测试                                │
│                                              │
│  [确认]                                       │
└──────────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "gen_driver_standalone_test",
    "header": "驱动已生成 — 是否立即上电独立测试？",
    "question": "请按接线表单独连接芯片（不接其他器件），然后选择：",
    "summary": {
      "chip": "SHT30",
      "protocol": "I2C",
      "address": "0x44",
      "test_script": "firmware/drivers/sht30_driver/test_sht30.py",
      "wiring_ref": "firmware/drivers/sht30_driver/wiring_sht30.md"
    },
    "items": [
      {
        "id": "test_now",
        "name": "已接线，开始测试",
        "subtitle": "仅接这颗芯片，不接其他器件",
        "meta": "推荐 — 确认芯片可独立工作后再集成到项目",
        "selected": true
      },
      {
        "id": "test_later",
        "name": "稍后手动测试",
        "subtitle": "测试脚本 + 接线参考已生成",
        "meta": "随时可运行 test_{chip}.py 进行独立验证",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "确认", "value": "confirm", "primary": true }
    ]
  }
}
```

**接线参考字段（`summary` 中的内容）：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `chip` | string | 芯片型号 |
| `protocol` | string | 通信协议 + 地址/波特率 |
| `address` | string | 总线地址（I2C/SPI CS） |
| `test_script` | string | 独立测试脚本路径 |
| `wiring_ref` | string | 完整接线参考文件路径 (.md) |

**round 2 回到此卡片时：** 如果 Step 7 测试失败 → 回 Step 3 修复 → 再次走到 Step 7，卡片 `header` 追加 "(第 2 次)"。

### script_run — run_on_device.py（Step 7 独立测试）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "standalone_test",
    "interpreter": "python",
    "script": ".upy/scripts/run_on_device.py",
    "args": ["--com", "{COM}", "--file", "firmware/drivers/{chip}_driver/test_{chip}.py", "--capture", "--timeout-ms", "15000"],
    "cwd": "{project_dir}",
    "timeout_ms": 30000
  }
}
```

**与 Step 3 共用 `run_on_device.py`，仅 `--file` 和 `--timeout-ms` 不同。** 独立测试脚本更简单（单次读数据），timeout 只需 15s。

### approval_request — 下一步选择卡片（gen_driver_next_step）

条件触发：Step 7 完成（或用户选择稍后测试），驱动就绪。不论 gen-driver 从哪里触发，都弹出。

```
┌──────────────────────────────────────────────┐
│  驱动已就绪 — 下一步？                         │
│                                              │
│  SHT30 驱动已生成，独立测试通过。                │
│  请选择后续操作：                               │
│                                              │
│  ○ 规范打包 + 发布到 upypi                      │
│    生成 README、package.json、LICENSE，         │
│    组织标准目录结构，发布到 upypi                │
│                                              │
│  ○ 集成到项目继续开发                           │
│    将驱动加入 manifest，继续主流程开发            │
│                                              │
│  ○ 结束                                       │
│    驱动文件已就绪，稍后手动处理                   │
│                                              │
│  [确认]                                       │
└──────────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "gen_driver_next_step",
    "header": "驱动已就绪 — 下一步？",
    "question": "SHT30 驱动已生成，独立测试通过。请选择后续操作：",
    "summary": {
      "chip": "SHT30",
      "driver_path": "firmware/drivers/sht30_driver/sht30.py",
      "test_passed": true,
      "has_manifest": true
    },
    "items": [
      {
        "id": "publish",
        "name": "规范打包 + 发布到 upypi",
        "subtitle": "生成 README、package.json、LICENSE，组织标准目录结构",
        "meta": "推荐 — 方便社区复用和 mip 安装",
        "selected": true
      },
      {
        "id": "integrate",
        "name": "集成到项目继续开发",
        "subtitle": "将驱动加入 manifest，继续主流程",
        "meta": "仅 pipeline 触发时可选",
        "selected": false,
        "disabled": false
      },
      {
        "id": "done",
        "name": "结束",
        "subtitle": "驱动文件已就绪，稍后手动处理",
        "meta": "可随时重新打开项目继续",
        "selected": false
      }
    ],
    "allow_add": false,
    "allow_remove": false,
    "multi_select": false,
    "actions": [
      { "label": "确认", "value": "confirm", "primary": true }
    ]
  }
}
```

| `summary` 字段 | 类型 | 说明 |
|------|------|------|
| `chip` | string | 芯片型号 |
| `driver_path` | string | 生产版驱动路径 |
| `test_passed` | bool | 独立测试是否通过。false 时 "发布"项的 `meta` 追加 "⚠️ 未经硬件验证" |
| `has_manifest` | bool | 是否有 manifest。false（独立触发）时 "集成到项目"项 `disabled: true` |

**用户选 "publish" → phase_complete(next_phase="publish")，插件自动触发 upy-publish skill。**
**用户选 "integrate" → phase_complete(next_phase="generate")，回到主流程。**
**用户选 "done" → phase_complete(next_phase=null)，收工。**

### status_update 列表
|---------|-------|---------|---------|
| extract_pdf | info | 正在提取 PDF 文本... | Step 1A 开始 |
| extract_done | success | ✓ 已提取 N 页文本 | Step 1A 完成 |
| convert_arduino | info | 正在分析 Arduino 代码结构... | Step 1B 开始 |
| convert_done | success | ✓ 识别 M 个函数，K 个 API 映射 | Step 1B 完成 |
| identify_image | info | 正在识别芯片型号... | 图片路径开始 |
| web_search | info | 正在搜索 {chip_model} 数据手册... | 芯片型号路径 |
| web_fetch | info | 正在拉取 GitHub 源码... | GitHub URL 路径 |
| analyze_chip | success | 芯片: {chip}, 协议: {I2C/SPI/UART}, 地址: 0xXX, ID寄存器: {有/无} | 数据手册分析完成 |
| gen_debug | info | 正在生成调试版驱动... | Step 2 |
| gen_debug_done | success | ✓ 调试版驱动已生成 (含 N 项自检) | Step 2 完成 |
| hw_check_devs | info | 正在检测 MicroPython 设备... | Step 3 开始 |
| hw_no_device | warn | 未检测到设备，等待用户选择... | 设备检测失败 |
| hw_run | info | 正在设备上运行验证 (第 N/10 轮)... | 每轮烧录 |
| hw_result_pass | success | ✓ 第 N 轮: SELF_TEST_PASS — 全部自检通过 | 验证通过 |
| hw_result_fail | warn | ✗ 第 N 轮: {错误摘要} → 修复中... | 验证失败 |
| hw_retry | info | 修改 {寄存器/时序/配置}，重新验证... | 进入下一轮 |
| hw_exhausted | danger | ✗ 10 轮验证已达上限，生成排查摘要 | 超限 |
| strip_debug | info | 正在生成生产版驱动... | Step 4 |
| strip_done | success | ✓ 生产版驱动已生成 | Step 4 完成 |
| normalize | info | 正在规范化驱动 (P0 规则)... | Step 5 |
| normalize_done | success | ✓ 规范化完成 (N 条规则已执行) | Step 5 完成 |
| gen_test_material | info | 正在生成独立测试脚本 + 接线参考... | Step 6 |
| gen_test_done | success | ✓ 独立测试脚本 + 接线参考已生成 | Step 6 完成 |
| standalone_test_prompt | info | 等待用户确认接线... | Step 7 弹卡片 |
| standalone_test_run | info | 正在运行独立测试... | Step 7 script_run |
| standalone_test_pass | success | ✓ {chip} 独立测试通过 — 驱动可集成到项目 | Step 7 PASS |
| standalone_test_fail | warn | ✗ {chip} 独立测试失败: {错误摘要} | Step 7 FAIL |
| next_step_prompt | info | 驱动就绪，等待用户选择后续操作... | Step 9 弹卡片 |
| update_manifest | info | 正在更新 manifest... | Step 8 |
| done | success | ✓ 驱动生成完成: {chip}.py | 全部完成 |

### script_run — extract_pdf.py（Step 1A）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "extract_pdf",
    "interpreter": "python",
    "script": ".upy/scripts/extract_pdf.py",
    "args": ["--input", "{user_pdf_path}", "--output", "docs/driver_extracted.json", "--json-summary"],
    "cwd": "{project_dir}",
    "timeout_ms": 30000
  }
}
```

**说明：** PDF 文本提取 (pymupdf)，插件本地执行。`--json-summary` 在 stdout 输出：`{"status":"ok","pages":42,"source":"datasheet.pdf"}`。timeout 30s 覆盖大 PDF（>100 页）。

### script_run — convert_arduino.py（Step 1B）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "convert_arduino",
    "interpreter": "python",
    "script": ".upy/scripts/convert_arduino.py",
    "args": ["--input", "{user_ino_path}", "--output", "docs/driver_mapping.json", "--json-summary"],
    "cwd": "{project_dir}",
    "timeout_ms": 15000
  }
}
```

**说明：** Arduino API 映射 + 代码结构提取。`--json-summary` 输出：`{"status":"ok","functions":12,"api_matches":8}`。

### script_run — run_on_device.py（Step 3）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "run_on_device",
    "interpreter": "python",
    "script": ".upy/scripts/run_on_device.py",
    "args": ["--com", "{COM}", "--file", "firmware/drivers/{chip}_driver/{chip}_debug.py", "--capture", "--timeout-ms", "30000"],
    "cwd": "{project_dir}",
    "timeout_ms": 60000
  }
}
```

**说明：** 通过 mpremote 将 .py 文件送入设备 REPL 执行并捕获 stdout/stderr 输出到 `logs/driver_verify_round{N}.log`。`--json-summary` 输出：`{"status":"ok","output_file":"logs/driver_verify_round1.log","exit_code":0,"duration_ms":12500}`。

**新脚本**，路径 `G:\MicroPython_Skills\upy-deploy\scripts\run_on_device.py`。核心逻辑：
```
mpremote connect {COM} run {file}  →  捕获 stdout/stderr  →  写入 logs/driver_verify_round{N}.log
```

### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "gen-driver",
    "result": "success",
    "summary": "驱动生成完成: SHT30 (I2C, 0x44), 5 轮硬件验证通过, 38 条 P0 规则已执行, 独立测试通过",
    "next_phase": "publish",
    "artifacts": [
      {
        "type": "file_list",
        "title": "生成文件",
        "files": [
          { "path": "docs/driver_understanding.json", "size": 4096, "status": "new", "description": "数据手册分析结果" },
          { "path": "firmware/drivers/sht30_driver/sht30_debug.py", "size": 8192, "status": "new", "description": "调试版驱动 (已验证)" },
          { "path": "firmware/drivers/sht30_driver/sht30.py", "size": 4096, "status": "new", "description": "生产版驱动 (规范化)" },
          { "path": "firmware/drivers/sht30_driver/test_sht30.py", "size": 1024, "status": "new", "description": "独立测试脚本 (极简验证)" },
          { "path": "firmware/drivers/sht30_driver/wiring_sht30.md", "size": 512, "status": "new", "description": "单芯片接线参考" },
          { "path": "logs/driver_verify_round1.log", "size": 2048, "status": "new", "description": "硬件验证第1轮日志" },
          { "path": "logs/driver_verify_round5.log", "size": 1024, "status": "new", "description": "硬件验证第5轮日志 (最终)" }
        ]
      },
      {
        "type": "table",
        "title": "驱动诊断信息",
        "headers": ["指标", "值"],
        "rows": [
          ["芯片型号", "SHT30"],
          ["通信协议", "I2C (地址 0x44)"],
          ["芯片ID寄存器", "无 (使用读写回验证)"],
          ["数据就绪方式", "固定延时 15ms (无状态寄存器)"],
          ["数据完整性", "CRC-8 校验"],
          ["硬件验证轮数", "5 / 10"],
          ["验证结果", "SELF_TEST_PASS"],
          ["P0 规则执行", "38/38"],
          ["数据来源", "Sensirion_Datasheet_SHT3x.pdf Page 4-12"]
        ]
      }
    ],
    "warnings": [],
    "errors": []
  }
}
```

**特殊情况 — 跳过硬件验证：**

```json
{
  "warnings": [
    "⚠️ 未经硬件验证：用户选择跳过 Step 3。驱动逻辑基于数据手册分析，未在实际设备上运行。建议在部署前手动测试。"
  ]
}
```

**特殊情况 — 10 轮耗尽：**

```json
{
  "result": "partial",
  "summary": "驱动生成未完成: SHT30 (I2C, 0x44), 10 轮验证未通过, 调试版驱动已保留",
  "errors": [
    "硬件验证 10 轮后仍未通过：I2C 读写回测试持续失败 (Wrote 0x00, read-back 0xFF)。排查方向：确认 I2C 地址 0x44 正确、检查 SDA/SCL 上拉电阻、确认供电 3.3V。详见 logs/driver_verify_round*.log"
  ]
}
```

---

## 四、SKILL.md 修改点

共 10 处改动：

| 序号 | 位置 | 当前行为 | 改为 | 原因 |
|------|------|---------|------|------|
| 1 | 前置条件 | `mpremote` 可用 + Python 3 + `pymupdf` | 删除。pymupdf 由插件环境保证（script_run 在插件端执行），mpremote 替换为 device_command | 服务端不感知环境 |
| 2 | Step 0 输入判断 | LLM 直接判断用户上传了什么 | `approval_request`(gen_driver_input) 卡片：拖拽上传 + 缩略图 + GitHub URL + 芯片型号。若 start_phase 已带 source 且文件齐全则跳过 | 插件端文件上传 UI |
| 3 | Step 1A PDF 提取 | `python extract_pdf.py --input ...` 本地执行 | `script_run(extract_pdf.py ... --json-summary)` → 插件执行 → `file_operation(read)` 回读 JSON → LLM 分析 | 插件执行脚本，服务器读结果 |
| 4 | Step 1B Arduino 转换 | `python convert_arduino.py --input ...` 本地执行 | `script_run(convert_arduino.py ... --json-summary)` → `file_operation(read)` 回读映射 + 原始源码 → LLM 翻译 | 同上 |
| 5 | Step 2 生成调试版 | LLM 写本地文件 | `file_operation(write)` → `firmware/drivers/{chip}_driver/{chip}_debug.py` | 统一文件操作 |
| 6 | Step 3 硬件验证 | `mpremote devs` + `mpremote resume run` | `device_command(devs)` 检测 → `script_run(run_on_device.py ... --capture)` 执行+捕获 → LLM 分析 → Edit + `file_operation(write)` → 循环。无设备时 `approval_request`(gen_driver_no_device) 三选一 | 服务器无硬件访问 |
| 7 | Step 4 脱调试 | LLM 写本地文件 | `file_operation(write)` → `firmware/drivers/{chip}_driver/{chip}.py` | 统一文件操作 |
| 8 | Step 5 规范化 | `Skill("upy-norm-driver")` 嵌套调用 | 删除嵌套调用。LLM 直接按 upy-norm-driver 的 38 条 P0 规则改写，`file_operation(write)` 覆盖 | 纯 LLM 代码转换，无需 skill 切换开销 |
| 9 | 新增 Step 6-8 | 无（原 SKILL.md 到 Step 5 结束，无独立验证收尾） | Step 6: 生成 test_{chip}.py + wiring_{chip}.md（必有）。Step 7: `approval_request`(gen_driver_standalone_test) 弹接线表 + 可选上电测试。Step 8: 条件更新 manifest（仅 pipeline 触发时有 manifest） | gen-driver 是独立 skill，用户拿到驱动后第一件事应该是上电接线单独测试 |
| 10 | 新增 Step 9 | 无（原 SKILL.md 无"下一步"选择） | `approval_request`(gen_driver_next_step) 弹三选一卡片：发布到 upypi / 集成到项目 / 结束。phase_complete 设置 next_phase 对应值 | gen-driver 独立 skill，驱动就绪后需明确后续路径 |

---

## 五、脚本改动

### extract_pdf.py

**路径：** `G:\MicroPython_Skills\upy-gen-driver\scripts\extract_pdf.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json-summary` | 成功时 stdout 输出 `{"status":"ok","pages":N,"source":"..."}`，失败时 `{"status":"error","message":"..."}` |

**其余无需改。** 脚本保持纯文本提取，不做结构化理解。

### convert_arduino.py

**路径：** `G:\MicroPython_Skills\upy-gen-driver\scripts\convert_arduino.py`

| 改动 | 内容 |
|------|------|
| 新增 `--json-summary` | 成功时 stdout 输出 `{"status":"ok","functions":N,"api_matches":M,"includes":[...]}` |

**其余无需改。** 脚本保持 API 映射 + 结构提取，不翻译代码。

### run_on_device.py（新建）

**路径：** `G:\MicroPython_Skills\upy-deploy\scripts\run_on_device.py`

**功能：** 通过 mpremote 将指定 .py 文件送入设备 REPL 执行，捕获 stdout/stderr，写入日志文件。

| 参数 | 说明 |
|------|------|
| `--com` | COM 端口号 |
| `--file` | 要执行的 .py 文件路径（相对于项目目录） |
| `--capture` | 启用输出捕获（写入日志文件） |
| `--timeout-ms` | 设备执行超时 (ms)，默认 30000 |
| `--json-summary` | 成功时 stdout 输出 `{"status":"ok","output_file":"...","exit_code":0,"duration_ms":12000}` |

### upy-norm-driver

**无需改。** gen-driver Step 5 由 LLM 直接执行 P0 规则改写（纯代码转换），不调用外部脚本或嵌套 skill。

---

## 六、对 upy-scaffold 的影响

| 源文件 | 目标位置 | 用途 |
|--------|---------|------|
| `upy-gen-driver/scripts/extract_pdf.py` | `{project}/.upy/scripts/extract_pdf.py` | PDF 文本提取（Step 1A） |
| `upy-gen-driver/scripts/convert_arduino.py` | `{project}/.upy/scripts/convert_arduino.py` | Arduino API 映射（Step 1B） |
| `upy-deploy/scripts/run_on_device.py` (新建) | `{project}/.upy/scripts/run_on_device.py` | 设备 REPL 执行+捕获（Step 3） |

**与 deploy 共用 flash_device.py。验证循环复用 run_on_device.py。**

---

## 七、插件端 UI 组件

| 组件 | 对应消息 | 说明 |
|------|---------|------|
| 文件上传卡片 | approval_request `gen_driver_input` | 拖拽/点击上传 PDF/代码/图片，缩略图列表，GitHub URL / 芯片型号输入 |
| 文件缩略图 | file_upload.generate_thumbnails | PDF 第 1 页缩略图、代码文件图标、图片缩放图 |
| 无设备提示 | approval_request `gen_driver_no_device` | 三选一（重新检测/跳过验证/稍后继续） |
| 进度时间线 | status_update × ~22 | 预处理→分析→生成→验证循环(N/10)→脱调试→规范化→独立验证材料→上电测试 |
| 验证循环进度 | status_update hw_run + hw_result_pass/fail | 每轮绿色/红色标识 PASS/FAIL + 错误摘要 |
| 独立测试接线卡片 | approval_request `gen_driver_standalone_test` | 单芯片接线表 + 电源要求 + 上拉电阻提醒，二选一（测试/稍后） |
| 独立测试结果 | status_update standalone_test_pass/fail | PASS 绿色 / FAIL 红色 + 错误摘要 + 排查入口 |
| 驱动文件预览 | phase_complete file_list | 点击 {chip}.py 查看生产版驱动源码 |
| 调试版驱动预览 | phase_complete file_list | 点击 {chip}_debug.py 查看含自检的调试版 |
| 独立测试脚本预览 | phase_complete file_list | 点击 test_{chip}.py 查看极简测试脚本 |
| 接线参考预览 | phase_complete file_list | 点击 wiring_{chip}.md 查看单芯片接线参考 |
| 验证日志预览 | phase_complete file_list | 点击 .log 查看每轮验证的完整 REPL 输出 |
| 诊断信息面板 | phase_complete table | 芯片/协议/验证轮数/数据来源/P0 执行数 |
| [生成驱动] 按钮 | 触发 start_phase | analyze 搜不到驱动后启用，或独立入口手动触发 |
| [继续验证] 按钮 | 触发 start_phase (续接) | result=partial 时，从 Step 3 继续 |
| [独立测试] 按钮 | 触发 start_phase (续接) | 选"稍后测试"后，可从 Step 7 续接 |
| 下一步选择卡片 | approval_request `gen_driver_next_step` | 三选一（发布/集成/结束），`has_manifest=false` 时"集成" disabled |
| [发布到 upypi] 入口 | phase_complete next_phase | next_phase="publish" 时自动触发 upy-publish skill |

---

## 八、独立测试场景

### 插件端测试（无服务器）

1. 手动发 approval_request `gen_driver_input` → 验证文件拖拽上传、缩略图展示、删除文件、GitHub URL / 芯片型号输入
2. 手动发 `script_run`(extract_pdf.py) → 验证 PDF 提取 + `--json-summary` 输出正确
3. 手动发 `script_run`(convert_arduino.py) → 验证 Arduino 映射 + `--json-summary` 输出正确
4. 手动发 `script_run`(run_on_device.py) → 验证设备执行 + 日志文件生成 + `--json-summary` 输出
5. 手动发 `device_command(devs)` → (mock 空) → 验证 approval_request `gen_driver_no_device` 卡片 + 三选一
6. 手动发 `status_update` 序列 → 验证完整进度时间线（含验证循环 N/10 进度）
7. 手动发 `phase_complete` (file_list + table) → 验证文件列表 + 诊断信息面板
8. mock result=partial (10 轮耗尽) → 验证 errors 展示 + [继续验证] 按钮
9. mock result=success + warnings (跳过验证) → 验证 ⚠️ 标注
10. 手动发 approval_request `gen_driver_standalone_test` → 验证接线表展示 + 二选一
11. 手动发 `script_run`(run_on_device.py --file test_{chip}.py) → 验证独立测试执行 + PASS/FAIL 输出
12. 手动发 approval_request `gen_driver_next_step` → 验证三选一（发布/集成/结束），`has_manifest=false` 时"集成" disabled
13. mock phase_complete next_phase="publish" → 验证插件自动触发 upy-publish skill
14. mock phase_complete next_phase="generate" → 验证插件回到主流程
15. mock phase_complete next_phase=null → 验证插件显示"完成"

### Skill 端测试（无插件）

1. mock 完整的 `source.type=pdf` + files[].content 含提取文本 → 验证 LLM 正确生成 understanding.json（协议、地址、ID寄存器、数据就绪方式、数据完整性）
2. mock `source.type=arduino` + files[].content 含映射 JSON + 原始源码 → 验证 LLM 正确翻译为 MPY（不能机械逐行）
3. mock `source.type=image` + files[].content_base64 → 验证 LLM 多模态识别芯片型号
4. mock `source.type=github_url` → 验证 WebFetch 拉取 + 翻译
5. mock `source.type=chip_model`="SHT30" → 验证 WebSearch → 找到 datasheet URL → 通知用户下载
6. mock device_command(devs) 返回空 → 验证 gen_driver_no_device 卡片 + skip 路径（最终输出带 ⚠️ 标注）+ save 路径（result=partial）
7. mock 验证第 1 轮 SELF_TEST_PASS → 验证正常退出循环进 Step 4
8. mock 验证第 3 轮 SELF_TEST_PASS → 验证中间轮次修复后通过
9. mock 验证 10 轮全 FAIL → 验证 result: "partial" + errors 排查摘要
10. 验证 Step 6 生成 test_{chip}.py + wiring_{chip}.md 内容正确（极简、不含调试打印、接线表准确）
11. 验证 Step 7 approval_request wiring 表信息提取正确（引脚映射、上拉电阻提醒、地址确认）
12. mock 独立测试 PASS → 验证 phase_complete summary 含"独立测试通过"
13. mock 独立测试 FAIL → 验证回到 Step 3 循环 + 再次触发 Step 7 卡片 header 标注"(第 2 次)"
14. mock manifest 存在（pipeline 触发）→ 验证 Step 8 更新 manifest drivers 字段
15. mock manifest 不存在（独立触发）→ 验证 Step 8 跳过，不报错
16. 对比规范化前后的 {chip}.py → 验证 38 条 P0 规则全部执行（中间件库跳过 #16/#16a/#16b/#16c/#29/#34-#38）
17. mock has_manifest=true（pipeline 触发）→ 验证 Step 8 更新 manifest + Step 9 "集成"选项可用
18. mock has_manifest=false（独立触发）→ 验证 Step 8 跳过 + Step 9 "集成"选项 disabled
19. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
