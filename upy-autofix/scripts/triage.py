#!/usr/bin/env python3
"""upy-autofix 数据采集脚本。纯结构化输出，不做修复决策。

用法:
  python triage.py --log-dir ./deploy_logs --port COM3 --attempt 1
  python triage.py --snapshot                             # git 保存快照
  python triage.py --rollback                             # git 回滚

输出 (stdout JSON):
{
  "status": "ok" | "fail",
  "error_type": "ImportError" | "OSError_19" | ... | "unknown",
  "p_level": "P0" | "P1" | "P2" | "P3" | "unknown",
  "traceback": "完整 traceback 或空字符串",
  "error_file": "main.py" 或 null,
  "error_line": 42 或 null,
  "i2c_scan": ["0x44"] 或 [],
  "i2c_ok": true | false | null,
  "i2c_error": null 或 "错误描述",
  "log_files": ["run_0.log"],
  "log_snippet": "最后 30 行(log合并后)",
  "deploy_success": true | false,
  "attempt": 1,
  "warnings": ["降级警告信息"]
}
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple


# ---- 错误模式 ----
ERROR_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex, error_type, p_level)
    (r"Traceback \(most recent call last\):\s*\n(?:.+\n)+?(\w+Error):\s*(.+)", "PythonTraceback", "P0"),
    (r"ImportError:\s*(.+)", "ImportError", "P0"),
    (r"AttributeError:\s*(.+)", "AttributeError", "P0"),
    (r"NameError:\s*(.+)", "NameError", "P0"),
    (r"SyntaxError:\s*(.+)", "SyntaxError", "P0"),
    (r"OSError:\s*\[Errno\s*19\].*", "OSError_19", "P1"),
    (r"OSError:\s*\[Errno\s*110\].*", "OSError_110", "P1"),
    (r"OSError:\s*\[Errno\s*12\].*", "OSError_12", "P2"),
    (r"MemoryError:\s*(.+)", "MemoryError", "P2"),
    (r"rst cause:\s*4", "WDT_Reset", "P1"),
    (r"Guru Meditation Error", "Guru_Meditation", "P1"),
    (r"\[FAIL\]\s*(.+)", "FailMarker", "P2"),
]


def _default_json(attempt: int = 1) -> Dict[str, Any]:
    return {
        "status": "ok",
        "error_type": "unknown",
        "p_level": "unknown",
        "traceback": "",
        "error_file": None,
        "error_line": None,
        "i2c_scan": [],
        "i2c_ok": None,
        "i2c_error": None,
        "log_files": [],
        "log_snippet": "",
        "deploy_success": True,
        "attempt": attempt,
        "warnings": [],
    }


# ---- 日志读取 ----
def read_logs(log_dir: str) -> Tuple[List[str], str, List[str]]:
    """读取日志目录，返回 (文件列表, 合并内容, 警告列表)。"""
    warnings: List[str] = []
    log_files: List[str] = []
    merged: List[str] = []

    try:
        if not os.path.isdir(log_dir):
            return [], "", [f"log-dir 不存在: {log_dir}"]

        for fname in sorted(os.listdir(log_dir)):
            if fname.endswith(".log"):
                fpath = os.path.join(log_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    merged.append(f"=== {fname} ===\n{content}")
                    log_files.append(fname)
                except Exception as e:
                    warnings.append(f"读取 {fname} 失败: {e}")
    except Exception as e:
        warnings.append(f"遍历日志目录失败: {e}")

    full = "\n".join(merged)
    snippet = "\n".join(full.split("\n")[-30:]) if full else ""
    return log_files, snippet, warnings


# ---- 错误解析 ----
def parse_errors(log_text: str) -> Dict[str, Any]:
    """从日志文本解析错误，返回 error 相关字段。"""
    result: Dict[str, Any] = {
        "error_type": "unknown",
        "p_level": "unknown",
        "traceback": "",
        "error_file": None,
        "error_line": None,
        "deploy_success": True,
    }

    if not log_text.strip():
        return result

    for pattern, err_type, p_level in ERROR_PATTERNS:
        try:
            m = re.search(pattern, log_text, re.IGNORECASE | re.DOTALL)
            if m:
                result["error_type"] = err_type
                result["p_level"] = p_level
                result["deploy_success"] = False

                # 提取完整 traceback
                tb_match = re.search(
                    r"(Traceback \(most recent call last\):[\s\S]*?)(?=\n\w|$)",
                    log_text
                )
                if tb_match:
                    result["traceback"] = tb_match.group(1).strip()

                # 提取文件和行号
                file_match = re.search(
                    r'File\s+"([^"]+)",\s*line\s+(\d+)',
                    log_text
                )
                if file_match:
                    result["error_file"] = file_match.group(1)
                    try:
                        result["error_line"] = int(file_match.group(2))
                    except (ValueError, TypeError):
                        pass

                break
        except Exception:
            continue

    # 超时无输出 → P3
    if result["error_type"] == "unknown" and not log_text.strip():
        result["error_type"] = "NoOutput"
        result["p_level"] = "P3"
        result["deploy_success"] = False

    return result


# ---- I2C 硬件检测 ----
def check_i2c(port: str, sda: int = 21, scl: int = 22) -> Dict[str, Any]:
    """I2C 硬件检测。返回 i2c 相关字段。"""
    result: Dict[str, Any] = {
        "i2c_scan": [],
        "i2c_ok": None,
        "i2c_error": None,
    }

    if not port:
        result["i2c_error"] = "未提供 COM 端口"
        return result

    # 硬件 I2C
    code = (
        "from machine import I2C, Pin\n"
        "try:\n"
        f"    i2c = I2C(0, scl=Pin({scl}), sda=Pin({sda}))\n"
        "    print('I2C_SCAN_START')\n"
        "    print([hex(a) for a in i2c.scan()])\n"
        "    print('I2C_SCAN_END')\n"
        "except Exception as e:\n"
        "    print('I2C_ERR:' + str(e))\n"
    )

    try:
        r = subprocess.run(
            ["mpremote", "connect", port, "resume", "exec", code],
            capture_output=True, text=True, timeout=15,
        )
        output = r.stdout + r.stderr

        if "I2C_ERR:" in output:
            err_part = output.split("I2C_ERR:")[-1].strip().split("\n")[0]
            result["i2c_error"] = err_part

            # 尝试 software I2C
            soft_code = (
                "from machine import SoftI2C, Pin\n"
                "try:\n"
                f"    si2c = SoftI2C(scl=Pin({scl}), sda=Pin({sda}))\n"
                "    print('SOFT_I2C_SCAN_START')\n"
                "    print([hex(a) for a in si2c.scan()])\n"
                "    print('SOFT_I2C_SCAN_END')\n"
                "except Exception as e:\n"
                "    print('SOFT_I2C_ERR:' + str(e))\n"
            )
            try:
                r2 = subprocess.run(
                    ["mpremote", "connect", port, "resume", "exec", soft_code],
                    capture_output=True, text=True, timeout=15,
                )
                output2 = r2.stdout + r2.stderr
                if "SOFT_I2C_ERR:" in output2:
                    err2 = output2.split("SOFT_I2C_ERR:")[-1].strip().split("\n")[0]
                    result["i2c_error"] = f"hw: {err_part}; soft: {err2}"
                else:
                    result = _parse_i2c_scan_output(output2, result)
            except Exception as e2:
                result["i2c_error"] = f"hw: {err_part}; soft attempt failed: {e2}"
        else:
            result = _parse_i2c_scan_output(output, result)

    except subprocess.TimeoutExpired:
        result["i2c_error"] = "mpremote I2C 扫描超时"
    except FileNotFoundError:
        result["i2c_error"] = "mpremote 未安装或不在 PATH 中"
    except Exception as e:
        result["i2c_error"] = str(e)

    result["i2c_ok"] = len(result["i2c_scan"]) > 0
    return result


def _parse_i2c_scan_output(output: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """从 I2C 扫描输出提取地址列表。"""
    try:
        parts = output.split("I2C_SCAN_START")
        if len(parts) < 2:
            parts = output.split("SOFT_I2C_SCAN_START")
        if len(parts) >= 2:
            addr_section = parts[-1].split("I2C_SCAN_END")[0].split("SOFT_I2C_SCAN_END")[0]
            addrs = re.findall(r"0x[0-9a-fA-F]+", addr_section)
            result["i2c_scan"] = addrs
    except Exception:
        pass
    return result


# ---- Git 操作 ----
def git_snapshot() -> Dict[str, Any]:
    """保存 git 快照。"""
    try:
        r1 = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, text=True, timeout=30,
            cwd=os.getcwd(),
        )
        r2 = subprocess.run(
            ["git", "commit", "-m", "autofix: snapshot before fix attempt"],
            capture_output=True, text=True, timeout=30,
            cwd=os.getcwd(),
        )
        commit_hash = ""
        m = re.search(r"\[[\w\-\.]+\s+([a-f0-9]+)\]", r2.stdout)
        if m:
            commit_hash = m.group(1)
        return {"snapshot_ok": r2.returncode == 0, "commit_hash": commit_hash}
    except Exception as e:
        return {"snapshot_ok": False, "error": str(e)}


def git_rollback() -> Dict[str, Any]:
    """回滚到最近一次 autofix snapshot 之前。"""
    try:
        # 找到最近的 autofix snapshot commit
        r = subprocess.run(
            ["git", "log", "--oneline", "-n", "10"],
            capture_output=True, text=True, timeout=10,
        )
        autofix_commits = [
            line for line in r.stdout.split("\n")
            if "autofix: snapshot" in line
        ]
        if not autofix_commits:
            return {"rollback_ok": False, "error": "未找到 autofix snapshot commit"}

        target_hash = autofix_commits[0].split()[0]
        # 回滚到这个 commit 之前的状态（保留工作区修改以便查看）
        r2 = subprocess.run(
            ["git", "checkout", f"{target_hash}^"],
            capture_output=True, text=True, timeout=30,
        )
        return {"rollback_ok": r2.returncode == 0, "reverted_to": target_hash}
    except Exception as e:
        return {"rollback_ok": False, "error": str(e)}


# ---- 主入口 ----
def main() -> None:
    parser = argparse.ArgumentParser(description="upy-autofix 数据采集")
    parser.add_argument("--log-dir", default="./deploy_logs", help="设备日志目录")
    parser.add_argument("--port", default="", help="COM 端口")
    parser.add_argument("--attempt", type=int, default=1, help="当前尝试次数")
    parser.add_argument("--snapshot", action="store_true", help="仅保存 git 快照")
    parser.add_argument("--rollback", action="store_true", help="仅执行 git 回滚")
    parser.add_argument("--sda", type=int, default=21, help="I2C SDA 引脚")
    parser.add_argument("--scl", type=int, default=22, help="I2C SCL 引脚")
    args = parser.parse_args()

    # 纯 git 操作模式
    if args.snapshot:
        result = git_snapshot()
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        return

    if args.rollback:
        result = git_rollback()
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        return

    # 正常数据采集模式
    data = _default_json(args.attempt)

    # 1. 读取日志
    try:
        log_files, log_snippet, warnings = read_logs(args.log_dir)
        data["log_files"] = log_files
        data["log_snippet"] = log_snippet
        data["warnings"].extend(warnings)
    except Exception as e:
        data["warnings"].append(f"日志读取异常: {e}")

    # 2. 解析错误
    try:
        err_info = parse_errors(data["log_snippet"])
        data.update(err_info)
    except Exception as e:
        data["warnings"].append(f"错误解析异常: {e}")

    # 3. I2C 硬件检测（仅当有 I2C 设备且提供端口时）
    if args.port:
        try:
            i2c_info = check_i2c(args.port, args.sda, args.scl)
            data.update(i2c_info)
        except Exception as e:
            data["i2c_error"] = str(e)
            data["warnings"].append(f"I2C 检测异常: {e}")

    # 4. 最终状态
    if not data["deploy_success"]:
        data["status"] = "fail"

    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
