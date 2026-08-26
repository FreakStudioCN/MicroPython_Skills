#!/usr/bin/env python3
"""Validate actual runtime-image hashes and total bytes before packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


MAX_APP_RUNTIME_BYTES = 1_048_576
MAX_MANIFEST_BYTES = 1_048_576
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BundleError(ValueError):
    pass


def _confined_path(allowed_root, value, name):
    if not isinstance(value, str) or not value:
        raise BundleError(f"{name} must be a non-empty path")
    raw_path = Path(value)
    path = raw_path.resolve(strict=True) if raw_path.is_absolute() else (allowed_root / raw_path).resolve(strict=True)
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise BundleError(f"{name} must stay inside allowed root") from exc
    return path


def validate(payload, allowed_root):
    if not isinstance(payload, dict) or payload.get("schema_version") != "mpos-visual-asset-bundle-v1":
        raise BundleError("unsupported visual asset bundle schema_version")
    budget = payload.get("runtime_byte_budget")
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0 or budget > MAX_APP_RUNTIME_BYTES:
        raise BundleError(f"runtime_byte_budget must be an integer from 1 to {MAX_APP_RUNTIME_BYTES}")
    assets = payload.get("assets")
    if not isinstance(assets, list) or len(assets) > 64:
        raise BundleError("assets must be a list with at most 64 entries")
    actual_runtime_bytes = 0
    normalized = []
    seen = set()
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            raise BundleError(f"{prefix} must be an object")
        path = _confined_path(allowed_root, asset.get("runtime_path"), f"{prefix}.runtime_path")
        if not path.is_file():
            raise BundleError(f"{prefix}.runtime_path must be a file")
        if path in seen:
            raise BundleError(f"duplicate runtime path: {asset.get('runtime_path')}")
        seen.add(path)
        expected_hash = asset.get("runtime_sha256")
        if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
            raise BundleError(f"{prefix}.runtime_sha256 is invalid")
        runtime_bytes = path.stat().st_size
        actual_runtime_bytes += runtime_bytes
        if actual_runtime_bytes > budget:
            raise BundleError(
                "visual assets exceed actual runtime byte budget: "
                f"actual {actual_runtime_bytes}, budget {budget}"
            )
        digest = hashlib.sha256()
        with path.open("rb") as runtime_file:
            while True:
                chunk = runtime_file.read(65_536)
                if not chunk:
                    break
                digest.update(chunk)
        actual_hash = digest.hexdigest()
        if actual_hash != expected_hash:
            raise BundleError(f"{prefix} SHA-256 mismatch")
        normalized.append(
            {
                "runtime_path": str(path.relative_to(allowed_root)),
                "runtime_sha256": actual_hash,
                "runtime_bytes": runtime_bytes,
            }
        )
    return {
        "schema_version": "mpos-visual-asset-bundle-validation-v1",
        "result": "success",
        "runtime_byte_budget": budget,
        "actual_runtime_bytes": actual_runtime_bytes,
        "asset_count": len(normalized),
        "assets": normalized,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate an MPOS visual asset runtime bundle")
    parser.add_argument("--input", required=True)
    parser.add_argument("--allowed-root", required=True)
    args = parser.parse_args()
    try:
        allowed_root = Path(args.allowed_root).resolve(strict=True)
        if not allowed_root.is_dir():
            raise BundleError("allowed root must be a directory")
        input_path = _confined_path(allowed_root, args.input, "input")
        if input_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise BundleError("visual asset bundle manifest exceeds byte budget")
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        result = validate(payload, allowed_root)
    except (BundleError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"result": "failed", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
