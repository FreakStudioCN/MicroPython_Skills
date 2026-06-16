# upy-publish 接口定义

> 状态：✅ 已定稿
>
> 收尾 Phase — 驱动规范打包 + 发布 upypi。将 gen-driver 生成的生产版驱动组织为标准目录结构，生成 README/package.json/LICENSE，可选发布到 upypi。

---

## 一、Skill 概述

| 项目 | 内容 |
|------|------|
| Phase | publish |
| 上游 Skill | upy-gen-driver（Step 9 用户选"发布"时自动进入）或用户手动触发 |
| 下游 Skill | 无（终点） |
| 一句话职责 | 读取生产版驱动 → LLM 生成 README + package.json → 脚本打包标准目录 → 可选上传 upypi |

**核心约束：**
- 不重复规范化——驱动文件已经过 gen-driver Step 5 的 P0 规则处理
- package.json 的 deps 查询 upypi 需插件端执行 curl
- 上传 upypi 为可选步骤，需用户确认

---

## 二、插件输入 → Skill（P→S）

```json
{
  "type": "start_phase",
  "phase": "publish",
  "session_id": "uuid-xxx",
  "payload": {
    "manifest": { },
    "driver_path": "firmware/drivers/sht30_driver/sht30.py",
    "driver_dir": "firmware/drivers/sht30_driver",
    "test_passed": true,
    "chip": "SHT30"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `manifest` | object? | 否 | 项目 manifest，有则写入 package.json 的 project 字段 |
| `driver_path` | string | 是 | 生产版驱动 .py 文件路径 |
| `driver_dir` | string | 是 | 驱动目录路径（含 test_{chip}.py / wiring_{chip}.md） |
| `test_passed` | bool | 是 | 硬件验证是否通过（false 时 README 加 ⚠️ 标注） |
| `chip` | string | 是 | 芯片型号 |

---

## 三、Skill 输出 → 插件（S→P）

### 消息序列

```
Step 1: 读取驱动文件
  → file_operation(read) → {driver_path}
  → (若 test_{chip}.py 存在) → file_operation(read) → test_{chip}.py
  → status_update "正在分析驱动结构..."

Step 2: 生成 README
  → LLM 按 gen-readme 模板分析 → file_operation(write) → {driver_dir}/README.md
  → status_update "✓ README.md 已生成"

Step 3: 查询 upypi 依赖
  → (解析驱动 import，提取第三方依赖)
  → script_run(curl upypi 查询每个依赖)
  → status_update "正在查询 upypi 依赖..."

Step 4: 生成 package.json
  → LLM 生成完整 package.json → file_operation(write) → {driver_dir}/package.json
  → status_update "✓ package.json 已生成"

Step 5: 打包标准目录
  → script_run(pack_driver.py --input {driver_dir} --output {project_dir}/{chip}_driver/)
  → status_update "✓ 标准目录已生成"

Step 6: 上传 upypi（可选）
  → approval_request: publish_confirm 卡片
  → (确认) → script_run(publish_to_upypi.py --package {chip}_driver/)
  → status_update "✓ 已发布到 upypi"
  → (取消) → 跳过

输出
  → phase_complete(file_list + package_info)
```

### approval_request — 发布确认卡片（publish_confirm）

```
┌──────────────────────────────────────────────┐
│  发布驱动到 upypi？                            │
│                                              │
│  驱动包已就绪：                                │
│  sht30_driver/                                │
│  ├── code/sht30.py                            │
│  ├── code/test_sht30.py                       │
│  ├── package.json                             │
│  ├── README.md                                │
│  └── LICENSE                                  │
│                                              │
│  ○ 发布到 upypi                                │
│  ○ 仅打包，暂不发布                            │
│                                              │
│  [确认]                                       │
└──────────────────────────────────────────────┘
```

```json
{
  "type": "approval_request",
  "payload": {
    "approval_id": "publish_confirm",
    "header": "发布驱动到 upypi？",
    "question": "驱动包已就绪，是否发布到 upypi？",
    "summary": {
      "package_name": "sht30_driver",
      "version": "1.0.0",
      "chip": "SHT30",
      "test_passed": true
    },
    "items": [
      {
        "id": "publish",
        "name": "发布到 upypi",
        "subtitle": "上传到 upypi，社区可用 mip 安装",
        "selected": true
      },
      {
        "id": "skip",
        "name": "仅打包，暂不发布",
        "subtitle": "保留标准目录结构，稍后手动上传",
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

### status_update 列表

| step_id | level | message | 触发时机 |
|---------|-------|---------|---------|
| read_driver | info | 正在分析驱动结构... | Step 1 |
| gen_readme | info | 正在生成 README.md... | Step 2 |
| gen_readme_done | success | ✓ README.md 已生成 | Step 2 完成 |
| query_upypi | info | 正在查询 upypi 依赖... | Step 3 |
| query_upypi_done | success | ✓ N 个依赖已解析 | Step 3 完成 |
| gen_pkg | info | 正在生成 package.json... | Step 4 |
| gen_pkg_done | success | ✓ package.json 已生成 | Step 4 完成 |
| pack | info | 正在打包标准目录... | Step 5 |
| pack_done | success | ✓ {chip}_driver/ 目录已生成 | Step 5 完成 |
| publish_confirm | info | 等待用户确认发布... | Step 6 弹卡片 |
| publish_run | info | 正在发布到 upypi... | Step 6 执行 |
| publish_done | success | ✓ 已发布到 upypi: {package_name} v{version} | 发布成功 |
| done | success | ✓ 打包发布完成 | 全部完成 |

### script_run — upypi 依赖查询（Step 3）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "upypi_query",
    "interpreter": "shell",
    "script": "curl",
    "args": ["-s", "https://upypi.net/api/search?q={dependency_name}"],
    "cwd": "{project_dir}",
    "timeout_ms": 10000
  }
}
```

### script_run — 打包目录（Step 5）

```json
{
  "type": "script_run",
  "payload": {
    "script_id": "pack_driver",
    "interpreter": "python",
    "script": ".upy/scripts/pack_driver.py",
    "args": ["--input", "{driver_dir}", "--output", "{project_dir}/{chip}_driver/", "--json-summary"],
    "cwd": "{project_dir}",
    "timeout_ms": 15000
  }
}
```

### phase_complete

```json
{
  "type": "phase_complete",
  "payload": {
    "phase": "publish",
    "result": "success",
    "summary": "驱动打包完成: sht30_driver v1.0.0, 已发布到 upypi",
    "next_phase": null,
    "manifest_content": {},
    "artifacts": [
      {
        "type": "file_list",
        "title": "打包文件",
        "files": [
          { "path": "sht30_driver/code/sht30.py", "size": 4096, "status": "new", "description": "生产版驱动" },
          { "path": "sht30_driver/code/test_sht30.py", "size": 1024, "status": "new", "description": "独立测试脚本" },
          { "path": "sht30_driver/README.md", "size": 3072, "status": "new", "description": "使用说明" },
          { "path": "sht30_driver/package.json", "size": 1024, "status": "new", "description": "包配置" },
          { "path": "sht30_driver/LICENSE", "size": 1071, "status": "new", "description": "MIT 许可证" }
        ]
      },
      {
        "type": "table",
        "title": "包信息",
        "headers": ["字段", "值"],
        "rows": [
          ["包名", "sht30_driver"],
          ["版本", "1.0.0"],
          ["芯片", "SHT30"],
          ["协议", "I2C (0x44)"],
          ["硬件验证", "✓ 已通过"],
          ["upypi 状态", "已发布 (https://upypi.net/package/sht30_driver)"]
        ]
      }
    ],
    "warnings": [],
    "errors": []
  }
}
```

---

## 四、脚本改动

### pack_driver.py（新建）

**路径：** `G:\MicroPython_Skills\upy-pack-driver\scripts\pack_driver.py`（由 scaffold 复制到 `{project}/.upy/scripts/pack_driver.py`）

**功能：** 将驱动目录下的文件组织为 upypi 标准目录结构：

```
{chip}_driver/
├── code/
│   ├── {chip}.py          ← 生产版驱动
│   └── test_{chip}.py     ← 独立测试脚本（若存在）
├── package.json           ← 包配置
├── README.md              ← 使用说明
└── LICENSE                ← MIT 许可证
```

| 参数 | 说明 |
|------|------|
| `--input` | 驱动目录路径 |
| `--output` | 输出目录路径 |
| `--json-summary` | stdout 输出 `{"status":"ok","package_path":"...","files":N}` |

### upy-norm-pkg / upy-gen-readme / upy-gen-pkg

**无需改。** publish skill 由 LLM 直接生成 README 和 package.json（纯代码生成），不嵌套调用其他 skill。pack_driver.py 执行目录组织。

---

## 五、对 upy-scaffold 的影响

| 源文件 | 目标位置 | 用途 |
|--------|---------|------|
| `upy-pack-driver/scripts/pack_driver.py` | `{project}/.upy/scripts/pack_driver.py` | 打包标准目录（Step 5） |

---

## 六、插件端 UI 组件

| 组件 | 对应消息 | 说明 |
|------|---------|------|
| 进度时间线 | status_update × ~8 | 分析→README→依赖查询→package.json→打包→发布 |
| 发布确认卡片 | approval_request `publish_confirm` | 二选一（发布/仅打包） |
| 打包文件预览 | phase_complete file_list | 点击查看各文件内容 |
| 包信息面板 | phase_complete table | 包名/版本/芯片/协议/验证状态/upypi URL |
| [发布驱动] 按钮 | 触发 start_phase | gen-driver next_step 选"发布"时自动触发 |

---

## 七、独立测试场景

### 插件端测试（无服务器）

1. 手动发 approval_request `publish_confirm` → 验证二选一 + 点击确认
2. 手动发 `status_update` 序列 → 验证 6 阶段进度
3. 手动发 `phase_complete` (file_list + table) → 验证打包文件列表 + 包信息面板

### Skill 端测试（无插件）

1. 准备已规范化的驱动文件 → mock file_operation(read) 返回内容
2. 验证 LLM 正确生成 README（硬件要求/接线表/API/示例代码）
3. 验证 LLM 正确生成 package.json（name/version/urls/deps/chips/fw）
4. mock upypi 查询返回→验证 deps 字段正确
5. mock pack_driver.py → 验证标准目录结构输出
6. 检查所有发出的消息 JSON 符合 02-protocol.md Schema
