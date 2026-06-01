#!/usr/bin/env python3
"""upy-generate Phase 1: 驱动下载。

从 project-manifest.json 读取 devices 列表，下载驱动 .py 文件到 lib/，
同时拉取 README.md 和 code/main.py 作为 LLM 理解驱动的参考材料。

用法：
  python download_drivers.py --project-dir G:/ai_project/test
"""

import argparse
import json
import os
import re
import sys
import warnings
from datetime import datetime, timezone

import requests

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

UPYPI_BASE = "https://upypi.net"

# ── Chinese-to-English name mapping ──
_CN_NAME_MAP = {
    "有源蜂鸣器": "buzzer", "无源蜂鸣器": "buzzer", "蜂鸣器": "buzzer",
    "温湿度传感器": "temp_hum_sensor", "气压传感器": "pressure_sensor",
    "显示屏": "display", "按键": "button", "按钮": "button",
    "继电器": "relay", "红外传感器": "ir_sensor",
    "电机": "motor", "舵机": "servo", "指示灯": "led",
    "面包板": "breadboard", "杜邦线": "dupont_wire",
}


def safe_var_name(name: str) -> str:
    for cn, en in _CN_NAME_MAP.items():
        if cn in name:
            return en
    ascii_name = name.encode("ascii", errors="ignore").decode("ascii")
    ascii_name = re.sub(r'[^a-zA-Z0-9_]', '_', ascii_name)
    ascii_name = re.sub(r'_+', '_', ascii_name).strip('_').lower()
    return ascii_name or "device"


def load_manifest(project_dir: str) -> dict:
    path = os.path.join(project_dir, "project-manifest.json")
    if not os.path.exists(path):
        print("[ERROR] project-manifest.json not found: {}".format(path), file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════════
#  Download helpers
# ═══════════════════════════════════════════════════════════════

def _http_get(url: str, timeout: int = 30) -> requests.Response:
    """GET request, returns Response or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout, verify=False)
        if resp.status_code != 200:
            return None
        return resp
    except Exception:
        return None


def _write_file(dest: str, content: str) -> bool:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(content)
    return True


# ═══════════════════════════════════════════════════════════════
#  upypi download
# ═══════════════════════════════════════════════════════════════

def _download_upypi(package_name: str, version: str, lib_dir: str, name: str) -> list:
    """Download driver .py + README.md + code/main.py from upypi.

    Returns list of dicts: {path, type} where type is 'driver'|'readme'|'example'.
    """
    base = "{}/pkgs/{}/{}".format(UPYPI_BASE, package_name, version)
    downloaded = []

    # 1) Fetch package.json for file list
    pkg_resp = _http_get("{}/package.json".format(base))
    if pkg_resp is None:
        print("[WARN] Failed to fetch package.json for {}".format(package_name), file=sys.stderr)
        return downloaded
    pkg = pkg_resp.json()

    # 2) Download driver .py files (from urls)
    for entry in pkg.get("urls", []):
        if len(entry) >= 2:
            target_name, source_path = entry[0], entry[1]
            file_url = "{}/{}".format(base, source_path)
            resp = _http_get(file_url)
            if resp is None:
                print("[WARN] Failed to download {}".format(target_name), file=sys.stderr)
                continue
            dest = os.path.join(lib_dir, target_name)
            _write_file(dest, resp.text)
            print("[OK] lib/{}".format(target_name))
            downloaded.append({"path": dest, "type": "driver", "filename": target_name})

    # 3) Try to download README.md (reference for LLM)
    readme_resp = _http_get("{}/README.md".format(base))
    if readme_resp is not None and readme_resp.text.strip():
        # Strip leading "# " from first heading to build filename
        dest = os.path.join(lib_dir, "{}_README.md".format(name))
        _write_file(dest, readme_resp.text)
        print("[OK] lib/{}_README.md (reference)".format(name))
        downloaded.append({"path": dest, "type": "readme", "filename": "{}_README.md".format(name)})

    # 4) Try to download code/main.py (reference example for LLM)
    main_resp = _http_get("{}/code/main.py".format(base))
    if main_resp is not None and main_resp.text.strip():
        dest = os.path.join(lib_dir, "{}_example.py".format(name))
        _write_file(dest, main_resp.text)
        print("[OK] lib/{}_example.py (reference)".format(name))
        downloaded.append({"path": dest, "type": "example", "filename": "{}_example.py".format(name)})

    return downloaded


# ═══════════════════════════════════════════════════════════════
#  GitHub download
# ═══════════════════════════════════════════════════════════════

def _download_github(driver_url: str, lib_dir: str, name: str) -> list:
    """Download driver .py + README.md from GitHub repo.

    Returns list of dicts: {path, type, filename}.
    """
    downloaded = []

    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)', driver_url)
    if not m:
        print("[WARN] Cannot parse GitHub URL: {}".format(driver_url), file=sys.stderr)
        return downloaded

    owner, repo = m.group(1), m.group(2)
    repo = repo.rstrip('/')

    # ── 1) Download .py files ──
    api_url = "https://api.github.com/repos/{}/{}/contents".format(owner, repo)
    try:
        resp2 = requests.get(api_url, timeout=30, verify=False,
                             headers={"Accept": "application/vnd.github.v3+json"})
        if resp2.status_code == 200:
            for item in resp2.json():
                fname = item.get("name", "")
                if fname.endswith(".py") and "setup" not in fname.lower():
                    dl_url = item.get("download_url", "")
                    if dl_url:
                        dl_resp = _http_get(dl_url)
                        if dl_resp:
                            dest = os.path.join(lib_dir, fname)
                            _write_file(dest, dl_resp.text)
                            print("[OK] lib/{}".format(fname))
                            downloaded.append({"path": dest, "type": "driver", "filename": fname})
    except Exception as e:
        print("[WARN] GitHub API failed: {}".format(e), file=sys.stderr)

    # Fallback: try well-known filenames
    if not downloaded:
        candidates = [
            repo.replace("micropython-", "") + ".py",
            repo.split("-")[-1] + ".py",
        ]
        for fn in candidates:
            raw_url = "https://raw.githubusercontent.com/{}/{}/master/{}".format(owner, repo, fn)
            resp = _http_get(raw_url, timeout=15)
            if resp is not None and fn.endswith(".py"):
                dest = os.path.join(lib_dir, fn)
                _write_file(dest, resp.text)
                print("[OK] lib/{} (fallback)".format(fn))
                downloaded.append({"path": dest, "type": "driver", "filename": fn})

    # ── 2) Try to download README.md ──
    readme_url = "https://raw.githubusercontent.com/{}/{}/master/README.md".format(owner, repo)
    readme_resp = _http_get(readme_url, timeout=15)
    if readme_resp is not None and readme_resp.text.strip():
        dest = os.path.join(lib_dir, "{}_README.md".format(name))
        _write_file(dest, readme_resp.text)
        print("[OK] lib/{}_README.md (reference)".format(name))
        downloaded.append({"path": dest, "type": "readme", "filename": "{}_README.md".format(name)})

    return downloaded


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="download drivers for upy-generate")
    parser.add_argument("--project-dir", required=True, help="Project root directory")
    args = parser.parse_args()

    project_dir = args.project_dir
    manifest = load_manifest(project_dir)
    devices = manifest.get("devices", [])
    lib_dir = os.path.join(project_dir, "firmware", "lib")

    print("")
    print("=" * 60)
    print("  upy-generate Phase 1: Driver download")
    print("=" * 60)

    for d in devices:
        name = safe_var_name(d.get("name", "unknown"))
        driver = d.get("driver", {})
        source = driver.get("source", "")

        print("")
        print("  [{}] source={}".format(name, source))

        if source == "upypi":
            pkg = driver.get("package_name", "")
            ver = driver.get("version", "1.0.0")
            if not pkg:
                print("[WARN] No package_name for {}".format(name))
                continue
            result = _download_upypi(pkg, ver, lib_dir, name)
        elif source == "awesome-micropython":
            url = driver.get("driver_url", "")
            if not url:
                print("[WARN] No driver_url for {}".format(name))
                continue
            result = _download_github(url, lib_dir, name)
        else:
            print("[SKIP] unknown source")
            continue

        if not any(r["type"] == "driver" for r in result):
            print("[WARN] No driver .py downloaded for {}".format(name))

    # ── Record download timestamp (phase stays scaffold until Phase 9) ──
    manifest["generate"] = manifest.get("generate", {})
    manifest["generate"]["driver_downloaded_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path = os.path.join(project_dir, "project-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("")
    print("[DONE] Driver download complete")
    print("")


if __name__ == "__main__":
    main()
