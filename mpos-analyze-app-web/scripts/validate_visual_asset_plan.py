#!/usr/bin/env python3
"""Validate an automatically selected MPOS visual asset plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ASSET_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_OUTPUT_PIXELS = 262_144


class PlanError(ValueError):
    pass


def _required_string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise PlanError(f"{name} must be a non-empty string")
    return value.strip()


def _required_bool(value, name):
    if not isinstance(value, bool):
        raise PlanError(f"{name} must be a boolean")
    return value


def _required_size(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 1024:
        raise PlanError(f"{name} must be an integer from 1 to 1024")
    return value


def validate(plan, allow_external=False, allow_web=False):
    if not isinstance(plan, dict):
        raise PlanError("visual_asset_plan must be an object")
    if plan.get("schema_version") != "mpos-visual-asset-plan-v1":
        raise PlanError("unsupported visual asset plan schema_version")
    if plan.get("decision_mode") not in {"automatic", "user_override"}:
        raise PlanError("decision_mode must be automatic or user_override")
    strategy = plan.get("render_strategy")
    if strategy not in {"lvgl_native", "raster_asset", "hybrid"}:
        raise PlanError("render_strategy must be lvgl_native, raster_asset, or hybrid")
    assets = plan.get("assets")
    if not isinstance(assets, list):
        raise PlanError("assets must be a list")
    if len(assets) > 64:
        raise PlanError("assets exceeds the 64-item plan budget")
    if strategy == "lvgl_native" and assets:
        raise PlanError("lvgl_native plans cannot contain raster assets")
    if strategy in {"raster_asset", "hybrid"} and not assets:
        raise PlanError(f"{strategy} plans must contain at least one raster asset")
    lvgl_elements = plan.get("lvgl_elements")
    if not isinstance(lvgl_elements, list) or not all(isinstance(item, str) and item.strip() for item in lvgl_elements):
        raise PlanError("lvgl_elements must be a list of non-empty strings")
    seen = set()
    normalized = []
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            raise PlanError(f"{prefix} must be an object")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not ASSET_ID_RE.fullmatch(asset_id):
            raise PlanError(f"{prefix}.id is invalid")
        if asset_id in seen:
            raise PlanError(f"duplicate asset id: {asset_id}")
        seen.add(asset_id)
        purpose = _required_string(asset.get("purpose"), f"{prefix}.purpose")
        reason = _required_string(asset.get("reason"), f"{prefix}.reason")
        fallback = _required_string(asset.get("fallback"), f"{prefix}.fallback")
        required = _required_bool(asset.get("required"), f"{prefix}.required")
        dynamic = _required_bool(asset.get("dynamic"), f"{prefix}.dynamic")
        interactive = _required_bool(asset.get("interactive"), f"{prefix}.interactive")
        contains_text = _required_bool(asset.get("contains_text"), f"{prefix}.contains_text")
        transparent = _required_bool(asset.get("transparent"), f"{prefix}.transparent")
        if dynamic or interactive or contains_text:
            labels = [
                label
                for label, enabled in (
                    ("dynamic", dynamic),
                    ("interactive", interactive),
                    ("contains_text", contains_text),
                )
                if enabled
            ]
            raise PlanError(f"{prefix} must remain lvgl_native because it is {', '.join(labels)}")
        width = _required_size(asset.get("width"), f"{prefix}.width")
        height = _required_size(asset.get("height"), f"{prefix}.height")
        if width * height > MAX_OUTPUT_PIXELS:
            raise PlanError(f"{prefix} exceeds output pixel budget")
        generation_mode = asset.get("generation_mode")
        if generation_mode not in {"procedural", "web", "external"}:
            raise PlanError(f"{prefix}.generation_mode is invalid")
        search_query = None
        if generation_mode == "web":
            search_query = _required_string(asset.get("search_query"), f"{prefix}.search_query")
            if not allow_web:
                raise PlanError(f"{prefix} requires web image search and network_read capability")
        if generation_mode == "external" and not allow_external:
            raise PlanError(f"{prefix} requires external_asset_generation permission")
        normalized_asset = {
            "id": asset_id,
            "purpose": purpose,
            "reason": reason,
            "fallback": fallback,
            "required": required,
            "width": width,
            "height": height,
            "transparent": transparent,
            "generation_mode": generation_mode,
        }
        if search_query is not None:
            normalized_asset["search_query"] = search_query
        normalized.append(normalized_asset)
    return {
        "schema_version": "mpos-visual-asset-plan-validation-v1",
        "result": "success",
        "render_strategy": strategy,
        "asset_count": len(normalized),
        "assets": normalized,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate an MPOS visual asset plan")
    parser.add_argument("--input", required=True)
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--allow-web", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        plan = payload.get("visual_asset_plan") if isinstance(payload, dict) and "visual_asset_plan" in payload else payload
        result = validate(plan, allow_external=args.allow_external, allow_web=args.allow_web)
    except (PlanError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"result": "failed", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
