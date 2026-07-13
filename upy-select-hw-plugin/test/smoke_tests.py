#!/usr/bin/env python3
"""Smoke tests for upy-select-hw-plugin."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
SKILL_DIR = TEST_DIR.parent
REPO_ROOT = SKILL_DIR.parent
SAMPLE_DIR = SKILL_DIR / "sample"
SELECT_HW_MANIFEST = SKILL_DIR / "scripts" / "select_hw_manifest.py"
BOARD_ROOT = REPO_ROOT / "upy-analyze-plugin" / "boards"
PLUGIN_VALIDATOR = Path("C:/Users/Administrator/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py")
EXPECTED_ARTIFACTS_BARE = [
    "select_hw_draft.json",
    "select_hw_validated.json",
    "phase_complete.select_hw.json",
    "pin_assignment_log.md",
    "select_hw_phase_log.md",
]
SESSION_ID = "022ad742-3269-42e9-ac20-c14f477ecdf2"
EXPECTED_ARTIFACTS_CWD = [f"sessions/{SESSION_ID}/{name}" for name in EXPECTED_ARTIFACTS_BARE]


def run(cmd: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        cmd,
        cwd=str(SKILL_DIR),
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def check_sample_json() -> None:
    paths = sorted(SAMPLE_DIR.glob("*.json"))
    if not paths:
        raise AssertionError("no sample JSON files found")
    for path in paths:
        load_json(path)


def check_skill_path_contract() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    required = [
        "resource_root",
        "artifact_root",
        "session_root",
        "不得因为 `artifact_root` 下缺少 `upy-select-hw-plugin` 或 `upy-analyze-plugin`",
        "不得通过复制 `upy-select-hw-plugin/scripts` 到 artifact workspace",
        "必须复制完整 `boards` 目录",
        "不能只加载 selected board",
        "板卡确认边界",
        "跨 MCU、跨芯片族、跨固件目标",
        "不得静默改写上游需求并输出 `success`",
        "approval_request: pin_plan_review",
        "用户确认前不得输出 `phase_complete(result=success)`",
        "pin_decisions 与 deviation",
        "如果 `reason_code=onboard_occupied`",
        "当 `pinout.gpio` 为 `GND`、`3V3`、`5V` 时",
        "不要把 `VDD`、`3V3`、`GND` 伪装成普通 MCU GPIO",
        "普通供电脚/地脚",
        "配置、模式、使能、地址、增益、启动等控制脚",
        "V0 不把 `requires_user_review` 当作复杂策略引擎",
        "脚本只校验字段类型、枚举、pinout 对应关系、硬禁用脚、冲突和电源/地类型",
        "不得使用样例占位时间或日期零点",
        "workflow_time.py",
        "runtime_context",
        "artifact_root_mode",
        "artifact_root_mode=cwd",
        "artifact_root_mode=session_root",
        "已用 GPIO",
        "未用 GPIO",
        "条件/保留 GPIO",
        "禁止 GPIO",
        "user_pin_constraints",
        "approval_response.payload.user_pin_constraints",
        "`pinout[].source` 必须为 `user_wiring`",
        "非法引脚不得静默改写",
    ]
    missing = [item for item in required if item not in text]
    if missing:
        raise AssertionError(f"SKILL.md path/root contract missing required text: {missing}")


def check_manifest_validation() -> None:
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--input",
            str(SAMPLE_DIR / "select_hw_draft.json"),
            "--board-root",
            str(BOARD_ROOT),
        ]
    )
    if proc.returncode != 0:
        raise AssertionError(f"select_hw_manifest.py rejected draft:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    if result.get("status") != "ok":
        raise AssertionError(f"draft validation did not return ok: {result}")
    manifest = result.get("manifest")
    if manifest.get("phase") != "select-hw":
        raise AssertionError("normalized manifest phase is not select-hw")
    if manifest.get("final_status") != "hardware_selected":
        raise AssertionError("normalized manifest final_status is not hardware_selected")
    if not manifest.get("pin_decisions"):
        raise AssertionError("normalized manifest should preserve pin_decisions")
    if manifest.get("pin_review", {}).get("approval_id") != "pin_plan_review":
        raise AssertionError("normalized manifest should preserve pin_review approval_id")


def check_cold_driver_status_normalization() -> None:
    def run_with_driver(driver: dict, *, index: int = 2) -> dict:
        draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
        draft["upstream_manifest"]["devices"][index]["driver"] = driver
        proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--stdin",
                "--board-root",
                str(BOARD_ROOT),
            ],
            input_text=json.dumps(draft, ensure_ascii=False),
        )
        if proc.returncode != 0:
            raise AssertionError(f"cold-driver draft should validate:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        return json.loads(proc.stdout)

    missing = run_with_driver({"source": "cold-driver"})
    driver = missing["manifest"]["devices"][2]["driver"]
    if driver.get("source") != "cold-driver" or driver.get("status") != "cold_driver_required":
        raise AssertionError(f"cold-driver source must normalize to cold_driver_required: {missing}")

    ready = run_with_driver(
        {
            "source": "cold-driver",
            "status": "ready",
            "path": "firmware/drivers/aht20_driver/aht20.py",
            "hardware_marker": "SELF_TEST_PASS:AHT20:TEMP_HUMIDITY_READ_OK",
        }
    )
    if ready["manifest"]["devices"][2]["driver"].get("status") != "ready":
        raise AssertionError(f"hardware-proven ready status should be preserved: {ready}")

    fake_ready = run_with_driver({"source": "cold-driver", "status": "ready"})
    if fake_ready["manifest"]["devices"][2]["driver"].get("status") != "cold_driver_required":
        raise AssertionError(f"ready without hardware proof must be downgraded: {fake_ready}")

    pending = run_with_driver({"source": "cold-driver", "status": "pending_validation"})
    if pending["manifest"]["devices"][2]["driver"].get("status") != "pending_validation":
        raise AssertionError(f"pending_validation should be preserved: {pending}")

    mismatched = run_with_driver({"source": "upypi", "status": "cold_driver_required", "package_name": "demo"})
    if mismatched["manifest"]["devices"][2]["driver"].get("source") != "upypi":
        raise AssertionError(f"source/status mismatch should not rewrite source: {mismatched}")
    if not any("keeping source unchanged" in item for item in mismatched.get("warnings", [])):
        raise AssertionError(f"source/status mismatch should warn: {mismatched}")


def check_formatted_output_validation() -> None:
    with tempfile.TemporaryDirectory(prefix="select-hw-") as temp_dir:
        output_path = Path(temp_dir) / "select_hw_validated.json"
        proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--input",
                str(SAMPLE_DIR / "select_hw_draft.json"),
                "--write-path",
                str(output_path),
                "--board-root",
                str(BOARD_ROOT),
            ]
        )
        if proc.returncode != 0:
            raise AssertionError(f"select_hw_manifest.py failed --write-path:\nstdout={proc.stdout}\nstderr={proc.stderr}")
        if not output_path.is_file():
            raise AssertionError("--write-path did not create select_hw_validated.json")
        with open(output_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("phase") != "select-hw":
            raise AssertionError("formatted output phase is not select-hw")
        if not manifest.get("pin_decisions"):
            raise AssertionError("formatted output dropped pin_decisions")
        if manifest.get("pin_review", {}).get("confirmed") is not True:
            raise AssertionError("formatted output dropped confirmed pin_review")
        validate_proc = run(
            [
                sys.executable,
                str(SELECT_HW_MANIFEST),
                "--validate-manifest-content",
                "--input",
                str(output_path),
                "--board-root",
                str(BOARD_ROOT),
            ]
        )
        if validate_proc.returncode != 0:
            raise AssertionError(
                "select_hw_manifest.py rejected formatted output:\n"
                f"stdout={validate_proc.stdout}\nstderr={validate_proc.stderr}"
            )


def check_board_unavailable_sample() -> None:
    msg = load_json(SAMPLE_DIR / "approval_request.board_unavailable.json")
    payload = msg.get("payload", {})
    if msg.get("type") != "approval_request":
        raise AssertionError("board_unavailable sample is not an approval_request")
    if payload.get("approval_id") != "board_unavailable":
        raise AssertionError("board_unavailable sample has wrong approval_id")
    action_values = {item.get("value") for item in payload.get("actions", [])}
    expected = {"use_recommended_similar", "select_known_board", "manual_wiring_description", "save_partial"}
    if action_values != expected:
        raise AssertionError(f"board_unavailable actions mismatch: {action_values}")
    manual_fields = {item.get("name") for item in payload.get("manual_wiring_schema", {}).get("fields", [])}
    required_fields = {"mcu_pin", "device", "device_pin", "signal"}
    if not required_fields.issubset(manual_fields):
        raise AssertionError(f"manual wiring schema missing fields: {required_fields - manual_fields}")


def check_pin_plan_revise_response_sample() -> None:
    msg = load_json(SAMPLE_DIR / "approval_response.pin_plan_review.revise.json")
    payload = msg.get("payload", {})
    if msg.get("type") != "approval_response":
        raise AssertionError("pin_plan_review revise sample is not an approval_response")
    if payload.get("approval_id") != "pin_plan_review":
        raise AssertionError("pin_plan_review revise sample has wrong approval_id")
    if payload.get("action") != "revise_pin_plan":
        raise AssertionError("pin_plan_review revise sample has wrong action")
    constraints = payload.get("user_pin_constraints")
    if not isinstance(constraints, list) or not constraints:
        raise AssertionError("pin_plan_review revise sample missing user_pin_constraints")
    required_fields = {"device", "device_pin", "mcu_pin", "signal"}
    for index, item in enumerate(constraints):
        if not isinstance(item, dict):
            raise AssertionError(f"user_pin_constraints[{index}] must be an object")
        missing = required_fields - set(item)
        if missing:
            raise AssertionError(f"user_pin_constraints[{index}] missing fields: {missing}")


def check_no_mcu_preferred_candidates() -> None:
    sys.path.insert(0, str(TEST_DIR))
    try:
        import select_hw_runner  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    manifest = draft["upstream_manifest"]
    manifest["requirements"]["mcu_specified"] = None
    candidates = select_hw_runner.select_board_candidates(manifest, limit=3)
    families = {candidate.get("chip_family") for candidate in candidates}
    preferred = {"rp2", "esp32", "esp32s2", "esp32s3", "esp32c3", "esp32c6"}
    if not candidates:
        raise AssertionError("no candidates returned for no-MCU manifest")
    if not families.issubset(preferred):
        raise AssertionError(f"no-MCU candidates include non-preferred families: {families - preferred}")
    if "rp2" not in families or not any(str(family).startswith("esp32") for family in families):
        raise AssertionError(f"no-MCU candidates should include both Pico/RP2 and ESP32 families: {families}")


def check_phase_complete_validation() -> None:
    success_path = SAMPLE_DIR / "phase_complete.select_hw.success.json"
    partial_path = SAMPLE_DIR / "phase_complete.select_hw.partial.json"
    compare_path = SAMPLE_DIR / "select_hw_manifest.after.json"
    with tempfile.TemporaryDirectory(prefix="select-hw-phase-") as temp_dir:
        session_dir = Path(temp_dir) / "sessions" / SESSION_ID
        session_dir.mkdir(parents=True, exist_ok=True)
        for sample_file, dest_name in [
            ("select_hw_draft.json", "select_hw_draft.json"),
            ("select_hw_manifest.after.json", "select_hw_validated.json"),
            ("pin_assignment_log.md", "pin_assignment_log.md"),
            ("select_hw_phase_log.md", "select_hw_phase_log.md"),
        ]:
            src = SAMPLE_DIR / sample_file
            if src.is_file():
                shutil.copy2(src, session_dir / dest_name)
        (session_dir / "phase_complete.select_hw.json").write_text(
            "{}", encoding="utf-8"
        )
        for path in [success_path, partial_path]:
            expected = [item if item != "phase_complete.select_hw.success.json" else path.name
                        for item in EXPECTED_ARTIFACTS_CWD]
            expected_args = [arg for item in expected for arg in ["--expected-artifact", item]]
            compare_args = ["--compare-manifest", str(compare_path)] if path == success_path else []
            proc = run(
                [
                    sys.executable,
                    str(SELECT_HW_MANIFEST),
                    "--validate-phase-complete",
                    "--input",
                    str(path),
                    *compare_args,
                    "--artifact-root",
                    str(temp_dir),
                    "--board-root",
                    str(BOARD_ROOT),
                    "--strict-board-pins",
                    *expected_args,
                ]
            )
            if proc.returncode != 0:
                raise AssertionError(
                    f"phase_complete validation failed for {path.name}:\nstdout={proc.stdout}\nstderr={proc.stderr}"
                )
            result = json.loads(proc.stdout)
            if result.get("status") != "ok":
                raise AssertionError(f"phase_complete validation did not return ok for {path.name}: {result}")


def check_phase_complete_requires_logs() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    artifacts = bad["payload"]["artifacts"]
    for artifact in artifacts:
        if artifact.get("type") != "file_list":
            continue
        artifact["files"] = [
            item for item in artifact.get("files", [])
            if Path(item.get("path", "")).name not in {"pin_assignment_log.md", "select_hw_phase_log.md"}
        ]
    expected_args = [arg for item in EXPECTED_ARTIFACTS_CWD for arg in ["--expected-artifact", item]]
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--compare-manifest",
            str(SAMPLE_DIR / "select_hw_manifest.after.json"),
            "--artifact-root",
            str(SKILL_DIR),
            "--board-root",
            str(BOARD_ROOT),
            "--strict-board-pins",
            *expected_args,
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("phase_complete validation should fail when log artifacts are not declared")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "pin_assignment_log.md" not in joined or "select_hw_phase_log.md" not in joined:
        raise AssertionError(f"missing log artifacts were not reported: {result}")


def check_success_requires_pin_review() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    bad["payload"]["manifest_content"]["pin_review"]["confirmed"] = False
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--compare-manifest",
            str(SAMPLE_DIR / "select_hw_manifest.after.json"),
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("phase_complete success should fail when pin_review is not confirmed")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "pin_review.confirmed" not in joined:
        raise AssertionError(f"missing pin_review confirmation error: {result}")


def check_pin_review_timing_validation() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    bad["payload"]["manifest_content"]["pin_review"]["confirmed_at"] = "2026-06-21T00:00:00Z"
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--compare-manifest",
            str(SAMPLE_DIR / "select_hw_manifest.after.json"),
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("phase_complete success should fail when pin_review.confirmed_at is a stale placeholder")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "confirmed_at" not in joined or ("too old" not in joined and "placeholder" not in joined):
        raise AssertionError(f"stale pin_review.confirmed_at was not reported: {result}")


def check_pin_decision_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad = json.loads(json.dumps(draft))
    bad["hardware_plan"]["pin_decisions"][0]["decision_type"] = "not_a_decision"
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("invalid pin_decision decision_type should fail validation")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "decision_type invalid" not in joined:
        raise AssertionError(f"invalid pin decision type was not reported: {result}")


def check_power_pin_type_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad = json.loads(json.dumps(draft))
    for item in bad["hardware_plan"]["pinout"]:
        if item.get("gpio") == "GND":
            item["type"] = "gpio_in"
            break
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("power/ground rails must not validate as gpio_in/gpio_out")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "type must be gnd" not in joined:
        raise AssertionError(f"power pin type mismatch was not reported: {result}")


def check_config_power_tie_simplified_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad = json.loads(json.dumps(draft))
    bad["hardware_plan"]["pinout"].append(
        {
            "device": "MAX98357",
            "pin_name": "GAIN",
            "gpio": "3V3",
            "type": "power_3v3",
            "source": "power",
            "notes": "test fixture: fixed mode/config pin tied to power",
        }
    )
    bad["hardware_plan"]["pin_decisions"].append(
        {
            "device": "MAX98357",
            "pin_name": "GAIN",
            "assigned_gpio": "3V3",
            "decision_type": "fixed_power_tie",
            "source": "fixed_power",
            "evidence": {"note": "test fixture: mode/config pin tied to power"},
            "requires_user_review": False,
        }
    )
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(f"config power tie review flag should not be fatal:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("warnings", []))
    if "requires_user_review should be true" in joined:
        raise AssertionError(f"requires_user_review strategy warning should not be emitted in simplified V0: {result}")


def check_adc2_wifi_digital_warning() -> None:
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--input",
            str(SAMPLE_DIR / "select_hw_draft.json"),
            "--board-root",
            str(BOARD_ROOT),
        ]
    )
    if proc.returncode != 0:
        raise AssertionError(f"sample draft should pass while reporting ADC2 digital warning:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("warnings", []))
    for gpio in ["GPIO4", "GPIO5"]:
        if gpio not in joined:
            raise AssertionError(f"ADC2 digital warning should include {gpio}: {result}")
    if "digital signals" not in joined:
        raise AssertionError(f"ADC2 warning should explain digital use is allowed: {result}")


def check_strict_board_pin_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad_draft = json.loads(json.dumps(draft))
    bad_draft["hardware_plan"]["pinout"][0]["gpio"] = 8
    bad_draft["hardware_plan"]["pinout"][0]["source"] = "auto_assigned"
    bad_draft["hardware_plan"]["pinout"][0]["notes"] = ""
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
            "--strict-board-pins",
        ],
        input_text=json.dumps(bad_draft, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("strict board pin validation should reject strapping/default-bus deviation")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []) + result.get("warnings", []))
    if "strapping" not in joined and "default" not in joined:
        raise AssertionError(f"strict board pin validation did not report expected issue: {result}")


def check_user_wiring_and_onboard_validation() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(draft, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(f"user_wiring sample should pass board validation:\nstdout={proc.stdout}\nstderr={proc.stderr}")

    occupied_draft = json.loads(json.dumps(draft))
    occupied_draft["hardware_plan"]["pinout"][3]["gpio"] = 8
    occupied_draft["hardware_plan"]["pinout"][3]["source"] = "auto_assigned"
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(occupied_draft, ensure_ascii=False),
    )
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []) + result.get("warnings", []))
    if "onboard peripheral" not in joined:
        raise AssertionError(f"onboard occupied pin warning was not reported: {result}")


def check_pinout_rejects_unknown_device() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad = json.loads(json.dumps(draft))
    bad["hardware_plan"]["pinout"].append(
        {
            "device": "DHT22",
            "pin_name": "DATA",
            "gpio": 12,
            "type": "gpio_in",
            "source": "auto_assigned",
        }
    )
    bad["hardware_plan"]["pin_decisions"].append(
        {
            "device": "DHT22",
            "pin_name": "DATA",
            "assigned_gpio": 12,
            "decision_type": "auto_assign_free_gpio",
            "source": "auto_assigned",
            "evidence": {"note": "test fixture: unknown generated device"},
            "requires_user_review": False,
        }
    )
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("pinout must reject devices not confirmed by upstream analyze")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "DHT22" not in joined or "upstream_manifest.devices" not in joined:
        raise AssertionError(f"unknown pinout device was not reported: {result}")


def check_bom_rejects_unknown_functional_hardware() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    bad = json.loads(json.dumps(draft))
    bad["hardware_plan"]["bom"].append(
        {
            "name": "OLED显示屏",
            "model": "SSD1306",
            "quantity": 1,
            "unit_price_yuan": 9,
            "product_url": "https://example.invalid/ssd1306",
        }
    )
    bad["hardware_plan"]["estimated_total_yuan"] = 67
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("BOM must reject functional hardware not confirmed upstream")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "SSD1306" not in joined and "OLED" not in joined:
        raise AssertionError(f"unknown functional BOM hardware was not reported: {result}")


def check_bom_allows_support_items_and_links() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    ok = json.loads(json.dumps(draft))
    ok["hardware_plan"]["bom"].append(
        {
            "name": "杜邦线",
            "model": "Female-Female 20cm",
            "quantity": 1,
            "unit_price_yuan": 3,
            "product_url": "https://example.invalid/jumper-wire",
        }
    )
    ok["hardware_plan"]["bom"][2]["product_url"] = "https://example.invalid/ttp223"
    ok["hardware_plan"]["estimated_total_yuan"] = 64
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(ok, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(
            "BOM support items and product links should not be treated as downstream hardware contract:\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )


def check_bom_link_index_template() -> None:
    template_path = SKILL_DIR / "references" / "bom_item_link_index.template.json"
    template = load_json(template_path)
    policy = template.get("policy", {})
    if policy.get("applies_to") != "all_physical_bom_items":
        raise AssertionError("BOM link template must apply to all physical BOM items")
    if policy.get("required_for_select_hw_success") is not False:
        raise AssertionError("BOM links must remain optional for select-hw success")
    if policy.get("do_not_fabricate_links") is not True:
        raise AssertionError("BOM link template must prohibit fabricated links")
    required = {"product_url", "shop_url", "datasheet_url", "supplier", "sku"}
    fields = set(template.get("link_fields", []))
    if fields != required:
        raise AssertionError(f"BOM link template fields mismatch: {fields}")
    item_template = template.get("bom_item_template", {})
    missing = required.difference(item_template)
    if missing:
        raise AssertionError(f"BOM item template missing link fields: {missing}")


def check_bom_link_template_is_optional_and_normalized() -> None:
    draft = load_json(SAMPLE_DIR / "select_hw_draft.json")
    missing = json.loads(json.dumps(draft))
    for item in missing["hardware_plan"]["bom"]:
        for field in ["product_url", "shop_url", "datasheet_url", "supplier", "sku"]:
            item.pop(field, None)
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(missing, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(
            "BOM link fields are optional procurement metadata and must not block select-hw:\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    result = json.loads(proc.stdout)
    manifest = result.get("manifest") or {}
    bom = manifest.get("bom")
    if not isinstance(bom, list) or not bom:
        raise AssertionError(f"normalized manifest missing BOM: {result}")
    required = {"product_url", "shop_url", "datasheet_url", "supplier", "sku"}
    for index, item in enumerate(bom):
        if not isinstance(item, dict):
            continue
        missing_fields = required.difference(item)
        if missing_fields:
            raise AssertionError(f"normalized BOM[{index}] missing optional link template fields: {missing_fields}")
        for field in required:
            if not isinstance(item.get(field), str):
                raise AssertionError(f"normalized BOM[{index}].{field} must be a string template value")


def check_runtime_context_required() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    del bad["payload"]["runtime_context"]
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("phase_complete validation should fail when runtime_context is missing")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "runtime_context" not in joined:
        raise AssertionError(f"missing runtime_context was not reported: {result}")


def check_artifact_root_mode_cwd_bare_fails() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    bad = json.loads(json.dumps(phase_complete))
    bad["payload"]["runtime_context"]["artifact_root_mode"] = "cwd"
    for artifact in bad["payload"]["artifacts"]:
        if artifact.get("type") != "file_list":
            continue
        for item in artifact.get("files", []):
            item["path"] = Path(item["path"]).name
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(bad, ensure_ascii=False),
    )
    if proc.returncode == 0:
        raise AssertionError("cwd mode should reject bare filenames")
    result = json.loads(proc.stdout)
    joined = "\n".join(result.get("errors", []))
    if "must be under" not in joined:
        raise AssertionError(f"bare filename in cwd mode was not reported: {result}")


def check_artifact_root_mode_session_root_ok() -> None:
    phase_complete = load_json(SAMPLE_DIR / "phase_complete.select_hw.success.json")
    modified = json.loads(json.dumps(phase_complete))
    modified["payload"]["runtime_context"]["artifact_root_mode"] = "session_root"
    modified["payload"]["runtime_context"]["session_root"] = "."
    for artifact in modified["payload"]["artifacts"]:
        if artifact.get("type") != "file_list":
            continue
        for item in artifact.get("files", []):
            item["path"] = Path(item["path"]).name
    proc = run(
        [
            sys.executable,
            str(SELECT_HW_MANIFEST),
            "--validate-phase-complete",
            "--stdin",
            "--board-root",
            str(BOARD_ROOT),
        ],
        input_text=json.dumps(modified, ensure_ascii=False),
    )
    if proc.returncode != 0:
        raise AssertionError(f"session_root mode should accept bare filenames:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    result = json.loads(proc.stdout)
    if result.get("status") != "ok":
        raise AssertionError(f"session_root mode validation did not return ok: {result}")


def check_runner_bridge() -> None:
    proc = run([sys.executable, str(TEST_DIR / "run_local_mock_session.py")])
    combined = proc.stdout + proc.stderr
    if proc.returncode != 0:
        raise AssertionError(f"runner bridge failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")
    if "PHASE COMPLETE" not in combined:
        raise AssertionError(f"runner bridge did not reach phase_complete:\n{combined}")
    if "upy-flash-mpy-firmware-plugin" not in combined:
        raise AssertionError(f"runner bridge did not emit upy-flash-mpy-firmware-plugin next phase:\n{combined}")
    for path in ["pin_assignment_log.md", "select_hw_phase_log.md"]:
        if path not in combined:
            raise AssertionError(f"runner bridge phase_complete did not declare {path}:\n{combined}")


def check_plugin_manifest() -> None:
    if not PLUGIN_VALIDATOR.exists():
        print(f"[SKIP] plugin validator not found: {PLUGIN_VALIDATOR}")
        return
    proc = run([sys.executable, str(PLUGIN_VALIDATOR), str(SKILL_DIR)])
    if proc.returncode != 0:
        raise AssertionError(f"plugin validator failed:\nstdout={proc.stdout}\nstderr={proc.stderr}")


def main() -> int:
    checks = [
        ("sample json", check_sample_json),
        ("skill path contract", check_skill_path_contract),
        ("manifest validation", check_manifest_validation),
        ("cold-driver status normalization", check_cold_driver_status_normalization),
        ("formatted output validation", check_formatted_output_validation),
        ("board unavailable sample", check_board_unavailable_sample),
        ("pin plan revise response sample", check_pin_plan_revise_response_sample),
        ("no mcu preferred candidates", check_no_mcu_preferred_candidates),
        ("phase_complete validation", check_phase_complete_validation),
        ("phase_complete requires logs", check_phase_complete_requires_logs),
        ("success requires pin review", check_success_requires_pin_review),
        ("pin review timing validation", check_pin_review_timing_validation),
        ("pin decision validation", check_pin_decision_validation),
        ("power pin type validation", check_power_pin_type_validation),
        ("config power tie simplified validation", check_config_power_tie_simplified_validation),
        ("adc2 wifi digital warning", check_adc2_wifi_digital_warning),
        ("strict board pin validation", check_strict_board_pin_validation),
        ("user wiring and onboard validation", check_user_wiring_and_onboard_validation),
        ("pinout rejects unknown device", check_pinout_rejects_unknown_device),
        ("bom rejects unknown functional hardware", check_bom_rejects_unknown_functional_hardware),
        ("bom allows support items and links", check_bom_allows_support_items_and_links),
        ("bom link index template", check_bom_link_index_template),
        ("bom link template optional and normalized", check_bom_link_template_is_optional_and_normalized),
        ("runtime context required", check_runtime_context_required),
        ("artifact cwd bare fails", check_artifact_root_mode_cwd_bare_fails),
        ("artifact session_root ok", check_artifact_root_mode_session_root_ok),
        ("runner bridge", check_runner_bridge),
        ("plugin manifest", check_plugin_manifest),
    ]
    for name, check in checks:
        check()
        print(f"[OK] {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
