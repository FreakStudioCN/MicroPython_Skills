#!/usr/bin/env python3
"""Resolve vendor firmware sources declared by board JSON."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TRUSTED_VENDOR_DIRECT_HOSTS = {
    "docs.w5500.com",
    "wiznet.io",
    "github.com",
    "github-releases.githubusercontent.com",
    "objects.githubusercontent.com",
}


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_json_url(url: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "upy-flash-mpy-firmware-plugin/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset, errors="replace"))


def filename_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return Path(urllib.parse.unquote(parsed.path)).name


def file_type_from_name(name: str) -> str | None:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or None


def family_from_board(board: dict[str, Any], firmware: dict[str, Any]) -> str:
    board_name = str(firmware.get("board_name") or "").upper()
    port = str(firmware.get("port") or "").lower()
    chip_family = str(board.get("chip_family") or "").lower()
    if board_name.startswith("ESP32_") or port == "esp32" or chip_family.startswith("esp32"):
        return "esp32"
    if port == "rp2" or board_name.startswith("RPI_PICO") or chip_family in {"rp2", "rp2040", "rp2350"}:
        return "pico"
    return "manual"


def install_for_latest(family: str, latest: dict[str, Any], flash_method: str | None) -> dict[str, Any]:
    final_type = latest.get("extracted_file_type") or latest.get("file_type")
    if family == "pico" and final_type == "uf2":
        return {
            "tool_hint": "uf2-drag-drop",
            "steps": [
                "Hold BOOTSEL while connecting USB.",
                "Copy the extracted firmware.uf2 file to the RPI-RP2 drive.",
                "Wait for the board to reboot.",
            ],
        }
    if flash_method == "wizlink-drag-drop":
        return {
            "tool_hint": "wizlink-drag-drop",
            "steps": [
                "Connect the W55MH32L-EVB and wait for the WIZLINK drive.",
                "Copy the downloaded .hex firmware to WIZLINK.",
                "Wait for flashing to finish and the board to reboot.",
            ],
        }
    return {
        "tool_hint": flash_method or "manual",
        "steps": [
            "Download the resolved firmware file.",
            "Follow the vendor board documentation to flash the firmware.",
            "Return to the plugin and confirm when the board has rebooted.",
        ],
    }


def github_release_url(repo: str, release_tag: str | None) -> str:
    if release_tag and release_tag != "latest":
        return f"https://api.github.com/repos/{repo}/releases/tags/{release_tag}"
    return f"https://api.github.com/repos/{repo}/releases/latest"


def select_asset(assets: list[Any], pattern: str | None, board_name: str) -> dict[str, Any] | None:
    candidates = [asset for asset in assets if isinstance(asset, dict) and asset.get("name")]
    if pattern:
        for asset in candidates:
            if fnmatch.fnmatchcase(str(asset["name"]), pattern):
                return asset
    compact_board = board_name.replace("-", "_").upper()
    for asset in candidates:
        name = str(asset["name"])
        if compact_board in name.upper() and name.lower().endswith(".zip"):
            return asset
    return None


def resolve_github_release_zip(
    board: dict[str, Any],
    firmware: dict[str, Any],
    *,
    release_json_file: str | None,
    timeout: int,
) -> dict[str, Any]:
    repo = firmware.get("repo")
    if not isinstance(repo, str) or "/" not in repo:
        raise ValueError("firmware.repo is required for github_release_zip")
    release_tag = firmware.get("release_tag")
    release_url = github_release_url(repo, str(release_tag) if release_tag else None)
    release = load_json(release_json_file) if release_json_file else read_json_url(release_url, timeout)
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("GitHub release JSON lacks assets[]")
    board_name = str(firmware.get("board_name") or board.get("id") or "")
    pattern = firmware.get("asset_pattern")
    asset = select_asset(assets, str(pattern) if pattern else None, board_name)
    if asset is None:
        raise LookupError(f"firmware asset not found for pattern={pattern!r}")
    download_url = asset.get("browser_download_url")
    if not isinstance(download_url, str) or not download_url:
        raise ValueError("selected GitHub release asset lacks browser_download_url")
    filename = str(asset["name"])
    archive_member = firmware.get("archive_member")
    latest = {
        "url": download_url,
        "filename": filename,
        "file_type": file_type_from_name(filename),
        "container_type": firmware.get("container_type") or "zip",
        "archive_member": archive_member,
        "extracted_filename": Path(str(archive_member)).name if archive_member else None,
        "extracted_file_type": firmware.get("file_type"),
        "version": release.get("tag_name") or release_tag,
        "date": str(release.get("published_at") or "")[:10] or None,
    }
    return {
        "status": "success",
        "board_id": board.get("id"),
        "board_name": firmware.get("board_name"),
        "display_name": board.get("display_name"),
        "family": family_from_board(board, firmware),
        "source": "github_release_zip",
        "board_url": firmware.get("url") or f"https://github.com/{repo}/releases",
        "release_api_url": release_url,
        "release_tag": latest["version"],
        "latest": latest,
        "install": install_for_latest(family_from_board(board, firmware), latest, firmware.get("flash_method")),
        "warnings": [],
    }


def require_trusted_vendor_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if parsed.scheme != "https" or host not in TRUSTED_VENDOR_DIRECT_HOSTS:
        raise ValueError(f"untrusted vendor firmware URL: {url}")


def resolve_vendor_direct(board: dict[str, Any], firmware: dict[str, Any]) -> dict[str, Any]:
    url = firmware.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("firmware.url is required for vendor_direct")
    require_trusted_vendor_url(url)
    filename = filename_from_url(url)
    if not filename:
        raise ValueError("vendor firmware URL does not contain a filename")
    latest = {
        "url": url,
        "filename": filename,
        "file_type": firmware.get("file_type") or file_type_from_name(filename),
        "version": firmware.get("latest_version"),
        "date": ((firmware.get("latest_release") or {}).get("date") if isinstance(firmware.get("latest_release"), dict) else None),
    }
    return {
        "status": "success",
        "board_id": board.get("id"),
        "board_name": firmware.get("board_name"),
        "display_name": board.get("display_name"),
        "family": family_from_board(board, firmware),
        "source": "vendor_direct",
        "board_url": url,
        "latest": latest,
        "install": install_for_latest(family_from_board(board, firmware), latest, firmware.get("flash_method")),
        "warnings": [],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board-json", required=True)
    parser.add_argument("--release-json-file")
    parser.add_argument("--out-json", "--output-json", dest="out_json")
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    try:
        board = load_json(args.board_json)
        firmware = board.get("firmware") if isinstance(board.get("firmware"), dict) else {}
        source = firmware.get("source") or "micropython_latest"
        if source == "github_release_zip":
            result = resolve_github_release_zip(
                board,
                firmware,
                release_json_file=args.release_json_file,
                timeout=args.timeout,
            )
        elif source == "vendor_direct":
            result = resolve_vendor_direct(board, firmware)
        else:
            raise ValueError(f"unsupported firmware source: {source}")
        write_json(result, args.out_json)
        return 0
    except (OSError, LookupError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        message = str(exc)
        if isinstance(exc, LookupError):
            code = "firmware_asset_not_found"
        elif "untrusted vendor firmware URL" in message:
            code = "vendor_firmware_url_untrusted"
        elif "unsupported firmware source" in message:
            code = "unsupported_firmware_source"
        elif isinstance(exc, urllib.error.URLError):
            code = "github_release_lookup_failed"
        else:
            code = "firmware_source_resolve_failed"
        write_json({"status": "failed", "error": {"code": code, "message": message}}, args.out_json)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
