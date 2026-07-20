#!/usr/bin/env python3
"""Download firmware resolved by MicroPython page or vendor source resolvers."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def portable_path(path: Path) -> str:
    return path.as_posix()


def artifact_path(path: Path, root: str | None) -> str | None:
    if not root:
        return None
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def file_type_from_name(name: str) -> str | None:
    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or None


def copy_or_download(url: str, dest: Path, timeout: int) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        local_path = urllib.request.url2pathname(parsed.path)
        if len(local_path) >= 3 and local_path[0] in {"/", "\\"} and local_path[2] == ":":
            local_path = local_path[1:]
        src = Path(local_path)
        shutil.copyfile(src, dest)
        return
    req = urllib.request.Request(url, headers={"User-Agent": "upy-flash-mpy-firmware-plugin/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        dest.write_bytes(response.read())


def safe_zip_member(member: str) -> str:
    path = PurePosixPath(member)
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError(f"unsafe archive member path: {member}")
    return path.as_posix()


def choose_archive_member(zf: zipfile.ZipFile, requested: str | None, final_type: str | None) -> str:
    names = [name for name in zf.namelist() if not name.endswith("/")]
    if requested:
        requested = safe_zip_member(requested)
        if requested not in names:
            raise LookupError(f"archive member not found: {requested}")
        return requested
    if final_type:
        matches = [name for name in names if name.lower().endswith("." + final_type.lower())]
        if len(matches) == 1:
            return matches[0]
        if matches:
            simple = [name for name in matches if PurePosixPath(name).name.lower() == f"firmware.{final_type.lower()}"]
            if len(simple) == 1:
                return simple[0]
    raise LookupError("archive member not found; resolved JSON must provide latest.archive_member")


def add_artifact_field(result: dict[str, Any], field: str, path: Path, root: str | None, warnings: list[dict[str, Any]]) -> None:
    rel_path = artifact_path(path, root)
    if not root:
        return
    if rel_path:
        result[field] = rel_path
    else:
        warnings.append(
            {
                "code": "artifact_path_unresolved",
                "message": f"{field} destination is not under artifact_root",
                "severity": "warning",
            }
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--artifact-root")
    parser.add_argument("--output-json", "--out-json", dest="output_json")
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    resolved = json.loads(Path(args.resolved_json).read_text(encoding="utf-8"))
    latest = resolved.get("latest") or {}
    url = latest.get("url")
    filename = latest.get("filename")
    if not url or not filename:
        write_json({"status": "failed", "error": {"code": "latest_firmware_not_found", "message": "resolved JSON lacks latest.url/filename"}}, args.output_json)
        return 2

    out_dir = Path(args.out_dir)
    container_type = latest.get("container_type")
    is_archive = container_type == "zip" or latest.get("file_type") == "zip"
    archive_member = latest.get("archive_member")
    if is_archive and archive_member:
        try:
            archive_member = safe_zip_member(str(archive_member))
        except ValueError as exc:
            write_json({"status": "failed", "error": {"code": "archive_extract_failed", "message": str(exc)}}, args.output_json)
            return 2
    final_file_type = latest.get("extracted_file_type") or (file_type_from_name(str(archive_member)) if archive_member else None)
    final_file_type = final_file_type or (None if is_archive else latest.get("file_type"))
    if is_archive:
        final_filename = latest.get("extracted_filename") or (Path(str(archive_member)).name if archive_member else f"firmware.{final_file_type or 'bin'}")
    else:
        final_filename = filename
    archive_dest = out_dir / filename
    dest = out_dir / final_filename if is_archive else archive_dest
    warnings: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "status": "planned" if args.no_download else "success",
        "firmware_url": url,
        "filename": final_filename,
        "file_type": final_file_type,
        "container_type": container_type,
        "downloaded": False,
        "downloaded_path": portable_path(dest),
    }
    if is_archive:
        result.update(
            {
                "archive_filename": filename,
                "archive_downloaded_path": portable_path(archive_dest),
                "archive_member": archive_member,
            }
        )
        add_artifact_field(result, "archive_artifact_path", archive_dest, args.artifact_root, warnings)
    add_artifact_field(result, "downloaded_artifact_path", dest, args.artifact_root, warnings)
    if warnings:
        result["warnings"] = warnings
    if not args.no_download:
        out_dir.mkdir(parents=True, exist_ok=True)
        copy_or_download(url, archive_dest, args.timeout)
        if is_archive:
            try:
                with zipfile.ZipFile(archive_dest) as zf:
                    member = choose_archive_member(zf, archive_member, final_file_type)
                    result["archive_member"] = member
                    with zf.open(member) as src, dest.open("wb") as out:
                        shutil.copyfileobj(src, out)
            except LookupError as exc:
                write_json(
                    {
                        "status": "failed",
                        "error": {"code": "archive_member_not_found", "message": str(exc)},
                        "archive_downloaded_path": portable_path(archive_dest),
                    },
                    args.output_json,
                )
                return 2
            except (OSError, ValueError, zipfile.BadZipFile) as exc:
                write_json(
                    {
                        "status": "failed",
                        "error": {"code": "archive_extract_failed", "message": str(exc)},
                        "archive_downloaded_path": portable_path(archive_dest),
                    },
                    args.output_json,
                )
                return 2
        result["downloaded"] = True
    write_json(result, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
