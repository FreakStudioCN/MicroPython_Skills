#!/usr/bin/env python3
"""Validate an mpos-prepare-deps dependency handoff JSON file."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_DEP_FIELDS = {
    "name",
    "source",
    "url",
    "install_action",
    "target_path",
    "imports",
    "app_layer_ok",
    "async_compatible",
    "sync_needs_adapter",
}
REQUIRED_SOURCES = {
    "mpos_builtin",
    "micropython-lib",
    "upypi",
    "awesome-micropython",
    "github",
}
REQUIRED_ASYNC_TERMS = {
    "async",
    "asyncio",
    "uasyncio",
    "aio",
    "await",
    "create_task",
    "sleep_ms",
    "non-blocking",
}
ASYNC_QUERY_HINTS = {
    "async",
    "asyncio",
    "uasyncio",
    "aio",
    "await",
    "create_task",
    "sleep_ms",
    "non-blocking",
    "nonblocking",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def _list_of_strings(value: object, field: str) -> list[str]:
    require(isinstance(value, list), f"{field} must be a list")
    result = []
    for index, item in enumerate(value):
        require(isinstance(item, str) and item, f"{field}[{index}] must be a non-empty string")
        result.append(item)
    return result


def _safe_rel(path: str, field: str) -> Path:
    value = Path(path)
    require(not value.is_absolute(), f"{field} must be relative")
    require(".." not in value.parts, f"{field} must not contain ..")
    return value


def _starts_with_path(path: str, prefix: str, field: str) -> None:
    _safe_rel(path, field)
    require(path == prefix or path.startswith(prefix.rstrip("/") + "/"), f"{field} must start with {prefix}")


def _has_async_query(queries: list[str]) -> bool:
    joined = "\n".join(queries).lower()
    return any(term in joined for term in ASYNC_QUERY_HINTS)


def validate(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc}")

    require(data.get("schema_version") == "mpos-prepare-deps-v1", "schema_version must be mpos-prepare-deps-v1")
    require(data.get("phase") == "prepare-deps", "phase must be prepare-deps")
    require(data.get("result") in {"success", "partial", "failed"}, "result must be success, partial, or failed")

    app = data.get("app")
    require(isinstance(app, dict), "app must be an object")
    fullname = app.get("fullname")
    app_dir = app.get("app_dir")
    assets_dir = app.get("assets_dir")
    require(isinstance(fullname, str) and fullname, "app.fullname is required")
    require(isinstance(app_dir, str) and app_dir.endswith(fullname), "app.app_dir must end with app.fullname")
    require(isinstance(assets_dir, str) and assets_dir.endswith(f"{fullname}/assets"), "app.assets_dir must end with <fullname>/assets")

    search_policy = data.get("search_policy")
    require(isinstance(search_policy, dict), "search_policy must be an object")
    sources = set(_list_of_strings(search_policy.get("sources"), "search_policy.sources"))
    missing_sources = sorted(REQUIRED_SOURCES - sources)
    require(not missing_sources, "search_policy.sources missing: " + ", ".join(missing_sources))
    async_terms = {item.lower() for item in _list_of_strings(search_policy.get("async_terms"), "search_policy.async_terms")}
    missing_async_terms = sorted(REQUIRED_ASYNC_TERMS - async_terms)
    require(not missing_async_terms, "search_policy.async_terms missing: " + ", ".join(missing_async_terms))

    cache = data.get("cache", {})
    require(isinstance(cache, dict), "cache must be an object")
    cache_path = ""
    if cache.get("enabled"):
        cache_path = cache.get("path", "")
        require(isinstance(cache_path, str) and cache_path.startswith("tmp/mpos-deps-cache/"), "cache.path must start with tmp/mpos-deps-cache/")
        require(cache_path == f"tmp/mpos-deps-cache/{fullname}", "cache.path must be tmp/mpos-deps-cache/<fullname>")
        artifacts = cache.get("artifacts", [])
        require(isinstance(artifacts, list), "cache.artifacts must be a list when present")
        for index, artifact in enumerate(artifacts):
            require(isinstance(artifact, dict), f"cache.artifacts[{index}] must be an object")
            artifact_path = artifact.get("path")
            require(isinstance(artifact_path, str) and artifact_path, f"cache.artifacts[{index}].path is required")
            _starts_with_path(artifact_path, cache_path, f"cache.artifacts[{index}].path")

    dependencies = data.get("dependencies")
    require(isinstance(dependencies, list), "dependencies must be a list")
    for index, dep in enumerate(dependencies):
        require(isinstance(dep, dict), f"dependencies[{index}] must be an object")
        missing = sorted(REQUIRED_DEP_FIELDS - set(dep))
        require(not missing, f"dependencies[{index}] missing fields: {', '.join(missing)}")
        name = dep.get("name")
        require(isinstance(name, str) and name, f"dependencies[{index}].name is required")
        source = dep.get("source")
        require(isinstance(source, str) and source, f"{name}: source is required")
        require(dep.get("app_layer_ok") is True, f"{name}: accepted dependency must have app_layer_ok=true")
        target_path = dep.get("target_path")
        require(isinstance(target_path, str) and target_path.startswith("assets/"), f"{name}: target_path must start with assets/")
        _safe_rel(target_path, f"{name}: target_path")
        require(target_path.endswith((".py", ".mpy", ".json", ".txt")) or "/__init__.py" in target_path or target_path.endswith("/"), f"{name}: target_path should point at an app runtime file or package")
        imports = _list_of_strings(dep.get("imports"), f"{name}: imports")
        require(imports, f"{name}: imports must not be empty")

        if source != "mpos_builtin":
            search_queries = _list_of_strings(dep.get("search_queries"), f"{name}: search_queries")
            require(_has_async_query(search_queries), f"{name}: search_queries must include async/aio/uasyncio/non-blocking strategy")
            if cache.get("enabled"):
                cache_records = _list_of_strings(dep.get("cache_records"), f"{name}: cache_records")
                require(cache_records, f"{name}: cache_records must not be empty when cache is enabled")
                for record_index, record_path in enumerate(cache_records):
                    _starts_with_path(record_path, cache_path, f"{name}: cache_records[{record_index}]")

        downloaded_to = dep.get("downloaded_to")
        if downloaded_to is not None:
            require(downloaded_to in {"app", "staged", "none"}, f"{name}: downloaded_to must be app, staged, or none")
        staged_path = dep.get("staged_path")
        if staged_path is not None:
            require(isinstance(staged_path, str), f"{name}: staged_path must be a string")
            _starts_with_path(staged_path, f"{cache_path}/staged/assets", f"{name}: staged_path")

        async_compatible = dep.get("async_compatible")
        sync_needs_adapter = dep.get("sync_needs_adapter")
        require(isinstance(async_compatible, bool), f"{name}: async_compatible must be boolean")
        require(isinstance(sync_needs_adapter, bool), f"{name}: sync_needs_adapter must be boolean")
        if not async_compatible:
            require(sync_needs_adapter is True, f"{name}: sync dependencies must set sync_needs_adapter=true")
            adapter_requirements = dep.get("adapter_requirements")
            require(isinstance(adapter_requirements, list) and adapter_requirements, f"{name}: sync dependency needs adapter_requirements")

        if dep.get("requires_vendor_path_injection"):
            require(dep.get("vendor_sys_path") == "assets/vendor", f"{name}: vendor dependencies must declare vendor_sys_path=assets/vendor")

        files = dep.get("files", [])
        require(isinstance(files, list), f"{name}: files must be a list when present")
        for file_index, file_item in enumerate(files):
            require(isinstance(file_item, dict), f"{name}: files[{file_index}] must be an object")
            file_target = file_item.get("target_path")
            if file_item.get("runtime", True):
                require(isinstance(file_target, str) and file_target.startswith("assets/"), f"{name}: runtime files[{file_index}].target_path must start with assets/")
                _safe_rel(file_target, f"{name}: files[{file_index}].target_path")
                file_staged_path = file_item.get("staged_path")
                if file_staged_path is not None:
                    require(isinstance(file_staged_path, str), f"{name}: files[{file_index}].staged_path must be a string")
                    _starts_with_path(file_staged_path, f"{cache_path}/staged/assets", f"{name}: files[{file_index}].staged_path")

    rejected = data.get("rejected", [])
    require(isinstance(rejected, list), "rejected must be a list")
    for index, item in enumerate(rejected):
        require(isinstance(item, dict), f"rejected[{index}] must be an object")
        require(bool(item.get("name")), f"rejected[{index}].name is required")
        require(bool(item.get("reason")), f"rejected[{index}].reason is required")

    handoff = data.get("handoff")
    require(isinstance(handoff, dict), "handoff must be an object")
    require(bool(handoff.get("next_skill")), "handoff.next_skill is required")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_dependency_handoff.py <dependency_handoff.json>", file=sys.stderr)
        return 2
    validate(Path(argv[1]))
    print("Dependency handoff is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
