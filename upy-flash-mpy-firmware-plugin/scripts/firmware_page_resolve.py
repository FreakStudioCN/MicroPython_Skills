#!/usr/bin/env python3
"""Resolve MicroPython latest firmware and installation instructions."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
HREF_RE = re.compile(r"\bhref\s*=\s*([\"'])(?P<href>.*?)\1", re.I | re.S)
CODE_RE = re.compile(r"<pre[^>]*>\s*<code[^>]*>(?P<body>.*?)</code>\s*</pre>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
INSTALL_RE = re.compile(r"(?s)<h2>\s*Installation instructions\s*</h2>(?P<body>.*?)(?:<h2>|</body>|$)", re.I)


def clean_text(value: str) -> str:
    value = TAG_RE.sub(" ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def clean_code(value: str) -> str:
    return html.unescape(TAG_RE.sub("", value)).strip()


def read_page(url: str, html_file: str | None, timeout: int) -> tuple[str, str]:
    if html_file:
        path = Path(html_file)
        return path.read_text(encoding="utf-8", errors="replace"), str(path)

    req = urllib.request.Request(url, headers={"User-Agent": "upy-flash-mpy-firmware-plugin/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace"), url


def normalize_board_url(url: str) -> str:
    return url if url.endswith("/") else url + "/"


def download_slug_from_url(url: str) -> str | None:
    slug = Path(urllib.parse.urlparse(url).path.rstrip("/")).name
    return slug or None


def resolve_board_url_from_index(
    download_index_url: str,
    board_name: str,
    index_html_file: str | None,
    timeout: int,
) -> tuple[str, str, list[str]]:
    index_url = normalize_board_url(download_index_url)
    page, source = read_page(index_url, index_html_file, timeout)
    expected = board_name.strip().upper()
    for match in ANCHOR_RE.finditer(page):
        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        href = html.unescape(href_match.group("href").strip())
        url = urllib.parse.urljoin(index_url, href)
        path_name = Path(urllib.parse.urlparse(url).path.rstrip("/")).name.upper()
        label = clean_text(match.group("body")).upper()
        block = block_text_around(page, match.start(), match.end()).upper()
        if expected in {path_name, label} or expected in block:
            return normalize_board_url(url), source, []
    raise LookupError(f"board {board_name} not found in MicroPython download index")


def install_section(html_text: str) -> str:
    match = INSTALL_RE.search(html_text)
    return match.group("body") if match else html_text


def filename_from_url(url: str) -> str:
    return os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))


def extension_for_family(family: str) -> str | None:
    if family == "esp32":
        return "bin"
    if family == "pico":
        return "uf2"
    return None


def block_text_around(html_text: str, start: int, end: int) -> str:
    lower = html_text.lower()
    for open_tag, close_tag in (("<div", "</div>"), ("<li", "</li>"), ("<tr", "</tr>"), ("<p", "</p>")):
        block_start = lower.rfind(open_tag, 0, start)
        if block_start == -1:
            continue
        block_end = lower.find(close_tag, end)
        if block_end != -1:
            return clean_text(html_text[block_start : block_end + len(close_tag)])
    return clean_text(html_text[max(0, start - 80) : min(len(html_text), end + 160)])


def parse_version_date(text: str) -> tuple[str | None, str | None]:
    version = None
    date = None
    m = re.search(r"\b(v\d+\.\d+(?:\.\d+)?(?:[-.\w]*)?)\b", text)
    if m:
        version = m.group(1)
        version = re.sub(r"\.(?:bin|uf2|dfu|hex|zip|elf|map)$", "", version, flags=re.I)
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if m:
        date = m.group(1)
    return version, date


def candidate_links(html_text: str, board_url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for match in ANCHOR_RE.finditer(html_text):
        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        url = urllib.parse.urljoin(board_url, html.unescape(href_match.group("href").strip()))
        text = clean_text(match.group("body"))
        block = block_text_around(html_text, match.start(), match.end())
        version, date = parse_version_date(" ".join([text, block]))
        path = urllib.parse.urlparse(url).path.lower()
        ext = Path(path).suffix.lower().lstrip(".")
        items.append(
            {
                "url": url,
                "filename": filename_from_url(url),
                "file_type": ext,
                "link_text": text,
                "nearby_text": block,
                "version": version,
                "date": date,
                "is_latest": "latest" in block.lower(),
                "is_preview": "preview" in path or "preview" in block.lower(),
            }
        )
    return items


def choose_latest(items: list[dict[str, Any]], family: str) -> dict[str, Any]:
    ext = extension_for_family(family)
    filtered = []
    for item in items:
        if family == "manual":
            if item["file_type"] in {"bin", "uf2", "dfu", "hex", "zip"}:
                filtered.append(item)
        elif item["file_type"] == ext:
            filtered.append(item)
    latest = [item for item in filtered if item["is_latest"] and not item["is_preview"]]
    if not latest:
        raise LookupError(f"no latest firmware found for family={family}")
    return latest[0]


def code_blocks(html_text: str) -> list[str]:
    return [clean_code(match.group("body")) for match in CODE_RE.finditer(html_text)]


def links_from_html(html_text: str, base_url: str | None = None) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in ANCHOR_RE.finditer(html_text):
        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        label = clean_text(match.group("body"))
        url = html.unescape(href_match.group("href").strip())
        if base_url:
            url = urllib.parse.urljoin(base_url, url)
        if url in seen:
            continue
        seen.add(url)
        links.append({"label": label or url, "url": url})
    return links


def manual_tool_hint(text: str, latest_type: str | None = None) -> str:
    lower = text.lower()
    if "teensy_loader_cli" in lower or "teensy loader" in lower:
        return "teensy-loader"
    if "st-flash" in lower or "st-link" in lower:
        return "st-flash"
    if "dfu-util" in lower or " dfu" in lower or latest_type == "dfu":
        return "dfu-util"
    if "uf2" in lower or "virtual drive" in lower:
        return "uf2-drag-drop"
    if "ftp" in lower or "/flash/sys" in lower:
        return "ftp-copy"
    return "manual"


def manual_commands(blocks: list[str], text: str) -> list[dict[str, Any]]:
    commands: list[str] = []
    for block in blocks:
        if any(token in block for token in ("dfu-util", "st-flash", "teensy_loader_cli", "machine.bootloader()")):
            commands.append(block)
    for match in re.finditer(r"(?im)^\s*(dfu-util|st-flash|teensy_loader_cli|machine\.bootloader\(\)).*$", text):
        commands.append(match.group(0).strip())

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for command in commands:
        command = re.sub(r"\s+", " ", command).strip()
        if not command or command in seen:
            continue
        seen.add(command)
        result.append(
            {
                "command": command,
                "source": "micropython_official",
                "execute_allowed": False,
            }
        )
    return result


def manual_steps(text: str, tool_hint: str, latest_type: str | None) -> list[str]:
    steps = [f"下载页面中标记为 latest 的 {'.' + latest_type if latest_type else '固件'} 文件。"]
    if "machine.bootloader()" in text:
        steps.append("如果设备当前已运行 MicroPython，可在 REPL 执行 machine.bootloader() 进入 bootloader。")
    if re.search(r"\bUSR\b|\bRST\b", text):
        steps.append("也可按官方页面说明使用板载按键进入 bootloader，例如按住 USR、点击 RST 后再松开。")
    elif "BOOTSEL" in text:
        steps.append("按官方页面说明使用 BOOTSEL 或复位按键进入 bootloader。")
    else:
        steps.append("按官方页面说明让开发板进入固件烧录或 bootloader 模式。")

    if tool_hint == "uf2-drag-drop":
        steps.append("把 UF2 固件复制到出现的虚拟磁盘。")
    elif tool_hint == "ftp-copy":
        steps.append("按官方页面说明通过 FTP 复制固件文件到设备指定目录。")
    elif tool_hint in {"dfu-util", "st-flash", "teensy-loader"}:
        steps.append("使用官方页面推荐的工具完成烧录；本 skill 只展示命令，不自动执行。")
    else:
        steps.append("使用官方页面或厂商说明推荐的方法完成烧录。")
    steps.append("设备重启后回到插件窗口点击确认。")
    return steps


def parse_install(html_text: str, family: str, board_url: str | None = None, latest: dict[str, Any] | None = None) -> dict[str, Any]:
    section = install_section(html_text)
    blocks = code_blocks(section)
    links = []
    for match in ANCHOR_RE.finditer(section):
        href_match = HREF_RE.search(match.group("attrs"))
        if not href_match:
            continue
        label = clean_text(match.group("body"))
        url = html.unescape(href_match.group("href").strip())
        if board_url:
            url = urllib.parse.urljoin(board_url, url)
        if "docs." in url or "documentation" in label.lower() or "esptool" in label.lower():
            links.append({"label": label or url, "url": url})

    if family == "esp32":
        erase = [b for b in blocks if "erase_flash" in b or "erase-flash" in b]
        write = [b for b in blocks if "write_flash" in b or "write-flash" in b]
        write_offset = None
        baud = None
        if write:
            tokens = re.split(r"\s+", write[0])
            for index, token in enumerate(tokens):
                if token in {"write_flash", "write-flash"} and index + 1 < len(tokens):
                    write_offset = tokens[index + 1]
                if token == "--baud" and index + 1 < len(tokens):
                    try:
                        baud = int(tokens[index + 1])
                    except ValueError:
                        pass
        return {
            "tool_hint": "esptool.py" if "esptool.py" in section else "esptool",
            "windows_tool_hint": "esptool" if "Windows users" in section else None,
            "docs": [link["url"] for link in links],
            "erase_commands": erase,
            "write_commands": write,
            "write_offset": write_offset,
            "baud": baud or 460800,
            "serial_port_placeholder": "PORTNAME",
            "troubleshooting": [
                clean_text(p)
                for p in re.findall(r"<p>(?P<body>.*?(?:troubleshooting|Troubleshooting).*?)</p>", section, re.I | re.S)
            ],
        }

    if family == "pico":
        return {
            "tool_hint": "uf2-drag-drop",
            "docs": [link["url"] for link in links],
            "steps": [
                "Hold BOOTSEL while connecting USB.",
                "Copy the downloaded UF2 file to the RPI-RP2 drive.",
                "Wait for the board to reboot.",
            ],
        }

    section_text = clean_text(section)
    latest_type = (latest or {}).get("file_type")
    tool_hint = manual_tool_hint(section_text, latest_type)
    return {
        "tool_hint": tool_hint,
        "docs": [link["url"] for link in links],
        "raw_text_excerpt": section_text[:700],
        "steps": manual_steps(section_text, tool_hint, latest_type),
        "commands": manual_commands(blocks, section_text),
        "links": links_from_html(section, board_url),
    }


def write_json(data: dict[str, Any], output: str | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-index-url", default="https://micropython.org/download/")
    parser.add_argument("--board-url")
    parser.add_argument("--board-name", required=True)
    parser.add_argument("--board-family", choices=("esp32", "pico", "manual"), required=True)
    parser.add_argument("--html-file")
    parser.add_argument("--index-html-file")
    parser.add_argument("--out-json", "--output-json", dest="out_json")
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        warnings: list[str] = []
        board_url = normalize_board_url(args.board_url) if args.board_url else None
        index_source = None
        match_method = "firmware_url_slug" if board_url else "download_index"
        if not board_url:
            board_url, index_source, index_warnings = resolve_board_url_from_index(
                args.download_index_url,
                args.board_name,
                args.index_html_file,
                args.timeout,
            )
            warnings.extend(index_warnings)
        download_slug = download_slug_from_url(board_url)
        page, source = read_page(board_url, args.html_file, args.timeout)
        latest = choose_latest(candidate_links(page, board_url), args.board_family)
        result = {
            "status": "success",
            "board_name": args.board_name,
            "download_slug": download_slug,
            "board_url": board_url,
            "download_index_url": args.download_index_url,
            "family": args.board_family,
            "page_source": source,
            "index_source": index_source,
            "resolved": {
                "download_slug": download_slug,
                "board_url": board_url,
                "match_method": match_method,
                "confidence": 1.0,
                "candidate_count": 1,
            },
            "latest": latest,
            "install": parse_install(page, args.board_family, board_url, latest),
            "warnings": warnings,
        }
        write_json(result, args.out_json)
        return 0
    except (OSError, LookupError, urllib.error.URLError, ValueError) as exc:
        result = {
            "status": "failed",
            "board_name": args.board_name,
            "board_url": args.board_url,
            "family": args.board_family,
            "error": {
                "code": "latest_firmware_not_found" if isinstance(exc, LookupError) else "firmware_page_lookup_failed",
                "message": str(exc),
            },
        }
        write_json(result, args.out_json)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
