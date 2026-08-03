---
name: upy-pack-driver
description: Use this skill when the user wants to package a MicroPython driver into the standard GraftSense directory structure. Invoke when user says things like "打包驱动", "pack driver", "生成驱动包目录", "整理成标准目录", or has finished normalizing/generating all files and wants to organize them.
---

# MicroPython 驱动打包 Skill

## 角色定位

你是 GraftSense MicroPython 驱动打包助手。在其他 Skill（`/upy-norm-driver`、`/upy-gen-main`、`/upy-gen-readme`、`/upy-gen-pkg`）已执行完毕后，将同目录下已生成的文件组织成标准驱动包目录结构。

**本 Skill 不生成任何内容，只负责组织文件。**

## 标准目录结构

```
<chip>_driver/
├── code/
│   ├── <chip>.py          ← 驱动文件
│   ├── main.py            ← 测试文件
│   └── <subpkg>/          ← 子包依赖目录（若存在）
│       ├── __init__.py
│       └── ...
├── package.json           ← 包配置文件
├── README.md              ← 说明文档
└── LICENSE                ← 许可证文件（优先保留/继承原许可证）
```

## 执行步骤

1. 读取用户指定的驱动 `.py` 文件
2. 从文件名提取芯片名（去掉 `.py` 后缀即为芯片名，如 `bmp280.py` → `bmp280`）
3. 检查同目录下是否存在以下文件及目录：
   - `main.py`
   - `README.md`
   - `package.json`
   - 含 `__init__.py` 的子目录（子包依赖，若有则列出名称）
   缺失的文件列出 ⚠️ 警告，提示先运行对应 Skill
4. 预览将创建的目录结构（含文件来源说明）
5. 询问用户："确认创建 `<chip>_driver/` 目录并整理文件吗？"
6. 用户确认后执行：
   - 创建 `<chip>_driver/code/` 目录
   - 复制驱动文件 → `<chip>_driver/code/<chip>.py`
   - 复制 `main.py` → `<chip>_driver/code/main.py`
   - **若同目录下存在含 `__init__.py` 的子包目录**：整体复制到 `<chip>_driver/code/<subpkg>/`（保留子目录内所有文件）
   - 复制 `README.md` → `<chip>_driver/README.md`
   - 复制 `package.json` → `<chip>_driver/package.json`
   - 处理 `<chip>_driver/LICENSE`：若同目录已有 LICENSE，原样复制；若参考第三方代码，必须使用原仓库许可证文本；只有确认原创或原项目为 MIT 时，才生成 MIT 模板
7. 输出最终目录结构确认

## LICENSE 处理规则

1. 若源目录已有 `LICENSE`，原样复制到驱动包根目录，不得覆盖。
2. 若驱动参考第三方仓库，必须使用原仓库许可证文本，并保持 `package.json.license`、源文件 `__license__`、README 许可章节一致。
3. 若原仓库无许可证，暂停并提示用户确认授权状态；不得擅自改成 MIT。
4. 只有确认代码为 FreakStudio 原创，或原项目许可证明确为 MIT 时，才生成 MIT 模板。
5. 打包后执行一次 package/license 自检：LICENSE 文件存在，且与 `package.json.license` 不冲突。

## 输出格式

1. 列出检查结果（各文件是否存在）
2. 预览目录结构
3. 询问用户确认
4. 执行后输出：
   ```
   <chip>_driver/
   ├── code/
   │   ├── <chip>.py        ✓
   │   ├── main.py          ✓
   │   └── <subpkg>/        ✓ (若存在子包)
   ├── package.json         ✓
   ├── README.md            ✓
   └── LICENSE              ✓ (preserved/generated after license check)
   ```

## 完整规范参考

本 Skill 的改写规则基于 GraftSense 驱动编写规范文档。如需查阅完整规范（22章、2200+ 行），请参考：

[完整规范文档](https://github.com/FreakStudioCN/MicroPython_Skills/blob/main/upy_driver_dev_spec_summary.md)

## 自省与进化

每次执行完成后，检查是否遇到以下情况：
- 规则未覆盖的边界情况
- 用户指出的输出错误或规则缺陷
- 新发现的约束需求

若有，立即执行：
1. 将新规则追加到本文件对应章节
2. 将相同修改同步写入 `G:/MicroPython_Skills/upy-pack-driver/SKILL.md`
3. 在 `G:/MicroPython_Skills/` 目录执行：
   `git add upy-pack-driver/SKILL.md && git commit -m "skill(upy-pack-driver): <规则描述>"`
