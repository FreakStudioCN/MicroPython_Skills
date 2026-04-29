---
name: fetch-doc
description: Use this skill when the user provides a URL and wants to extract key information from it. Supports GitHub files, upypi pages, and general web pages. Invoke when user says things like "帮我看一下这个链接", "从这个URL提取信息", "这个页面说了什么", "读取这个文档", or pastes any URL and asks about its content.
---

# 文档获取与关键信息提取 Skill

## 角色定位

给定任意 URL，自动获取内容并提取关键信息。支持 GitHub 文件、upypi 包页面、普通网页等。

## 脚本路径

```
{skill_dir}/scripts/fetch_github.py
```

用法：
```bash
# 获取文本内容
python {skill_dir}/scripts/fetch_github.py "{url}"

# 下载图片
python {skill_dir}/scripts/fetch_github.py --image "{url}" "{save_dir}"
```

## 执行步骤

### 第一步：识别 URL 类型

| URL 特征 | 处理方式 |
|---|---|
| `github.com/.../blob/...` | 自动转换为 raw URL，脚本获取 |
| `raw.githubusercontent.com/...` | 直接用脚本获取 |
| `upypi.net/pkgs/...` | curl 获取 JSON |
| 图片（.png/.jpg/.gif） | `--image` 参数下载到本地 |
| 其他网页 | curl 或脚本获取 HTML，提取正文 |

### 第二步：获取内容

优先用 Bash 工具调用脚本：
```bash
python "C:/Users/Administrator/.claude/skills/fetch-doc/scripts/fetch_github.py" "{url}" 2>/dev/null
```

GitHub URL 自动转换，SSL 证书问题自动跳过。

### 第三步：提取关键信息

根据内容类型提取：

| 内容类型 | 提取重点 |
|---|---|
| README.md | 简介、功能列表、快速开始代码、注意事项 |
| 驱动 .py | 类名、构造参数、公共 API 表格 |
| package.json | 包名、版本、依赖、文件列表 |
| 普通文档 | 标题结构、核心段落、代码块 |

### 第四步：输出

以用户问题为导向输出，不固定格式。若用户只是"看一下"，输出摘要；若用户问具体问题，直接回答。
