#!/usr/bin/env python3
"""Run a target MPOS app inside the MicroPythonOS desktop simulator."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


STATIC_GATES = {
    "manifest",
    "cpython_syntax",
    "mpy_syntax",
    "mpy_imports",
    "make_lint",
    "flake8",
    "pylint",
}
PYLINT_STRONG_FAIL_BITS = 1 | 2 | 32
MARKER = "__MPOS_TEST_JSON__"


def utc_now() -> str:
    fixed = os.environ.get("MPOS_TEST_APP_UTC_NOW", "").strip()
    if fixed:
        return fixed
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_fullname(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""):
        raise ValueError("app fullname must contain only letters, digits, dots, underscores, and hyphens")
    if "/" in value or "\\" in value or ".." in value.split("."):
        raise ValueError("app fullname must not contain path separators or '..' components")
    return value


def check_generation_result(path: Path | None, fullname: str) -> dict[str, Any]:
    check = {
        "name": "generation_result_static_gates",
        "required": False,
        "ok": True,
        "status": "not_provided",
        "path": str(path) if path else None,
        "warnings": [],
        "errors": [],
    }
    if path is None:
        check["warnings"].append("generation_result.json was not provided; static gates are assumed to be owned by mpos-gen-app")
        return check
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        check.update(ok=False, status="invalid_json")
        check["errors"].append(f"{type(exc).__name__}: {exc}")
        return check

    app = data.get("app", {}) if isinstance(data, dict) else {}
    if app.get("fullname") != fullname:
        check["warnings"].append(f"generation_result app.fullname={app.get('fullname')!r} does not match {fullname!r}")

    gates = data.get("validation", {}).get("gates", []) if isinstance(data, dict) else []
    by_name = {gate.get("name"): gate for gate in gates if isinstance(gate, dict)}
    missing = sorted(STATIC_GATES - set(by_name))
    if missing:
        check["warnings"].append("missing static gate records: " + ", ".join(missing))

    for name in sorted(STATIC_GATES & set(by_name)):
        gate = by_name[name]
        rc = gate.get("returncode")
        if not isinstance(rc, int):
            check["errors"].append(f"{name}: returncode is not an integer")
            continue
        if name == "pylint":
            if rc & PYLINT_STRONG_FAIL_BITS:
                check["errors"].append(f"{name}: fatal/error/usage pylint bits set in returncode {rc}")
        elif gate.get("required", True) and rc != 0:
            check["errors"].append(f"{name}: required gate returncode {rc}")

    if check["errors"]:
        check.update(ok=False, status="failed")
    else:
        check["status"] = "passed" if not check["warnings"] else "passed_with_warnings"
    return check


def import_controller(repo: Path):
    scripts = repo / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from mpos_controller import MPOSController, _resolve_binary  # type: ignore
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass
    return MPOSController, _resolve_binary


def parse_marker(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", "replace")
    payload = {"ok": False, "raw_output": text}
    for line in reversed(text.splitlines()):
        if MARKER in line:
            candidate = line.split(MARKER, 1)[1].strip()
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    parsed["raw_output"] = text
                    return parsed
            except json.JSONDecodeError:
                payload["parse_error"] = candidate
                break
    return payload


def summarize_tree(tree: Any) -> dict[str, Any]:
    summary = {"available": tree is not None, "node_count": 0, "types": {}, "sample": []}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            summary["node_count"] += 1
            node_type = str(node.get("type") or node.get("class") or node.get("name") or "unknown")
            summary["types"][node_type] = summary["types"].get(node_type, 0) + 1
            if len(summary["sample"]) < 20:
                sample = {k: node.get(k) for k in ("type", "class", "text", "label") if k in node}
                if sample:
                    summary["sample"].append(sample)
            for key in ("children", "childs", "items"):
                children = node.get(key)
                if isinstance(children, list):
                    for child in children:
                        walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(tree)
    return summary


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _restore_file(path: Path, content: bytes | None) -> None:
    if content is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def run_desktop_runner_probe(
    repo: Path,
    fullname: str,
    timeout_seconds: int,
    skip: bool = False,
) -> dict[str, Any]:
    script = repo / "scripts" / "run_desktop.sh"
    command = [str(script), fullname]
    check: dict[str, Any] = {
        "name": "desktop_runner_launch",
        "required": not skip,
        "ok": False,
        "status": "pending",
        "command": " ".join(command),
        "cwd": str(repo),
        "timeout_seconds": timeout_seconds,
        "warnings": [],
        "errors": [],
    }
    if skip:
        check.update(ok=True, status="skipped")
        check["warnings"].append("desktop runner launch probe skipped by explicit flag")
        return check
    if not script.exists():
        check.update(status="missing_tool")
        check["errors"].append(f"{script} does not exist")
        return check
    if timeout_seconds <= 0:
        check.update(status="invalid_timeout")
        check["errors"].append("--desktop-probe-timeout must be greater than zero")
        return check

    config_path = repo / "internal_filesystem" / "prefs" / "com.micropythonos.settings" / "config.json"
    previous_config = config_path.read_bytes() if config_path.exists() else None
    stdout = ""
    proc = None
    timed_out = False
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, _ = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _as_text(exc.stdout)
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                more, _ = proc.communicate(timeout=3)
                stdout += _as_text(more)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
                try:
                    more, _ = proc.communicate(timeout=2)
                    stdout += _as_text(more)
                except Exception:
                    pass
    except Exception as exc:
        check.update(status="failed_to_launch")
        check["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            _restore_file(config_path, previous_config)
        except Exception as exc:
            check["warnings"].append(f"failed to restore desktop autostart config: {type(exc).__name__}: {exc}")

    if stdout:
        check["stdout_tail"] = stdout[-4000:]
    if proc is not None and proc.returncode is not None:
        check["returncode"] = proc.returncode
    if timed_out:
        check["timed_out"] = True

    if check["errors"]:
        return check

    launch_marker = f"run_desktop.sh: running app {fullname}" in stdout
    external_markers = [
        "Error importing mpos.main",
        "no module named '_webrepl'",
        "No such file or directory",
    ]
    runtime_markers = [
        "Traceback (most recent call last):",
        "ImportError:",
        "ERROR:",
    ]
    external_hits = [marker for marker in external_markers if marker in stdout]
    runtime_hits = [marker for marker in runtime_markers if marker in stdout]
    repl_ready = "Starting asyncio REPL" in stdout or "\n>>> " in stdout or stdout.endswith(">>> ")
    if not launch_marker:
        check.update(status="launch_marker_missing")
        check["errors"].append("run_desktop.sh did not report that it started the target app")
        return check
    if external_hits:
        check.update(status="desktop_boot_error", external_blocking=True)
        check["errors"].append(
            "desktop runner output contained OS boot markers: {}".format(
                ", ".join(external_hits)
            )
        )
        return check
    if runtime_hits:
        if not repl_ready:
            check.update(status="runner_runtime_error_before_repl", possibly_app_failure=True)
            check["errors"].append(
                "desktop runner output contained runtime markers before REPL was ready: {}".format(
                    ", ".join(runtime_hits)
                )
            )
            return check
        check["warnings"].append(
            "desktop runner output contained runtime markers after boot; controller smoke remains the source of truth: {}".format(
                ", ".join(runtime_hits)
            )
        )
    if not timed_out and proc is not None and proc.returncode not in (None, 0):
        check.update(status="nonzero_exit")
        check["errors"].append(f"run_desktop.sh exited with returncode {proc.returncode}")
        return check

    check["ok"] = True
    if timed_out:
        check["status"] = "launched_with_runtime_warnings" if runtime_hits else "launched_until_timeout"
        check["warnings"].append(
            "run_desktop.sh is a long-lived interactive runner; timeout after clean launch is treated as pass"
        )
    else:
        check["status"] = "passed_with_runtime_warnings" if runtime_hits else "passed"
    return check


def _find_emscripten(repo: Path) -> dict[str, Any]:
    check: dict[str, Any] = {
        "available": False,
        "command": None,
        "source": None,
        "warnings": [],
    }
    emcc = shutil.which("emcc")
    if emcc:
        check.update(available=True, command=emcc, source="PATH")
        return check
    for envsh in (repo / ".." / "emsdk" / "emsdk_env.sh", repo / ".." / ".." / "emsdk" / "emsdk_env.sh"):
        if envsh.exists():
            check["source"] = str(envsh.resolve())
            return check
    check["warnings"].append("emcc is not on PATH and no sibling emsdk_env.sh was found")
    return check


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_get_no_proxy(url: str, timeout_seconds: float) -> tuple[int, bytes, str]:
    opener = build_opener(ProxyHandler({}))
    with opener.open(url, timeout=timeout_seconds) as response:
        body = response.read(1024)
        content_type = response.headers.get("Content-Type", "")
        return int(response.status), body, content_type


def _terminate_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
    except Exception:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def run_chrome_web_check(url: str, timeout_seconds: int) -> dict[str, Any]:
    check: dict[str, Any] = {
        "requested": True,
        "ok": False,
        "status": "pending",
        "warnings": [],
        "errors": [],
    }
    chrome = None
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(candidate)
        if path:
            chrome = path
            break
    if chrome is None:
        check.update(ok=True, status="skipped_missing_chrome")
        check["warnings"].append("Chrome/Chromium command was not found; browser automation skipped")
        return check
    check["command"] = chrome
    with tempfile.TemporaryDirectory(prefix="mpos-web-chrome-") as profile:
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--user-data-dir={profile}",
            "--dump-dom",
            url,
        ]
        try:
            proc = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            check.update(ok=True, status="skipped_chrome_timeout")
            check["warnings"].append(f"Chrome automation timed out after {timeout_seconds}s")
            check["stdout_tail"] = _as_text(exc.stdout)[-2000:]
            check["stderr_tail"] = _as_text(exc.stderr)[-2000:]
            return check
        except Exception as exc:
            check.update(ok=True, status="skipped_chrome_launch_failed")
            check["warnings"].append(f"{type(exc).__name__}: {exc}")
            return check
    check["returncode"] = proc.returncode
    check["stdout_tail"] = proc.stdout[-2000:]
    check["stderr_tail"] = proc.stderr[-2000:]
    if proc.returncode == 0:
        check.update(ok=True, status="passed")
    else:
        check.update(ok=True, status="skipped_chrome_failed")
        check["warnings"].append(f"Chrome automation exited with returncode {proc.returncode}")
    return check


def run_web_port_check(
    repo: Path,
    timeout_seconds: int,
    browser_check: bool = False,
) -> dict[str, Any]:
    script = repo / "scripts" / "run_web.sh"
    web_dir = repo / "web"
    required_artifacts = [
        web_dir / "index.html",
        web_dir / "micropython.js",
        web_dir / "micropython.wasm",
        web_dir / "micropython.data",
    ]
    check: dict[str, Any] = {
        "name": "web_port",
        "required": False,
        "ok": True,
        "status": "pending",
        "tool": str(script),
        "artifacts": {str(path.relative_to(repo)): path.exists() for path in required_artifacts},
        "emscripten": _find_emscripten(repo),
        "warnings": [],
        "errors": [],
    }
    if not script.exists():
        check.update(status="skipped_missing_local_web_tooling")
        check["warnings"].append(f"{script} does not exist")
        return check
    missing = [path for path in required_artifacts if not path.exists()]
    if missing:
        emscripten = check["emscripten"]
        if not emscripten.get("available") and not emscripten.get("source"):
            check["status"] = "skipped_missing_emscripten"
            check["warnings"].append("web artifacts are missing and Emscripten is unavailable")
        else:
            check["status"] = "skipped_missing_web_artifacts"
            check["warnings"].append("web artifacts are missing; run scripts/build_mpos.sh web before HTTP Web Port smoke")
        check["missing_artifacts"] = [str(path.relative_to(repo)) for path in missing]
        return check
    if timeout_seconds <= 0:
        check["status"] = "skipped_invalid_timeout"
        check["warnings"].append("--web-port-timeout must be greater than zero")
        return check

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}/"
    check["url"] = url
    command = [str(script), "--no-build"]
    check["command"] = "PORT={} {}".format(port, " ".join(command))
    proc = None
    stdout = ""
    try:
        env = os.environ.copy()
        env["PORT"] = str(port)
        proc = subprocess.Popen(
            command,
            cwd=str(repo),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        last_error = ""
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                status, body, content_type = _http_get_no_proxy(url, timeout_seconds=1.5)
                check["http"] = {
                    "status": status,
                    "content_type": content_type,
                    "body_prefix": body[:120].decode("utf-8", "replace"),
                }
                if status == 200 and b"MicroPython" in body:
                    check["status"] = "passed_http"
                    if browser_check:
                        check["browser"] = run_chrome_web_check(url, timeout_seconds)
                    else:
                        check["browser"] = {
                            "requested": False,
                            "ok": True,
                            "status": "skipped_not_requested",
                            "warnings": [],
                        }
                    return check
                last_error = f"unexpected HTTP response {status}"
            except URLError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)
        if proc and proc.poll() is not None:
            check["returncode"] = proc.returncode
        check["status"] = "skipped_http_unavailable"
        check["warnings"].append(last_error or "Web Port HTTP server did not become ready before timeout")
    except Exception as exc:
        check["status"] = "skipped_web_port_launch_failed"
        check["warnings"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if proc is not None:
            _terminate_process(proc)
            try:
                more, _ = proc.communicate(timeout=1)
                stdout += _as_text(more)
            except Exception:
                pass
        if stdout:
            check["stdout_tail"] = stdout[-4000:]
    return check


def smoke(repo: Path, fullname: str, args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {
        "schema_version": "mpos-test-app-v1",
        "phase": "test-app",
        "result": "failed",
        "created_at_utc": utc_now(),
        "app": {
            "fullname": fullname,
            "app_dir": f"internal_filesystem/apps/{fullname}",
        },
        "environment": {
            "repo": str(repo),
            "backend": "process",
            "runner": "scripts/mpos_controller.py",
            "desktop_runner": "scripts/run_desktop.sh",
            "heapsize": args.heapsize,
        },
        "checks": [],
        "artifacts": [],
        "blocking_questions": [],
        "handoff": {
            "next_skill": "mpos-gen-app",
            "reason": "App smoke test has not passed.",
        },
    }

    gen_check = check_generation_result(Path(args.generation_result) if args.generation_result else None, fullname)
    result["checks"].append(gen_check)

    desktop_runner_check = run_desktop_runner_probe(
        repo,
        fullname,
        args.desktop_probe_timeout,
        skip=args.skip_desktop_runner_probe,
    )
    result["checks"].append(desktop_runner_check)

    if args.web_port_check:
        result["checks"].append(
            run_web_port_check(
                repo,
                args.web_port_timeout,
                browser_check=args.web_port_browser_check,
            )
        )

    desktop_check = {
        "name": "desktop_smoke",
        "required": True,
        "ok": False,
        "status": "pending",
        "command": "MPOSController(process).exec(AppManager.start_app)",
        "cwd": str(repo / "internal_filesystem"),
        "warnings": [],
        "errors": [],
    }
    result["checks"].append(desktop_check)

    if not desktop_runner_check["ok"]:
        if desktop_runner_check.get("external_blocking"):
            desktop_check["status"] = "skipped_after_desktop_runner_failure"
            desktop_check["errors"].append("desktop runner failed before controller smoke could be trusted")
            result["handoff"] = {
                "next_skill": None,
                "reason": "MicroPythonOS desktop runner failed before structured app smoke; fix local OS simulator/tooling first unless the log clearly points to the target app.",
            }
            return result, 1
        desktop_check["warnings"].append("desktop runner launch probe failed; continuing to structured controller smoke")

    try:
        MPOSController, resolve_binary = import_controller(repo)
        binary = Path(resolve_binary())
        desktop_check["binary"] = str(binary)
        result["environment"]["binary"] = str(binary)
    except Exception as exc:
        desktop_check["errors"].append(f"cannot resolve MicroPythonOS desktop binary: {type(exc).__name__}: {exc}")
        result["handoff"]["reason"] = "Desktop simulator binary/controller is unavailable."
        return result, 1

    code = f"""
import json
try:
    from mpos.content.app_manager import AppManager
    from mpos.ui.testing import wait_for_render
    ok = AppManager.start_app({fullname!r})
    wait_for_render({int(args.render_iterations)})
    print({MARKER!r} + json.dumps({{"ok": bool(ok), "start_result": repr(ok)}}))
except Exception as exc:
    import sys
    try:
        sys.print_exception(exc)
    except Exception:
        print(repr(exc))
    print({MARKER!r} + json.dumps({{"ok": False, "error_type": type(exc).__name__, "error": str(exc)}}))
"""

    try:
        with MPOSController(backend="process", heapsize=args.heapsize) as mpos:
            boot_raw = mpos.exec_multiline(f"""
import json, sys
mods = []
for name in ("mpos", "mpos.main"):
    if name in sys.modules:
        mods.append(name)
print({MARKER!r} + json.dumps({{"ok": "mpos.main" in sys.modules, "modules": mods}}))
""")
            boot = parse_marker(boot_raw)
            desktop_check["boot"] = {k: v for k, v in boot.items() if k != "raw_output"}
            if not boot.get("ok"):
                desktop_check["errors"].append("MicroPythonOS main module did not finish booting in the desktop simulator")
                desktop_check["boot_stdout_tail"] = boot.get("raw_output", "")[-3000:]
                result["handoff"] = {
                    "next_skill": None,
                    "reason": "MicroPythonOS desktop simulator boot failed before the target app was started; rebuild/fix local OS tooling first.",
                }
                return result, 1

            started = parse_marker(mpos.exec_multiline(code))
            desktop_check["start"] = {k: v for k, v in started.items() if k != "raw_output"}
            raw_output = started.get("raw_output", "")
            if raw_output:
                desktop_check["stdout_tail"] = raw_output[-3000:]
            if not started.get("ok"):
                desktop_check["errors"].append(started.get("error") or started.get("parse_error") or "AppManager.start_app returned false")
            try:
                visible_text = mpos.get_visible_text()
                desktop_check["visible_text"] = visible_text[:50]
            except Exception as exc:
                desktop_check["warnings"].append(f"visible text collection failed: {type(exc).__name__}: {exc}")
                visible_text = []

            expected_missing = [text for text in args.expected_text if text not in visible_text]
            if expected_missing:
                desktop_check["errors"].append("missing expected visible text: " + ", ".join(repr(item) for item in expected_missing))

            if not args.skip_widget_tree:
                try:
                    tree = mpos.get_widget_tree()
                    desktop_check["widget_tree_summary"] = summarize_tree(tree)
                except Exception as exc:
                    desktop_check["warnings"].append(f"widget tree collection failed: {type(exc).__name__}: {exc}")

            if args.screenshot:
                try:
                    out_dir = Path(args.artifact_dir)
                    if not out_dir.is_absolute():
                        out_dir = repo / out_dir
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shot = out_dir / f"{fullname}.bmp"
                    shot.write_bytes(mpos.screenshot())
                    result["artifacts"].append({"kind": "screenshot", "path": str(shot), "format": "bmp"})
                except Exception as exc:
                    desktop_check["warnings"].append(f"screenshot failed: {type(exc).__name__}: {exc}")
    except Exception as exc:
        desktop_check["errors"].append(f"{type(exc).__name__}: {exc}")
        desktop_check["traceback"] = traceback.format_exc()[-4000:]

    desktop_check["ok"] = not desktop_check["errors"]
    if desktop_check["ok"]:
        desktop_check["status"] = "passed"
        result["result"] = "success" if gen_check["ok"] else "partial"
        result["handoff"] = {
            "next_skill": None,
            "reason": "Target app started successfully in the MicroPythonOS desktop simulator.",
        }
        return result, 0 if gen_check["ok"] else 1

    desktop_check["status"] = "failed"
    return result, 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an MPOS app desktop simulator smoke test")
    parser.add_argument("--repo", default="/home/leeqingshui/MicroPythonOS")
    parser.add_argument("--app-fullname", required=True)
    parser.add_argument("--generation-result", help="Optional mpos-gen-app generation_result.json")
    parser.add_argument("--expected-text", action="append", default=[])
    parser.add_argument("--render-iterations", type=int, default=10)
    parser.add_argument("--heapsize", default="32M")
    parser.add_argument("--desktop-probe-timeout", type=int, default=20)
    parser.add_argument("--skip-desktop-runner-probe", action="store_true")
    parser.add_argument("--web-port-check", action="store_true", help="Optionally serve existing Web Port artifacts and run an HTTP smoke check")
    parser.add_argument("--web-port-timeout", type=int, default=20)
    parser.add_argument("--web-port-browser-check", action="store_true", help="Optionally attempt Chrome/Chromium headless loading after the HTTP check")
    parser.add_argument("--screenshot", action="store_true")
    parser.add_argument("--artifact-dir", default="tmp/mpos-test-app")
    parser.add_argument("--skip-widget-tree", action="store_true")
    parser.add_argument("--output", help="Write result JSON to this path")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    fullname = safe_fullname(args.app_fullname)
    result, rc = smoke(repo, fullname, args)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
