#!/usr/bin/env python3
"""upy-autofix 硬件信号验证脚本。纯执行器，不做诊断决策。

用法:
  python hardware_sanity.py --config sanity_config.json --port COM3
  python hardware_sanity.py --config sanity_config.json --port COM3 --timeout 60

输出 (stdout JSON):
{
  "results": [
    {
      "id": "xxx",
      "category": "i2c_sensor",
      "mode": "self_verify",
      "label": "BMP280",
      "status": "pass" | "fail" | "timeout" | "aborted",
      "output": "REPL 输出",
      "detail": "判定说明"
    }
  ],
  "summary": {
    "total": 3, "pass": 2, "fail": 1,
    "hardware_ok": false,
    "failing": ["xxx"]
  }
}
"""

import argparse
import json
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


# ── 自检型: 运行 mpremote exec 并自动判定 ──

def run_self_verify(test: Dict[str, Any], port: str) -> Dict[str, Any]:
    test_id = test["id"]
    code = test.get("code", "")
    pass_pattern = test.get("pass_pattern", "")
    fail_pattern = test.get("fail_pattern", "")
    value_key = test.get("value_key", "")
    value_range = test.get("value_range", [])
    timeout_ms = test.get("timeout_ms", 5000)
    timeout_sec = max(timeout_ms / 1000 + 3, 8)

    result = {
        "id": test_id,
        "category": test.get("category", "unknown"),
        "mode": "self_verify",
        "label": test.get("label", test_id),
        "status": "fail",
        "output": "",
        "detail": "",
    }

    try:
        proc = subprocess.run(
            ["mpremote", "connect", port, "resume", "exec", code],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        result["output"] = output.strip()

        # 判定
        if "Traceback" in output:
            result["status"] = "fail"
            tb_line = [l for l in output.split("\n") if "Error:" in l]
            result["detail"] = f"REPL 异常: {tb_line[-1] if tb_line else '未知'}"

        elif fail_pattern and fail_pattern in output:
            result["status"] = "fail"
            result["detail"] = f"匹配失败模式: {fail_pattern}"

        elif pass_pattern and pass_pattern in output:
            if value_key and value_range and len(value_range) >= 2:
                # 提取数值并做范围检查
                m = re.search(
                    rf"{re.escape(value_key)}[:=]\s*([-\d.]+)",
                    output
                )
                if m:
                    try:
                        val = float(m.group(1))
                        lo, hi = value_range[0], value_range[1]
                        if lo <= val <= hi:
                            result["status"] = "pass"
                            result["detail"] = f"{value_key}={val}, 在[{lo},{hi}]范围内"
                        else:
                            result["status"] = "fail"
                            result["detail"] = f"{value_key}={val}, 超出范围[{lo},{hi}]"
                    except ValueError:
                        result["status"] = "pass"
                        result["detail"] = f"pass_pattern 匹配但数值解析失败"
                else:
                    result["status"] = "pass"
                    result["detail"] = f"pass_pattern 匹配, 无数值"
            else:
                result["status"] = "pass"
                result["detail"] = f"pass_pattern 匹配"

        elif not output.strip():
            result["status"] = "timeout"
            result["detail"] = "无输出（设备无响应或死循环）"

        else:
            result["status"] = "fail"
            result["detail"] = "输出不匹配任何预期模式"
            if len(output) > 200:
                result["output"] = output[:200] + "...(truncated)"

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["detail"] = f"mpremote 超时 ({timeout_sec}s)"
    except FileNotFoundError:
        result["status"] = "fail"
        result["detail"] = "mpremote 未安装或不在 PATH 中"
    except Exception as e:
        result["status"] = "fail"
        result["detail"] = str(e)

    return result


# ── 反馈型: 运行 mpremote exec + 等待用户输入 ──

def run_user_feedback(test: Dict[str, Any], port: str) -> Dict[str, Any]:
    test_id = test["id"]
    code = test.get("code", "")
    timeout_ms = test.get("timeout_ms", 8000)
    timeout_sec = max(timeout_ms / 1000 + 3, 10)

    result = {
        "id": test_id,
        "category": test.get("category", "unknown"),
        "mode": "user_feedback",
        "label": test.get("label", test_id),
        "status": "fail",
        "output": "",
        "user_response": "",
        "detail": "",
    }

    # 先运行驱动代码
    try:
        proc = subprocess.run(
            ["mpremote", "connect", port, "resume", "exec", code],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        result["output"] = output.strip()

        if "Traceback" in output:
            result["status"] = "fail"
            result["detail"] = "驱动代码执行异常，未询问用户"
            return result

    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["detail"] = "驱动代码执行超时"
        return result
    except Exception as e:
        result["status"] = "fail"
        result["detail"] = str(e)
        return result

    # 询问用户 —— 通过 stdout 输出特殊格式供 LLM 识别
    # 实际交互由 LLM (SKILL.md) 读取此 JSON 后调用 AskUserQuestion
    question = test.get("question", f"{test.get('label', test_id)} 正常工作了？")
    result["_pending_question"] = question
    result["detail"] = "等待用户反馈"

    return result


# ── 批量执行 ──

def run_tests(
    config: Dict[str, Any], port: str
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    tests: List[Dict[str, Any]] = config.get("tests", [])
    results: List[Dict[str, Any]] = []

    pending_feedback: List[Dict[str, Any]] = []

    for test in tests:
        mode = test.get("mode", "self_verify")

        if mode == "user_feedback":
            r = run_user_feedback(test, port)
            if r.get("_pending_question"):
                pending_feedback.append(r)
            else:
                results.append(r)
        else:
            r = run_self_verify(test, port)
            results.append(r)

        # 连续 exec 之间给设备喘息
        time.sleep(0.5)

    # 合并结果
    all_results = results + pending_feedback

    # 汇总
    total = len(all_results)
    passed = sum(1 for r in all_results if r["status"] == "pass")
    failed = sum(1 for r in all_results if r["status"] == "fail")

    failing = [r["id"] for r in all_results if r["status"] != "pass"]

    summary = {
        "total": total,
        "pass": passed,
        "fail": failed,
        "hardware_ok": len(failing) == 0,
        "failing": failing,
        "pending_feedback": len(pending_feedback) > 0,
    }

    return all_results, summary


# ── 主入口 ──

def main() -> None:
    parser = argparse.ArgumentParser(
        description="upy-autofix 硬件信号验证执行器"
    )
    parser.add_argument(
        "--config", required=True,
        help="sanity_config.json 路径"
    )
    parser.add_argument(
        "--port", default="",
        help="COM 端口 (如 COM3)"
    )
    parser.add_argument(
        "--timeout", type=int, default=60,
        help="总超时时间 (秒), 默认 60"
    )
    args = parser.parse_args()

    # 读取配置
    try:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(json.dumps(
            {"error": f"读取配置文件失败: {e}"},
            ensure_ascii=False, indent=2
        ))
        sys.exit(1)

    if not args.port:
        print(json.dumps(
            {"error": "未提供 COM 端口 (--port)"},
            ensure_ascii=False, indent=2
        ))
        sys.exit(1)

    # 执行测试
    results, summary = run_tests(config, args.port)

    output = {
        "results": results,
        "summary": summary,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
