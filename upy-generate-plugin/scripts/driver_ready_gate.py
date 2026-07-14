"""Shared #53 explicit driver workflow-status gate for upy-generate-plugin."""

from __future__ import annotations

import re
from typing import Any


READY_STATUS = "ready"
COLD_REQUIRED_STATUS = "cold_driver_required"
BLOCKING_STATUSES = {COLD_REQUIRED_STATUS, "pending_validation", "unverified", "failed"}
KNOWN_STATUSES = BLOCKING_STATUSES | {READY_STATUS}
SELF_TEST_MARKER_RE = re.compile(r"^SELF_TEST_PASS:([^:]+):([^:]+)$")


def _string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_driver_id(value: str | None) -> str | None:
    if not value:
        return None
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_")
    return safe or None


def _driver_id(device: dict[str, Any], driver: dict[str, Any]) -> str | None:
    for value in (
        driver.get("driver_id"),
        driver.get("id"),
        driver.get("name"),
        device.get("driver_id"),
    ):
        text = _string(value)
        if text:
            return text
    return None


def _device_name(device: dict[str, Any], index: int) -> str:
    return _string(device.get("name")) or _string(device.get("id")) or f"devices[{index}]"


def _driver_status(device: dict[str, Any], driver: dict[str, Any]) -> str | None:
    for value in (
        driver.get("status"),
        driver.get("driver_status"),
        device.get("driver_status"),
    ):
        text = _string(value)
        if text:
            return text
    return None


def _marker(driver: dict[str, Any]) -> str | None:
    return _string(driver.get("hardware_marker")) or _string(driver.get("marker"))


def _path(driver: dict[str, Any]) -> str | None:
    return _string(driver.get("path")) or _string(driver.get("driver_path"))


def _pipeline_output(driver_id: str | None) -> str | None:
    safe = _safe_driver_id(driver_id)
    if safe:
        return f"firmware/drivers/{safe}_driver/"
    return "firmware/drivers/<driver_id>_driver/"


def _base_error(
    code: str,
    device_name: str,
    index: int,
    driver_id: str | None,
    status: str | None,
    message: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "phase_step": "pre_generate_driver_ready_gate",
        "device": device_name,
        "device_index": index,
        "driver_id": driver_id,
        "driver_status": status,
        "required_status": READY_STATUS,
        "next_phase": "upy-gen-driver-plugin",
        "next_action": "run_upy_gen_driver_plugin_pipeline",
        "output_path": _pipeline_output(driver_id),
        "retryable": True,
        "message": message,
    }


def driver_ready_gate_errors(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return blocking errors for explicit non-ready driver workflow states.

    Existing scaffold/generate manifests often carry source-only drivers such as
    builtin_runtime, upypi, github, none, or manual without a workflow status.
    Those are resolved by the normal dependency path. This gate only blocks a
    durable driver workflow status when it is present and not hardware-ready.
    """
    devices = manifest.get("devices")
    if not isinstance(devices, list):
        return []

    errors: list[dict[str, Any]] = []
    for index, device in enumerate(devices):
        if not isinstance(device, dict):
            errors.append(
                _base_error(
                    "DRIVER_NOT_READY",
                    f"devices[{index}]",
                    index,
                    None,
                    None,
                    "manifest_content.devices[] entries must be objects before generate can run",
                )
            )
            continue
        driver = device.get("driver")
        device_name = _device_name(device, index)
        if not isinstance(driver, dict):
            driver = {}

        status = _driver_status(device, driver)
        driver_id = _driver_id(device, driver)
        if status is None:
            continue

        if status != READY_STATUS:
            code = "COLD_DRIVER_REQUIRED" if status == COLD_REQUIRED_STATUS else "DRIVER_NOT_READY"
            if status not in KNOWN_STATUSES:
                code = "DRIVER_STATUS_UNSUPPORTED"
            errors.append(
                _base_error(
                    code,
                    device_name,
                    index,
                    driver_id,
                    status,
                    f"device driver_status is {status}; only driver_status=ready can enter generate",
                )
            )
            continue

        driver_path = _path(driver)
        if not driver_path:
            errors.append(
                _base_error(
                    "DRIVER_READY_PATH_MISSING",
                    device_name,
                    index,
                    driver_id,
                    status,
                    "driver_status=ready requires driver.path",
                )
            )

        marker = _marker(driver)
        if not marker:
            errors.append(
                _base_error(
                    "DRIVER_READY_MARKER_MISSING",
                    device_name,
                    index,
                    driver_id,
                    status,
                    "driver_status=ready requires hardware_marker=SELF_TEST_PASS:<driver_id>:<scenario>",
                )
            )
            continue

        marker_match = SELF_TEST_MARKER_RE.match(marker)
        if not marker_match:
            errors.append(
                _base_error(
                    "DRIVER_READY_MARKER_INVALID",
                    device_name,
                    index,
                    driver_id,
                    status,
                    "hardware_marker must match SELF_TEST_PASS:<driver_id>:<scenario>",
                )
            )
            continue

        if driver_id and marker_match.group(1) != driver_id:
            errors.append(
                _base_error(
                    "DRIVER_READY_MARKER_DRIVER_ID_MISMATCH",
                    device_name,
                    index,
                    driver_id,
                    status,
                    "hardware_marker driver_id must match the ready driver metadata",
                )
            )

    return errors
