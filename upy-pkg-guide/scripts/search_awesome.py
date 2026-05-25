"""
search_awesome.py — 从 awesome-micropython 索引中搜索驱动包

用法:
    python search_awesome.py <chip_name>

示例:
    python search_awesome.py spacecan
    python search_awesome.py BMP280
    python search_awesome.py MPU6050

返回格式 (JSON):
    {
        "query": "spacecan",
        "results": [
            {
                "name": "micropython-spacecan",
                "url": "https://gitlab.com/...",
                "desc": "...",
                "category": "Communications",
                "subcategory": "CAN"
            }
        ]
    }
"""

import sys
import json
import re
import urllib.request
import base64


GITHUB_API = "https://api.github.com/repos/mcauser/awesome-micropython/contents/readme.md"
# 本地缓存路径（与脚本同目录）
import os
CACHE_FILE = os.path.join(os.path.dirname(__file__), "_awesome_cache.json")
CACHE_MAX_AGE_SECONDS = 86400  # 24 小时


def fetch_readme():
    """拉取 readme.md，优先使用本地缓存"""
    import time

    # 检查缓存是否有效
    if os.path.exists(CACHE_FILE):
        age = time.time() - os.path.getmtime(CACHE_FILE)
        if age < CACHE_MAX_AGE_SECONDS:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return f.read()

    # 拉取远端
    req = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": "upy-pkg-guide/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = base64.b64decode(data["content"]).decode("utf-8")

    # 写缓存
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    return content


def parse_index(content):
    """
    解析 README，返回结构：
    { category: { subcategory: [ {name, url, desc} ] } }
    """
    index = {}
    current_category = None
    current_subcategory = None
    entry_re = re.compile(r"^\* \[([^\]]+)\]\(([^)]+)\)\s*[-–]\s*(.+)")

    for line in content.split("\n"):
        line = line.rstrip()
        if line.startswith("### "):
            current_category = line[4:].strip()
            index[current_category] = {}
        elif line.startswith("#### "):
            current_subcategory = line[5:].strip()
            if current_category:
                index[current_category].setdefault(current_subcategory, [])
        elif m := entry_re.match(line):
            if current_category and current_subcategory and \
                    current_subcategory in index.get(current_category, {}):
                index[current_category][current_subcategory].append({
                    "name": m.group(1),
                    "url": m.group(2),
                    "desc": m.group(3).strip(),
                })

    return index


def search(index, query):
    """
    大小写不敏感地在库名和描述中搜索 query，返回匹配条目列表。
    每条目附带 category 和 subcategory。
    """
    q = query.upper()
    hits = []
    for category, subcats in index.items():
        for subcat, entries in subcats.items():
            for e in entries:
                if q in e["name"].upper() or q in e["desc"].upper():
                    hits.append({
                        **e,
                        "category": category,
                        "subcategory": subcat,
                    })
    return hits


def infer_repo_type(url):
    """根据 URL 判断托管平台"""
    if "github.com" in url:
        return "github"
    elif "gitlab.com" in url:
        return "gitlab"
    elif "codeberg.org" in url:
        return "codeberg"
    else:
        return "unknown"


def get_repo_files(url):
    """
    给定仓库 URL，返回 .py 文件列表 (path, raw_url)。
    支持 GitHub 和 GitLab。
    """
    repo_type = infer_repo_type(url)
    files = []

    if repo_type == "github":
        # 解析 owner/repo（处理可能的子路径，如 .../tree/master/subdir）
        path_parts = url.rstrip("/").split("github.com/")[-1].split("/")
        owner, repo = path_parts[0], path_parts[1]
        # 如果是直接指向 .py 文件
        if len(path_parts) > 2 and path_parts[-1].endswith(".py"):
            raw_url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            return [{"path": path_parts[-1], "raw_url": raw_url}]
        # 仓库根目录
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/"
        req = urllib.request.Request(api_url, headers={"User-Agent": "upy-pkg-guide/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            entries = json.loads(resp.read().decode("utf-8"))
        for entry in entries:
            if entry["name"].endswith(".py"):
                files.append({"path": entry["path"], "raw_url": entry["download_url"]})

    elif repo_type == "gitlab":
        # 解析 namespace/project
        path_parts = url.rstrip("/").split("gitlab.com/")[-1].split("/")
        namespace = path_parts[0]
        project = path_parts[1]
        encoded = urllib.parse.quote(f"{namespace}/{project}", safe="")
        api_url = f"https://gitlab.com/api/v4/projects/{encoded}/repository/tree?recursive=true"
        req = urllib.request.Request(api_url, headers={"User-Agent": "upy-pkg-guide/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            entries = json.loads(resp.read().decode("utf-8"))
        for entry in entries:
            if entry["type"] == "blob" and entry["path"].endswith(".py"):
                raw_url = f"https://gitlab.com/{namespace}/{project}/-/raw/master/{entry['path']}"
                files.append({"path": entry["path"], "raw_url": raw_url})

    return files


def fetch_text(raw_url):
    """下载文本文件，失败返回 None"""
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "upy-pkg-guide/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


if __name__ == "__main__":
    import urllib.parse

    if len(sys.argv) < 2:
        print("用法: python search_awesome.py <chip_name>", file=sys.stderr)
        sys.exit(1)

    query = sys.argv[1]

    try:
        content = fetch_readme()
    except Exception as e:
        print(json.dumps({"error": f"无法获取 awesome-micropython 索引: {e}"}))
        sys.exit(1)

    index = parse_index(content)
    results = search(index, query)

    output = {"query": query, "results": results}
    # Windows 终端兼容输出
    sys.stdout.buffer.write(json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")
