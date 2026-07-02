#!/usr/bin/env python3
"""Validate upy-wiring-plugin start, upstream, and phase_complete JSON files."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from common import configure_stdio, load_json, manifest_of, payload_of, print_json


PHASE = "upy-wiring-plugin"
UPSTREAM_PHASE = "upy-generate-plugin"
PROTOCOL_VERSION = "1.0"
SUCCESS_REQUIRED = {
    "docs/wiring.json",
    "docs/wiring.md",
    "docs/wiring.html",
    "docs/wiring_pins.md",
    "docs/wiring.svg",
    "docs/wiring.png",
}
IMAGE_ARTIFACTS = {"docs/wiring.svg", "docs/wiring.png"}
ALLOWED_RESULTS = {"success", "partial", "failed"}
REQUIRED_CAPABILITIES = {
    "approval_request",
    "file_operation",
    "script_run",
    "checkpoint_resume",
    "cancellation",
    "retry",
    "timeout",
    "permission_prompt",
}
ALLOWED_INVOCATION_MODES = {"plugin_protocol", "local_skill_test"}
ALLOWED_CHECKPOINTS = {
    "started",
    "upstream_validated",
    "inputs_read",
    "wiring_json_written",
    "wiring_json_validated",
    "artifacts_rendered",
    "manifest_updated",
    "phase_completed",
    "render_incomplete",
    "cancelled",
    "failed",
}
ERROR_CODES = {
    "PROTOCOL_UNSUPPORTED",
    "CAPABILITY_UNAVAILABLE",
    "UPSTREAM_PHASE_MISSING",
    "UPSTREAM_PHASE_INVALID",
    "PROJECT_MANIFEST_MISSING",
    "FIRMWARE_NOT_FOUND",
    "WIRING_SCHEMA_INVALID",
    "WIRING_CONFLICT_REQUIRES_REVIEW",
    "WIRING_IMAGE_RENDER_PERMISSION_DENIED",
    "WIRING_IMAGE_RENDER_TIMEOUT",
    "WIRING_IMAGE_RENDER_FAILED",
    "FILE_PERMISSION_DENIED",
    "SCRIPT_PERMISSION_DENIED",
    "CANCELLED_BY_USER",
    "IDEMPOTENCY_CONFLICT",
}
WARNING_CODES = {
    "WIRING_IMAGE_RENDER_NETWORK_FALLBACK",
    "WIRING_HTML_USES_CDN",
    "WIRING_CONFLICT_NON_BLOCKING",
    "WIRING_ARTIFACT_REUSED",
}
NETWORK_BACKENDS = {"mermaid_ink", "cdn", "network"}
MULTIWIRE_INTERFACES = {"I2S", "I2C", "SPI", "UART"}
MIDDLEWARE_TYPES = {"middleware", "cloud", "service", "software", "library"}
MIDDLEWARE_INTERFACES = {"WIFI", "NETWORK", "HTTP", "HTTPS", "MQTT", "REST"}


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def norm_path(value: str) -> str:
    return str(PurePosixPath(value.replace("\\", "/")))


def artifact_paths(artifacts: Any) -> set[str]:
    paths: set[str] = set()
    if not isinstance(artifacts, list):
        return paths
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("path")
        if isinstance(path, str):
            paths.add(norm_path(path))
        files = artifact.get("files")
        if isinstance(files, list):
            for item in files:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.add(norm_path(item["path"]))
    return paths


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def idempotency_key_valid(value: Any, session_id: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if isinstance(session_id, str) and session_id and session_id not in value:
        return False
    return bool(re.match(r"^upy-wiring-plugin:[^:]+:[a-z0-9_-]+:v[0-9]+$", value))


def structured_errors_valid(value: Any, errors: list[str], *, required: bool = False) -> None:
    if value in (None, []):
        if required:
            errors.append("structured errors are required")
        return
    require(isinstance(value, list), errors, "payload.errors must be a list")
    if not isinstance(value, list):
        return
    for idx, item in enumerate(value):
        require(isinstance(item, dict), errors, f"errors[{idx}] must be an object")
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        require(isinstance(code, str) and code in ERROR_CODES, errors, f"errors[{idx}].code is invalid")
        require(item.get("severity") in {"info", "warning", "blocking"}, errors, f"errors[{idx}].severity is invalid")
        require(isinstance(item.get("retryable"), bool), errors, f"errors[{idx}].retryable boolean is required")
        require(isinstance(item.get("message"), str) and bool(item.get("message")), errors, f"errors[{idx}].message is required")
        require(item.get("checkpoint") in ALLOWED_CHECKPOINTS, errors, f"errors[{idx}].checkpoint is invalid")
        require(isinstance(item.get("next_action"), str) and bool(item.get("next_action")), errors, f"errors[{idx}].next_action is required")


def structured_warnings_valid(value: Any, errors: list[str]) -> None:
    if value in (None, []):
        return
    require(isinstance(value, list), errors, "payload.warnings must be a list")
    if not isinstance(value, list):
        return
    for idx, item in enumerate(value):
        require(isinstance(item, dict), errors, f"warnings[{idx}] must be an object")
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        require(isinstance(code, str) and code in WARNING_CODES, errors, f"warnings[{idx}].code is invalid")
        require(item.get("severity") in {"info", "warning"}, errors, f"warnings[{idx}].severity is invalid")
        require(isinstance(item.get("retryable"), bool), errors, f"warnings[{idx}].retryable boolean is required")
        require(isinstance(item.get("message"), str) and bool(item.get("message")), errors, f"warnings[{idx}].message is required")
        require(item.get("checkpoint") in ALLOWED_CHECKPOINTS, errors, f"warnings[{idx}].checkpoint is invalid")


def network_permission_valid(payload: dict[str, Any], backend: Any) -> bool:
    if backend not in NETWORK_BACKENDS:
        return True
    permission = payload.get("network_permission") or payload.get("permission_grant")
    if not isinstance(permission, dict):
        return False
    return (
        permission.get("approval_id") == "wiring_network_render"
        and permission.get("result") in {"render_all", "allow", "approved"}
        and isinstance(permission.get("granted_at"), str)
        and bool(permission.get("granted_at"))
    )


def normalize_token(value: Any) -> str:
    return re.sub(r"[^0-9a-z]+", "", str(value or "").lower())


def name_tokens(value: Any) -> set[str]:
    raw = re.findall(r"[0-9A-Za-z]+", str(value or "").lower())
    stop = {"and", "with", "speaker", "audio", "amplifier", "module", "device"}
    return {item for item in raw if len(item) >= 3 and item not in stop}


def gpio_key(value: Any) -> str:
    text = str(value or "").strip()
    match = re.match(r"^(?:GPIO)?([0-9]+)$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return text.upper()


def is_gpio_like(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(re.match(r"^(?:GPIO)?[0-9]+$", text, flags=re.IGNORECASE) or re.match(r"^GP[0-9]+$", text, flags=re.IGNORECASE))


def manifest_device_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    devices = manifest.get("devices")
    if not isinstance(devices, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in devices:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            result[item["name"]] = item
    return result


def is_physical_device(device: dict[str, Any] | None) -> bool:
    if not isinstance(device, dict):
        return True
    dtype = str(device.get("type") or "").strip().lower()
    iface = str(device.get("interface") or "").strip().upper()
    if dtype in MIDDLEWARE_TYPES:
        return False
    if iface in MIDDLEWARE_INTERFACES:
        return False
    return True


def component_text(component: dict[str, Any]) -> str:
    return " ".join(str(component.get(key) or "") for key in ("id", "name", "model", "type", "interface"))


def component_matches_device(component: dict[str, Any], device_name: str) -> bool:
    text = normalize_token(component_text(component))
    device_norm = normalize_token(device_name)
    if device_norm and (device_norm in text or text in device_norm):
        return True
    tokens = name_tokens(device_name)
    if not tokens:
        return False
    return any(token in text for token in tokens)


def endpoint_matches_device(endpoint: dict[str, Any], components: list[dict[str, Any]], device_name: str) -> bool:
    component_ref = str(endpoint.get("component") or "")
    for component in components:
        if not isinstance(component, dict):
            continue
        ids = {str(component.get("id") or ""), str(component.get("name") or "")}
        if component_ref in ids and component_matches_device(component, device_name):
            return True
    return component_matches_device({"id": component_ref, "name": component_ref}, device_name)


def endpoint_is_mcu(endpoint: dict[str, Any], components: list[dict[str, Any]]) -> bool:
    component_ref = str(endpoint.get("component") or "")
    if component_ref.lower() == "mcu":
        return True
    for component in components:
        if not isinstance(component, dict):
            continue
        ids = {str(component.get("id") or ""), str(component.get("name") or "")}
        if component_ref in ids and str(component.get("type") or "").lower() == "mcu":
            return True
    return False


def endpoint_has_gpio(endpoint: dict[str, Any], expected_gpio: Any) -> bool:
    expected = gpio_key(expected_gpio)
    values = [endpoint.get("gpio"), endpoint.get("pin"), endpoint.get("label"), endpoint.get("role")]
    for value in values:
        if value is None:
            continue
        text = str(value)
        if gpio_key(text) == expected:
            return True
        if re.search(rf"\bGPIO{re.escape(expected)}\b", text, flags=re.IGNORECASE):
            return True
    return False


def endpoint_pin_matches(endpoint: dict[str, Any], pin_name: Any) -> bool:
    expected = str(pin_name or "").strip().lower()
    if not expected:
        return False
    for key in ("pin", "label", "role"):
        value = str(endpoint.get(key) or "").strip().lower()
        if value == expected or expected in value:
            return True
    return False


def load_project_manifest(artifact_root: Path) -> dict[str, Any] | None:
    manifest_path = artifact_root / "project-manifest.json"
    if not manifest_path.is_file():
        return None
    return load_json(manifest_path)


def candidate_upstream_paths(payload: dict[str, Any], artifact_root: Path | None, session_root: Path | None) -> list[Path]:
    raw_path = payload.get("source_phase_complete_path")
    if not isinstance(raw_path, str) or not raw_path:
        return []
    path = Path(raw_path)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        bases: list[Path] = []
        if session_root is not None:
            bases.extend([session_root, session_root.parent, session_root.parent.parent])
        if artifact_root is not None:
            bases.extend([artifact_root, artifact_root.parent, artifact_root.parent.parent])
        seen_bases: set[Path] = set()
        for base in bases:
            if base in seen_bases:
                continue
            seen_bases.add(base)
            candidates.append(base / path)
        if session_root is not None:
            candidates.append(session_root / Path(path.name))
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=False)
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def load_upstream_manifest(payload: dict[str, Any], artifact_root: Path | None, session_root: Path | None) -> dict[str, Any] | None:
    inline = payload.get("source_phase_complete")
    if isinstance(inline, dict):
        manifest = manifest_of(inline)
        if isinstance(manifest, dict) and manifest:
            return manifest
    for path in candidate_upstream_paths(payload, artifact_root, session_root):
        if not path.is_file():
            continue
        try:
            manifest = manifest_of(load_json(path))
        except Exception:
            continue
        if isinstance(manifest, dict) and manifest:
            return manifest
    return None


def project_manifest_update_errors(current_manifest: dict[str, Any], upstream_manifest: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(upstream_manifest, dict):
        return errors
    if "updated_at" not in upstream_manifest or "updated_at" not in current_manifest:
        return errors
    if current_manifest.get("updated_at") != upstream_manifest.get("updated_at"):
        errors.append(
            "project-manifest.json root updated_at must not be changed by upy-wiring-plugin; "
            "write wiring.generated_at or phase_complete.timestamp instead"
        )
    return errors


def manifest_i2s_content_errors(wiring: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pinout = manifest.get("pinout")
    if not isinstance(pinout, list):
        return errors
    devices = manifest_device_map(manifest)
    i2s_pins = [
        item for item in pinout
        if isinstance(item, dict)
        and str(item.get("type") or "").lower().startswith("i2s_")
        and is_gpio_like(item.get("gpio"))
        and is_physical_device(devices.get(str(item.get("device") or "")))
    ]
    if not i2s_pins:
        return errors

    components = wiring.get("components")
    connections = wiring.get("connections")
    buses = wiring.get("buses")
    require(isinstance(components, list) and bool(components), errors, "I2S pinout requires non-empty wiring.json components[]")
    require(isinstance(connections, list) and bool(connections), errors, "I2S pinout requires non-empty wiring.json connections[]")
    require(isinstance(buses, list) and any(isinstance(bus, dict) and bus.get("type") == "i2s" for bus in buses), errors, "I2S pinout requires wiring.json buses[] with type=i2s")
    if not isinstance(components, list) or not isinstance(connections, list):
        return errors

    i2s_devices = sorted({str(pin.get("device") or "") for pin in i2s_pins if pin.get("device")})
    for device_name in i2s_devices:
        if not any(isinstance(component, dict) and component_matches_device(component, device_name) for component in components):
            errors.append(f"I2S device from project-manifest pinout is missing from components[]: {device_name}")

    for pin in i2s_pins:
        device_name = str(pin.get("device") or "")
        pin_name = str(pin.get("pin_name") or pin.get("signal") or "")
        gpio = pin.get("gpio")
        matched = False
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            endpoints = [conn.get("from"), conn.get("to")]
            if not all(isinstance(endpoint, dict) for endpoint in endpoints):
                continue
            mcu_ok = any(endpoint_is_mcu(endpoint, components) and endpoint_has_gpio(endpoint, gpio) for endpoint in endpoints if isinstance(endpoint, dict))
            dev_ok = any(
                endpoint_matches_device(endpoint, components, device_name) and endpoint_pin_matches(endpoint, pin_name)
                for endpoint in endpoints
                if isinstance(endpoint, dict)
            )
            protocol = str(conn.get("protocol") or "").upper()
            if mcu_ok and dev_ok and protocol in {"", "I2S"}:
                matched = True
                break
        if not matched:
            errors.append(f"I2S pinout wire is missing from connections[]: {device_name}.{pin_name} -> GPIO{gpio_key(gpio)}")
    return errors


def wiring_json_content_errors(
    artifact_root: Path,
    *,
    payload: dict[str, Any] | None = None,
    session_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    wiring_path = artifact_root / "docs" / "wiring.json"
    if not wiring_path.is_file():
        return errors
    try:
        wiring = load_json(wiring_path)
    except Exception as exc:
        return [f"docs/wiring.json could not be read for content validation: {exc}"]
    for idx, item in enumerate(wiring.get("standalone", []) if isinstance(wiring.get("standalone"), list) else []):
        if not isinstance(item, dict):
            continue
        pin = item.get("pin")
        if isinstance(pin, str) and "," in pin:
            errors.append(
                f"standalone[{idx}].pin must not contain comma-separated multiple pins in success wiring.json; "
                "use components/connections or buses with device pin mappings"
            )
    connections = wiring.get("connections")
    components = wiring.get("components")
    if isinstance(connections, list) and connections:
        require(isinstance(components, list) and bool(components), errors, "wiring.json connections require non-empty components")
        for idx, conn in enumerate(connections):
            require(isinstance(conn, dict), errors, f"connections[{idx}] must be an object")
            if not isinstance(conn, dict):
                continue
            for end_name in ("from", "to"):
                endpoint = conn.get(end_name)
                require(isinstance(endpoint, dict), errors, f"connections[{idx}].{end_name} must be an object")
                if isinstance(endpoint, dict):
                    require(isinstance(endpoint.get("component"), str) and endpoint.get("component"), errors, f"connections[{idx}].{end_name}.component is required")
                    require(isinstance(endpoint.get("pin"), str) and endpoint.get("pin"), errors, f"connections[{idx}].{end_name}.pin is required")
    md_path = artifact_root / "docs" / "wiring.md"
    if isinstance(components, list) and components and isinstance(connections, list) and connections and md_path.is_file():
        try:
            md_text = md_path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            errors.append(f"docs/wiring.md could not be read for readability validation: {exc}")
        else:
            if "subgraph alerts_sg" in md_text:
                errors.append("component topology wiring.md must not render alerts_sg inside the main diagram")
            if re.search(r"-+(?:\.|>)?\|[^|\n]{16,}\|", md_text):
                errors.append("component topology wiring.md must not use long Mermaid edge labels; use intermediate net_* label nodes")
            if "net_" not in md_text:
                errors.append("component topology wiring.md must use intermediate net_* label nodes for readable pin-to-pin labels")
    try:
        project_manifest = load_project_manifest(artifact_root)
    except Exception as exc:
        errors.append(f"project-manifest.json could not be read for wiring content validation: {exc}")
        project_manifest = None
    if isinstance(project_manifest, dict):
        upstream_manifest = load_upstream_manifest(payload or {}, artifact_root, session_root)
        errors.extend(project_manifest_update_errors(project_manifest, upstream_manifest))
        errors.extend(manifest_i2s_content_errors(wiring, project_manifest))
    return errors


def file_manifest_errors(
    manifest: Any,
    paths: set[str],
    *,
    require_success_files: bool,
    artifact_root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    require(isinstance(manifest, dict), errors, "payload.file_manifest object is required")
    if not isinstance(manifest, dict):
        return errors
    require(isinstance(manifest.get("path"), str) and manifest.get("path"), errors, "file_manifest.path is required")
    files = manifest.get("files")
    require(isinstance(files, list), errors, "file_manifest.files list is required")
    if not isinstance(files, list):
        return errors
    file_paths: set[str] = set()
    for idx, item in enumerate(files):
        require(isinstance(item, dict), errors, f"file_manifest.files[{idx}] must be an object")
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str):
            norm = norm_path(path)
            file_paths.add(norm)
            require(norm in paths, errors, f"file_manifest.files[{idx}].path must also appear in artifacts")
        else:
            errors.append(f"file_manifest.files[{idx}].path is required")
        require(isinstance(item.get("type"), str) and item.get("type"), errors, f"file_manifest.files[{idx}].type is required")
        require(item.get("required") is True, errors, f"file_manifest.files[{idx}].required must be true")
        sha = item.get("sha256")
        require(isinstance(sha, str) and bool(re.match(r"^[0-9a-f]{64}$", sha)), errors, f"file_manifest.files[{idx}].sha256 must be 64 lowercase hex chars")
        expected_bytes = item.get("bytes")
        expected_sha = item.get("sha256")
        require(isinstance(expected_bytes, int) and expected_bytes > 0, errors, f"file_manifest.files[{idx}].bytes must be positive integer")
        require(isinstance(item.get("source"), str) and item.get("source"), errors, f"file_manifest.files[{idx}].source is required")
        require(item.get("checkpoint") in ALLOWED_CHECKPOINTS, errors, f"file_manifest.files[{idx}].checkpoint is invalid")
        if artifact_root is not None and isinstance(path, str):
            real_path = artifact_root / norm
            require(real_path.is_file(), errors, f"file_manifest.files[{idx}].path does not exist under artifact_root: {norm}")
            if real_path.is_file():
                actual_bytes = real_path.stat().st_size
                require(actual_bytes == expected_bytes, errors, f"file_manifest.files[{idx}].bytes mismatch for {norm}: expected {expected_bytes}, got {actual_bytes}")
                if isinstance(expected_sha, str) and re.match(r"^[0-9a-f]{64}$", expected_sha):
                    actual_sha = sha256_file(real_path)
                    require(actual_sha == expected_sha, errors, f"file_manifest.files[{idx}].sha256 mismatch for {norm}")
    if require_success_files:
        missing = sorted(SUCCESS_REQUIRED - file_paths)
        require(not missing, errors, f"file_manifest missing required wiring files: {missing}")
    return errors


def session_state_errors(state: Any, payload: dict[str, Any], *, success: bool) -> list[str]:
    errors: list[str] = []
    require(isinstance(state, dict), errors, "payload.session_state object is required")
    if not isinstance(state, dict):
        return errors
    require(isinstance(state.get("path"), str) and state.get("path"), errors, "session_state.path is required")
    checkpoint = state.get("checkpoint")
    require(checkpoint in ALLOWED_CHECKPOINTS, errors, "session_state.checkpoint is invalid")
    if success:
        require(checkpoint == "phase_completed", errors, "success session_state.checkpoint must be phase_completed")
    if "idempotency_key" in state:
        require(state.get("idempotency_key") == payload.get("idempotency_key"), errors, "session_state.idempotency_key must match payload.idempotency_key")
    if "session_id" in state:
        require(state.get("session_id") == payload.get("session_id"), errors, "session_state.session_id must match payload.session_id")
    return errors


def infer_session_root(artifact_root: Path | None) -> Path | None:
    if artifact_root is None:
        return None
    try:
        if artifact_root.name.lower() == "project":
            return artifact_root.parent
    except Exception:
        pass
    return None


def session_file_consistency_errors(session_root: Path | None, payload: dict[str, Any], *, success: bool) -> list[str]:
    errors: list[str] = []
    if not success or session_root is None:
        return errors
    path = session_root / "session_state.upy_wiring_plugin.json"
    if not path.is_file():
        return errors
    try:
        state = load_json(path)
    except Exception as exc:
        return [f"session_state.upy_wiring_plugin.json could not be read: {exc}"]
    if state.get("session_id") and state.get("session_id") != payload.get("session_id"):
        errors.append("session_state file session_id must match phase_complete payload.session_id")
    if state.get("idempotency_key") and state.get("idempotency_key") != payload.get("idempotency_key"):
        errors.append("session_state file idempotency_key must match phase_complete payload.idempotency_key")
    source_phase = payload.get("source_phase")
    mode = state.get("mode")
    source = state.get("source")
    if source_phase == UPSTREAM_PHASE:
        require(mode != "direct_test", errors, "formal upy-generate-plugin success must not have session_state.mode=direct_test")
        require(source != "test_only", errors, "formal upy-generate-plugin success must not have session_state.source=test_only")
    return errors


def validate_start(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = payload_of(data)
    require(data.get("type") == "start_phase", errors, "type must be start_phase")
    require(data.get("protocol_version") == PROTOCOL_VERSION, errors, f"protocol_version must be {PROTOCOL_VERSION}")
    require(data.get("phase") == PHASE or payload.get("phase") == PHASE, errors, f"phase must be {PHASE}")
    session_id = data.get("session_id") or payload.get("session_id")
    idem = data.get("idempotency_key") or payload.get("idempotency_key")
    require(isinstance(session_id, str) and bool(session_id), errors, "session_id is required")
    require(idempotency_key_valid(idem, session_id), errors, "idempotency_key is required and must include session_id")
    require(payload.get("mode") in {"full", "direct_test"}, errors, "payload.mode must be full or direct_test")
    invocation_mode = payload.get("invocation_mode", "plugin_protocol" if payload.get("mode") == "full" else "local_skill_test")
    require(invocation_mode in ALLOWED_INVOCATION_MODES, errors, "payload.invocation_mode is invalid")
    if payload.get("mode") == "full":
        require(invocation_mode == "plugin_protocol", errors, "full mode requires invocation_mode=plugin_protocol")
        require(payload.get("local_test") is not True, errors, "full mode must not set local_test=true")
    if payload.get("mode") == "direct_test":
        require(invocation_mode == "local_skill_test", errors, "direct_test requires invocation_mode=local_skill_test")
        require(payload.get("local_test") is True, errors, "direct_test requires local_test=true")
    require(payload.get("source_phase") in {UPSTREAM_PHASE, "test_only"}, errors, "payload.source_phase must be upy-generate-plugin or test_only")
    runtime = payload.get("runtime_context")
    require(isinstance(runtime, dict), errors, "payload.runtime_context object is required")
    if isinstance(runtime, dict):
        for field in ("session_root", "project_root", "resource_root"):
            require(bool(runtime.get(field)), errors, f"runtime_context.{field} is required")
    capabilities = payload.get("capabilities")
    require(isinstance(capabilities, dict), errors, "payload.capabilities object is required")
    if isinstance(capabilities, dict):
        for field in sorted(REQUIRED_CAPABILITIES):
            require(capabilities.get(field) is True, errors, f"capabilities.{field}=true is required")
    render_policy = payload.get("render_policy")
    require(isinstance(render_policy, dict), errors, "payload.render_policy object is required")
    if isinstance(render_policy, dict):
        formats = set(render_policy.get("formats", [])) if isinstance(render_policy.get("formats"), list) else set()
        require(SUCCESS_REQUIRED <= {f"docs/wiring.{fmt}" if fmt not in {"pins", "json"} else ("docs/wiring_pins.md" if fmt == "pins" else "docs/wiring.json") for fmt in formats}, errors, "render_policy.formats must request json/md/html/pins/svg/png")
        require(render_policy.get("network_rendering") in {"ask", "allow", "deny"}, errors, "render_policy.network_rendering is invalid")
        require(isinstance(render_policy.get("timeout_ms"), int) and render_policy.get("timeout_ms") > 0, errors, "render_policy.timeout_ms positive integer is required")
    if payload.get("mode") == "full":
        require(bool(payload.get("source_phase_complete_path")) or isinstance(payload.get("source_phase_complete"), dict), errors, "full mode requires source_phase_complete or source_phase_complete_path")
    return {"status": "ok" if not errors else "failed", "errors": errors}


def validate_upstream(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    payload = payload_of(data)
    manifest = manifest_of(data)
    require(data.get("type") == "phase_complete", errors, "upstream type must be phase_complete")
    require(data.get("phase") == UPSTREAM_PHASE or payload.get("phase") == UPSTREAM_PHASE, errors, f"upstream phase must be {UPSTREAM_PHASE}")
    require(payload.get("result") == "success", errors, "upstream result must be success")
    require(isinstance(manifest, dict) and bool(manifest), errors, "upstream manifest_content is required")
    if isinstance(manifest, dict):
        require(manifest.get("phase") == "generate", errors, "upstream manifest_content.phase must be generate")
        for field in ("mcu", "devices", "generate"):
            require(field in manifest, errors, f"upstream manifest_content.{field} is required")
    optional = payload.get("optional_next_phases", [])
    if isinstance(optional, list) and optional:
        phases = {item.get("phase") for item in optional if isinstance(item, dict)}
        require(PHASE in phases, errors, f"upstream optional_next_phases must include {PHASE}")
    return {"status": "ok" if not errors else "failed", "errors": errors}


def validate_phase_complete(
    data: dict[str, Any],
    *,
    artifact_root: Path | None = None,
    session_root: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    payload = payload_of(data)
    result = payload.get("result")
    manifest = payload.get("manifest_content")
    artifacts = payload.get("artifacts")
    paths = artifact_paths(artifacts)
    checks = payload.get("checks")
    render_policy = payload.get("render_policy")

    require(data.get("type") == "phase_complete", errors, "type must be phase_complete")
    require(data.get("protocol_version") == PROTOCOL_VERSION or payload.get("protocol_version") == PROTOCOL_VERSION, errors, f"protocol_version must be {PROTOCOL_VERSION}")
    require(data.get("phase") == PHASE or payload.get("phase") == PHASE, errors, f"phase must be {PHASE}")
    require(payload.get("phase") == PHASE, errors, f"payload.phase must be {PHASE}")
    session_id = data.get("session_id") or payload.get("session_id")
    require(isinstance(session_id, str) and bool(session_id), errors, "session_id is required")
    require(idempotency_key_valid(payload.get("idempotency_key"), session_id), errors, "payload.idempotency_key is required and must include session_id")
    require(result in ALLOWED_RESULTS, errors, "payload.result is invalid")
    require(payload.get("checkpoint") in ALLOWED_CHECKPOINTS, errors, "payload.checkpoint is invalid")
    require(payload.get("next_phase") is None, errors, "wiring phase_complete next_phase must be null")
    require(isinstance(artifacts, list), errors, "payload.artifacts must be a list")
    require(isinstance(checks, dict), errors, "payload.checks must be an object")
    require(isinstance(manifest, dict), errors, "payload.manifest_content object is required")
    structured_warnings_valid(payload.get("warnings"), errors)
    if isinstance(manifest, dict):
        require(manifest.get("phase") == "wiring", errors, "manifest_content.phase must be wiring")
        wiring = manifest.get("wiring")
        require(isinstance(wiring, dict), errors, "manifest_content.wiring object is required")
        if isinstance(wiring, dict):
            for key in ("json", "md", "html", "pins"):
                require(bool(wiring.get(key)), errors, f"manifest_content.wiring.{key} is required")
            if result == "success":
                for key in ("svg", "png"):
                    require(bool(wiring.get(key)), errors, f"manifest_content.wiring.{key} is required for success")

    if result == "success":
        missing = sorted(SUCCESS_REQUIRED - paths)
        require(not missing, errors, f"success artifacts missing required wiring files: {missing}")
        require(IMAGE_ARTIFACTS <= paths, errors, "success artifacts must include docs/wiring.svg and docs/wiring.png")
        require(not payload.get("errors"), errors, "success payload.errors must be empty")
        if isinstance(checks, dict):
            for name in ("wiring_schema", "render_wiring", "manifest_update"):
                check = checks.get(name)
                require(isinstance(check, dict) and check.get("ok") is True, errors, f"success checks.{name}.ok=true is required")
        render_result = payload.get("render_result")
        require(isinstance(render_result, dict), errors, "success payload.render_result object is required")
        if isinstance(render_result, dict):
            for key in ("json", "md", "html", "pins", "svg", "png"):
                item = render_result.get(key)
                require(isinstance(item, dict) and item.get("ok") is True and isinstance(item.get("path"), str), errors, f"render_result.{key}.ok=true and path are required")
            network_policy = render_policy.get("network_rendering") if isinstance(render_policy, dict) else None
            if network_policy == "deny":
                for key in ("svg", "png"):
                    item = render_result.get(key)
                    backend = item.get("backend") if isinstance(item, dict) else None
                    require(
                        backend not in {"mermaid_ink", "cdn", "network"},
                        errors,
                        f"render_result.{key}.backend must not use network when render_policy.network_rendering=deny",
                    )
            for key in ("svg", "png"):
                item = render_result.get(key)
                if isinstance(item, dict) and item.get("backend"):
                    backend = item.get("backend")
                    require(
                        backend in {"local_mmdc", "local_mermaid", "mermaid_ink"},
                        errors,
                        f"render_result.{key}.backend is invalid",
                    )
                    require(
                        network_permission_valid(payload, backend),
                        errors,
                        f"render_result.{key}.backend={backend} requires network_permission approval evidence",
                    )
        errors.extend(file_manifest_errors(payload.get("file_manifest"), paths, require_success_files=True, artifact_root=artifact_root))
        errors.extend(session_state_errors(payload.get("session_state"), payload, success=True))
        errors.extend(session_file_consistency_errors(session_root or infer_session_root(artifact_root), payload, success=True))
        if artifact_root is not None:
            errors.extend(wiring_json_content_errors(artifact_root, payload=payload, session_root=session_root))
    elif result in {"partial", "failed"}:
        require(bool(payload.get("errors") or payload.get("warnings") or payload.get("checkpoint")), errors, "partial/failed must include errors, warnings, or checkpoint")
        structured_errors_valid(payload.get("errors"), errors, required=False)
        if payload.get("file_manifest") is not None:
            errors.extend(file_manifest_errors(payload.get("file_manifest"), paths, require_success_files=False, artifact_root=artifact_root))
        if payload.get("session_state") is not None:
            errors.extend(session_state_errors(payload.get("session_state"), payload, success=False))
    return {"status": "ok" if not errors else "failed", "errors": errors}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--validate-start-phase", action="store_true")
    parser.add_argument("--validate-upstream", action="store_true")
    parser.add_argument("--validate-phase-complete", action="store_true")
    parser.add_argument("--artifact-root", default=None, help="Project/artifact root used to verify declared file_manifest files")
    parser.add_argument("--session-root", default=None, help="Session root used to verify session_state consistency")
    return parser.parse_args()


def main() -> int:
    configure_stdio()
    args = parse_args()
    data = load_json(args.input)
    if args.validate_start_phase:
        result = validate_start(data)
    elif args.validate_upstream:
        result = validate_upstream(data)
    elif args.validate_phase_complete:
        artifact_root = Path(args.artifact_root) if args.artifact_root else None
        session_root = Path(args.session_root) if args.session_root else None
        result = validate_phase_complete(data, artifact_root=artifact_root, session_root=session_root)
    else:
        result = {"status": "failed", "errors": ["choose a validation mode"]}
    print_json(result)
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

