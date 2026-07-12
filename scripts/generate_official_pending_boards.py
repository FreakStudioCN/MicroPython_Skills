from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


MICROPYTHON_DOWNLOAD_URL = "https://micropython.org/download/"
USER_AGENT = "Blockless hardware catalog refresh/1.0 (+https://blockless.ai)"
PENDING_SCHEMA = "blockless.micropython.official_board_pending.v1"


class BoardIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.boards: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "a" and "board-card" in classes:
            slug = (attr.get("href") or "").strip().strip("/")
            self._current = {
                "slug": slug,
                "detail_url": urljoin(MICROPYTHON_DOWNLOAD_URL, f"{slug}/"),
            }
            self._field = None
        elif self._current is not None and tag == "div" and "board-product" in classes:
            self._field = "name"
        elif self._current is not None and tag == "div" and "board-vendor" in classes:
            self._field = "vendor"
        elif self._current is not None and tag == "img":
            src = (attr.get("src") or "").strip()
            if src:
                self._current["image_url"] = urljoin(MICROPYTHON_DOWNLOAD_URL, src)

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._field:
            value = data.strip()
            if value:
                self._current[self._field] = value

    def handle_endtag(self, tag: str) -> None:
        if self._current is not None and tag == "div":
            self._field = None
        elif self._current is not None and tag == "a":
            if self._current.get("slug"):
                self.boards.append(self._current)
            self._current = None
            self._field = None


class BoardDetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.name = ""
        self.vendor = ""
        self.features: list[str] = []
        self.source_url = ""
        self.more_info_url = ""
        self.image_url = ""
        self.firmware_links: list[dict[str, str]] = []
        self._capture_h2 = False
        self._current_label = ""
        self._capture_label_text = False
        self._current_link: dict[str, str] | None = None
        self._in_anchor = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "h2" and not self.name:
            self._capture_h2 = True
            return
        if tag == "img" and "hero" in (attr.get("class") or "").split():
            src = (attr.get("src") or "").strip()
            if src:
                self.image_url = urljoin(MICROPYTHON_DOWNLOAD_URL, src)
            return
        if tag == "strong":
            self._capture_label_text = True
            self._current_label = ""
            return
        if tag == "a":
            href = (attr.get("href") or "").strip()
            self._in_anchor = True
            self._current_link = {"href": href, "text": ""}

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._capture_h2 and not self.name:
            self.name = text
        elif self._in_anchor and self._current_link is not None:
            self._current_link["text"] += text
        elif self._capture_label_text:
            self._current_label += text
        elif self._current_label.startswith("Vendor"):
            self.vendor = text
            self._current_label = ""
        elif self._current_label.startswith("Features"):
            self.features = [part.strip() for part in text.split(",") if part.strip()]
            self._current_label = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._capture_h2 = False
        elif tag == "strong":
            self._capture_label_text = False
        elif tag == "a" and self._current_link is not None:
            href = self._current_link["href"]
            text = self._current_link["text"]
            full_url = urljoin(MICROPYTHON_DOWNLOAD_URL, href)
            if self._current_label.startswith("Source on GitHub"):
                self.source_url = full_url
                self._current_label = ""
            elif self._current_label.startswith("More info"):
                self.more_info_url = full_url
                self._current_label = ""
            elif "/resources/firmware/" in href:
                parsed = parse_firmware_text(text)
                if parsed:
                    parsed["url"] = full_url
                    self.firmware_links.append(parsed)
            self._current_link = None
            self._in_anchor = False


def fetch_text(url: str, timeout: int = 30) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_download_index(html: str) -> list[dict[str, Any]]:
    parser = BoardIndexParser()
    parser.feed(html)
    return parser.boards


def parse_board_detail(slug: str, html: str) -> dict[str, Any]:
    parser = BoardDetailParser()
    parser.feed(html)
    releases = sorted(
        (item for item in parser.firmware_links if "preview" not in item["version"]),
        key=lambda item: item["date"],
        reverse=True,
    )
    previews = sorted(
        (item for item in parser.firmware_links if "preview" in item["version"]),
        key=lambda item: item["date"],
        reverse=True,
    )
    return {
        "slug": slug,
        "name": parser.name or slug,
        "vendor": parser.vendor,
        "features": parser.features,
        "detail_url": urljoin(MICROPYTHON_DOWNLOAD_URL, f"{slug}/"),
        "image_url": parser.image_url,
        "source_url": parser.source_url,
        "more_info_url": parser.more_info_url,
        "firmware": {
            "latest_release": releases[0] if releases else None,
            "latest_preview": previews[0] if previews else None,
        },
    }


def parse_firmware_text(text: str) -> dict[str, str] | None:
    match = re.search(r"(v[^\s]+)\s+\((\d{4}-\d{2}-\d{2})\)", text)
    if not match:
        return None
    return {"version": match.group(1), "date": match.group(2)}


def port_from_board(board: dict[str, Any]) -> str:
    source = str(board.get("source_url") or "")
    match = re.search(r"/ports/([^/]+)/boards/", source)
    if match:
        return match.group(1)
    slug = str(board.get("slug") or "").upper()
    if slug.startswith("ESP32"):
        return "esp32"
    if slug.startswith(("RPI_", "PICO", "WAVESHARE_RP", "ADAFRUIT_FEATHER_RP", "SPARKFUN_PROMICRO_RP")):
        return "rp2"
    if slug.startswith(("PYB", "STM32", "VCC_GND", "WEACT")):
        return "stm32"
    return ""


def mcu_from_board(board: dict[str, Any], port: str) -> str:
    slug = str(board.get("slug") or "").upper()
    source = str(board.get("source_url") or "").lower()
    if "esp32c3" in source or "_C3" in slug:
        return "esp32c3"
    if "esp32s3" in source or "_S3" in slug:
        return "esp32s3"
    if "esp32s2" in source or "_S2" in slug:
        return "esp32s2"
    if "esp32c6" in source or "_C6" in slug:
        return "esp32c6"
    if "rp2350" in source or "RP2350" in slug:
        return "rp2350"
    if "rp2040" in source or "PICO" in slug or "RP2040" in slug:
        return "rp2040"
    if slug == "PYBD_SF2":
        return "stm32f722"
    return port


def family_from_mcu(mcu: str, port: str) -> str:
    if mcu in {"esp32", "esp32s2", "esp32s3", "esp32c3", "esp32c6", "esp8266", "rp2350"}:
        return mcu
    if mcu == "rp2040":
        return "rp2"
    return port or mcu


def proposed_skill_id(slug: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-")


def safe_filename(slug: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", slug).strip("_") or "board"


def load_cached_boards(path: Path) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("fetched_at") or ""), list(payload.get("boards") or []), []


def fetch_one_board(entry: dict[str, Any], fetched_at: str, timeout: int) -> dict[str, Any]:
    slug = entry["slug"]
    detail = parse_board_detail(slug, fetch_text(entry["detail_url"], timeout=timeout))
    board = {**entry, **{k: v for k, v in detail.items() if v not in ("", [], None)}}
    board["fetched_at"] = fetched_at
    return board


def fetch_boards(
    limit: int | None,
    sleep_seconds: float,
    *,
    workers: int,
    timeout: int,
    fallback_cache: Path | None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    fetched_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    entries = parse_download_index(fetch_text(MICROPYTHON_DOWNLOAD_URL, timeout=timeout))
    if limit is not None:
        entries = entries[:limit]
    boards: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    fallback_by_slug: dict[str, dict[str, Any]] = {}
    if fallback_cache and fallback_cache.is_file():
        _, fallback_boards, _ = load_cached_boards(fallback_cache)
        fallback_by_slug = {str(board.get("slug")): board for board in fallback_boards if board.get("slug")}

    workers = max(1, workers)
    if workers == 1:
        for entry in entries:
            slug = entry["slug"]
            try:
                boards.append(fetch_one_board(entry, fetched_at, timeout))
            except Exception as exc:  # noqa: BLE001
                fallback = fallback_by_slug.get(slug)
                if fallback:
                    fallback = dict(fallback)
                    fallback["fallback_from_cache"] = True
                    boards.append(fallback)
                errors.append({"slug": slug, "detail_url": entry.get("detail_url"), "error": str(exc), "used_fallback": bool(fallback)})
            if sleep_seconds:
                time.sleep(sleep_seconds)
    else:
        by_slug: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(fetch_one_board, entry, fetched_at, timeout): entry for entry in entries}
            for future in as_completed(future_map):
                entry = future_map[future]
                slug = entry["slug"]
                try:
                    by_slug[slug] = future.result()
                except Exception as exc:  # noqa: BLE001
                    fallback = fallback_by_slug.get(slug)
                    if fallback:
                        fallback = dict(fallback)
                        fallback["fallback_from_cache"] = True
                        by_slug[slug] = fallback
                    errors.append({"slug": slug, "detail_url": entry.get("detail_url"), "error": str(exc), "used_fallback": bool(fallback)})
        boards = [by_slug[entry["slug"]] for entry in entries if entry["slug"] in by_slug]
    return fetched_at, boards, errors


def pending_payload(board: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    slug = str(board.get("slug") or "")
    port = port_from_board(board)
    mcu = mcu_from_board(board, port)
    family = family_from_mcu(mcu, port)
    features = board.get("features") if isinstance(board.get("features"), list) else []
    firmware = board.get("firmware") if isinstance(board.get("firmware"), dict) else {}
    return {
        "schema": PENDING_SCHEMA,
        "status": "needs_human_verification",
        "select_hw_ready": False,
        "support_status": "official_firmware_only",
        "promotion_target": "upy-analyze-plugin/boards/<skill_board_id>.json only after pin-layout review",
        "official_board_slug": slug,
        "proposed_skill_board_id": proposed_skill_id(slug),
        "display_name": board.get("name") or slug,
        "vendor": board.get("vendor") or "",
        "port": port,
        "mcu_inferred": mcu,
        "chip_family_inferred": family,
        "features": features,
        "firmware": {
            "url": board.get("detail_url") or urljoin(MICROPYTHON_DOWNLOAD_URL, f"{slug}/"),
            "port": port,
            "board_name": slug,
            "latest_release": firmware.get("latest_release"),
            "latest_preview": firmware.get("latest_preview"),
        },
        "source": {
            "index_url": MICROPYTHON_DOWNLOAD_URL,
            "detail_url": board.get("detail_url") or urljoin(MICROPYTHON_DOWNLOAD_URL, f"{slug}/"),
            "source_url": board.get("source_url") or "",
            "more_info_url": board.get("more_info_url") or "",
            "image_url": board.get("image_url") or "",
            "fetched_at": board.get("fetched_at") or fetched_at,
        },
        "known_missing_for_select_hw": [
            "physical board variant confirmation",
            "pinout diagram or schematic",
            "pin_layout.default_bus_pins",
            "pin_layout.restricted_gpio",
            "pin_layout.pin_options when applicable",
            "onboard_peripherals and occupied pins",
            "board power/logic voltage notes",
        ],
        "verification": {
            "image_matches_physical_board": False,
            "official_slug_maps_to_specific_board": False,
            "pinout_source_verified": False,
            "schematic_or_vendor_doc_verified": False,
            "default_bus_pins_verified": False,
            "restricted_gpio_verified": False,
            "onboard_peripherals_verified": False,
            "safe_to_promote_to_skill_board_definition": False,
        },
        "notes": [
            "This file is an official MicroPython inventory record, not a select-hw board definition.",
            "Do not copy this file to the top-level boards directory as a supported board until verification is complete.",
        ],
    }


def write_outputs(
    boards: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    fetched_at: str,
    output_dir: Path,
    course_md: Path | None,
    used_cache: Path | None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("*.json"):
        try:
            path.unlink()
        except PermissionError:
            # A viewer/indexer may briefly hold a generated JSON. Keep it; the
            # regenerated index remains the authoritative list for this run.
            pass
    generated: list[dict[str, Any]] = []
    for board in boards:
        slug = str(board.get("slug") or "")
        if not slug:
            continue
        payload = pending_payload(board, fetched_at)
        filename = f"{safe_filename(slug)}.json"
        safe_write_text(output_dir / filename, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        generated.append(
            {
                "official_board_slug": slug,
                "display_name": payload["display_name"],
                "vendor": payload["vendor"],
                "port": payload["port"],
                "mcu_inferred": payload["mcu_inferred"],
                "chip_family_inferred": payload["chip_family_inferred"],
                "file": filename,
                "detail_url": payload["source"]["detail_url"],
                "image_url": payload["source"]["image_url"],
            }
        )
    manifest = {
        "schema": "blockless.micropython.official_pending_manifest.v1",
        "source_url": MICROPYTHON_DOWNLOAD_URL,
        "fetched_at": fetched_at,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_cache": str(used_cache) if used_cache else None,
        "board_count": len(generated),
        "error_count": len(errors),
        "errors": errors,
        "output_dir": str(output_dir),
        "boards": generated,
        "counts_by_port": dict(sorted(Counter(item["port"] or "unknown" for item in generated).items())),
        "counts_by_vendor": dict(sorted(Counter(item["vendor"] or "unknown" for item in generated).items())),
    }
    raw_payload = {
        "source": MICROPYTHON_DOWNLOAD_URL,
        "fetched_at": fetched_at,
        "board_count": len(boards),
        "boards": boards,
        "errors": errors,
    }
    safe_write_text(output_dir / "micropython_boards.current.json", json.dumps(raw_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    safe_write_text(output_dir / "index.json", json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    safe_write_text(output_dir / "README.md", render_pending_readme(manifest))
    if course_md:
        course_md.parent.mkdir(parents=True, exist_ok=True)
        course_csv = course_md.with_name("MicroPython官方板卡资料收集Excel模板-2026-07-12.csv")
        manifest["course_csv"] = str(course_csv)
        safe_write_text(course_csv, render_collection_csv(manifest), encoding="utf-8-sig")
        safe_write_text(course_md, render_course_md(manifest))
    return manifest


def safe_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    for attempt in range(4):
        try:
            path.write_text(content, encoding=encoding)
            return
        except PermissionError:
            if attempt == 3:
                fallback = path.with_name(f"{path.name}.new")
                fallback.write_text(content, encoding=encoding)
                return
            time.sleep(0.25)


def render_pending_readme(manifest: dict[str, Any]) -> str:
    return f"""# Official MicroPython Pending Board Records

Generated from {MICROPYTHON_DOWNLOAD_URL}

- Fetched at: {manifest["fetched_at"]}
- Board count: {manifest["board_count"]}
- Status: pending human verification

Files in this directory are not select-hw board definitions. They intentionally use
`schema={PENDING_SCHEMA}` and `select_hw_ready=false`. Keep verified board definitions
in the parent `boards/*.json` directory only after pin layout review is complete.
"""


def render_course_md(manifest: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# MicroPython 官方板卡待核验资料清单")
    lines.append("")
    lines.append(f"日期：{datetime.now(UTC).date().isoformat()}")
    lines.append("")
    lines.append("## 当前已生成内容")
    lines.append("")
    lines.append(f"- 官方来源：{MICROPYTHON_DOWNLOAD_URL}")
    lines.append(f"- 官方数据抓取时间：`{manifest['fetched_at']}`")
    lines.append(f"- 待核验 JSON 目录：`{manifest['output_dir']}`")
    lines.append(f"- 已生成待核验板卡数：`{manifest['board_count']}`")
    lines.append(f"- 抓取错误数：`{manifest['error_count']}`")
    if manifest.get("source_cache"):
        lines.append(f"- 使用缓存文件：`{manifest['source_cache']}`")
    lines.append(f"- 原始官方缓存快照：`{manifest['output_dir']}\\micropython_boards.current.json`")
    if manifest.get("course_csv"):
        lines.append(f"- Excel 收集模板：`{manifest['course_csv']}`")
    lines.append("")
    lines.append("这些 JSON 只是官方 MicroPython inventory，不是可直接给 select-hw 分配引脚的正式板卡定义。")
    lines.append("正式可用的板卡仍必须放在 `G:\\MicroPython_Skills\\upy-analyze-plugin\\boards\\<skill_board_id>.json` 顶层，并且要有真实 `pin_layout`。")
    lines.append("")
    lines.append("## 给新手的目标")
    lines.append("")
    lines.append("这项工作不是让你直接写代码，也不是让你判断硬件一定正确。")
    lines.append("你的任务是把每块官方板卡的资料收集齐，填进 Excel 表格，并把网页、PDF、图片链接或文件发回来。")
    lines.append("我会根据这些资料做二次核验，再决定哪些板卡可以晋升为正式 `pin_layout`。")
    lines.append("")
    lines.append("## 第一步：先建一个 Excel 表格")
    lines.append("")
    lines.append("已经生成了一个 CSV 模板，可以直接用 Excel 打开：")
    lines.append("")
    lines.append("```text")
    lines.append(str(manifest.get("course_csv") or "MicroPython官方板卡资料收集Excel模板-2026-07-12.csv"))
    lines.append("```")
    lines.append("")
    lines.append("如果你自己新建 Excel，表头按下面这些列来：")
    lines.append("")
    lines.append("| 列名 | 怎么填 |")
    lines.append("| --- | --- |")
    lines.append("| official_slug | 不要改，来自 MicroPython 官方，例如 `ESP32_GENERIC_S3` |")
    lines.append("| display_name | 不要改，板卡显示名 |")
    lines.append("| vendor | 不要改，厂商名 |")
    lines.append("| port | 不要改，例如 `esp32`、`rp2`、`stm32` |")
    lines.append("| pending_json | 不要改，对应 `_official_pending` 里的 JSON 文件 |")
    lines.append("| 收集状态 | 填：未开始 / 已找到官网 / 有 pin 图 / 有原理图 / 可初审 / 资料不足 |")
    lines.append("| 具体板卡型号 | 如果官方 slug 是 generic，一定要写具体型号，例如 ESP32-S3 DevKitC-1 |")
    lines.append("| 官方 MicroPython 页面 | 可以直接复制 `detail_url` |")
    lines.append("| 厂商产品页 HTML | 厂商官网产品页、资料页、购买页 URL |")
    lines.append("| GitHub/source 页面 | MicroPython source 或厂商资料仓库 URL |")
    lines.append("| 板卡图片 URL/文件名 | 官方板卡图或实物正反面图 |")
    lines.append("| pinout 图片 URL/文件名 | 最重要，必须能看清 GPIO 标号 |")
    lines.append("| schematic PDF URL/文件名 | 原理图，有就填，没有先空着 |")
    lines.append("| datasheet/hardware PDF | 硬件手册、用户手册、Getting Started 文档 |")
    lines.append("| 默认 I2C | 例如 `SDA=GPIO5, SCL=GPIO6`，不知道就空着 |")
    lines.append("| 默认 SPI | 例如 `MOSI=..., MISO=..., SCK=..., CS=...` |")
    lines.append("| 默认 UART | 例如 `TX=..., RX=...` |")
    lines.append("| 禁用/慎用 GPIO | 启动脚、flash/PSRAM、USB、JTAG、输入专用脚等 |")
    lines.append("| 板载外设占用 | LED、Button、RGB、屏幕、SD 卡、蜂鸣器等占用哪些脚 |")
    lines.append("| 电压说明 | 3.3V/5V、VBUS、电池、电流限制 |")
    lines.append("| 是否 generic target | 是 / 否 / 不确定 |")
    lines.append("| 备注 | 不确定的地方直接写，不要猜 |")
    lines.append("")
    lines.append("## 第二步：每块板怎么收集资料")
    lines.append("")
    lines.append("按这个顺序做，不要跳步：")
    lines.append("")
    lines.append("1. 打开 `_official_pending/<official_slug>.json`，先看里面的 `source.detail_url`、`source.source_url`、`source.more_info_url`、`source.image_url`。")
    lines.append("2. 把 `source.detail_url` 填到 Excel 的“官方 MicroPython 页面”。")
    lines.append("3. 打开 `source.more_info_url`。如果能打开厂商产品页，就填到“厂商产品页 HTML”。")
    lines.append("4. 打开 `source.source_url`。如果是 GitHub board 目录，就填到“GitHub/source 页面”。")
    lines.append("5. 在厂商页面里找 `pinout`、`schematic`、`hardware`、`datasheet`、`user manual`、`getting started` 这些字样。")
    lines.append("6. 找到 pinout 图片后，把图片 URL 填进 Excel；如果是下载到本地的图片，就把文件名写进去。")
    lines.append("7. 找到 schematic 或 hardware PDF 后，把 URL 或文件名填进 Excel。")
    lines.append("8. 如果页面明确写了默认 I2C/SPI/UART，就填；没有明确写就空着。")
    lines.append("9. 如果看到 boot、strapping、reserved、flash、PSRAM、USB、JTAG、NC、input only 这些说明，填到“禁用/慎用 GPIO”。")
    lines.append("10. 如果不确定某个引脚能不能用，不要自己推断，在备注里写“不确定”。")
    lines.append("")
    lines.append("## 第三步：发给我什么资料")
    lines.append("")
    lines.append("推荐发一个资料包，里面至少包含：")
    lines.append("")
    lines.append("```text")
    lines.append("MicroPython官方板卡资料收集Excel模板-2026-07-12.xlsx 或 .csv")
    lines.append("boards资料/")
    lines.append("  ESP32_GENERIC_S3/")
    lines.append("    product-page.html 或 产品页URL.txt")
    lines.append("    pinout.png / pinout.jpg / pinout.pdf")
    lines.append("    schematic.pdf")
    lines.append("    front.jpg")
    lines.append("    back.jpg")
    lines.append("    notes.txt")
    lines.append("  RPI_PICO_W/")
    lines.append("    ...")
    lines.append("```")
    lines.append("")
    lines.append("如果你不方便打包文件，也可以只给 Excel + URL。只要 URL 是公开可访问的，我可以继续核验。")
    lines.append("")
    lines.append("## HTML 页面 + pin 图片算不算初步可用？")
    lines.append("")
    lines.append("算，但只能算“初步资料可用”，不能直接算“正式 pin layout 可用”。")
    lines.append("")
    lines.append("| 等级 | 需要什么资料 | 可以做什么 | 不能做什么 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append("| Level 0：官方 inventory | MicroPython 官方页面 | 证明这块板在官方固件列表里 | 不能分配 GPIO |")
    lines.append("| Level 1：初步资料可用 | 官方页面 + 厂商 HTML 页面 + pinout 图片 | 我可以开始整理草稿、判断是否是具体物理板 | 不能标成 `builtin_pin_layout` |")
    lines.append("| Level 2：可生成草稿 JSON | Level 1 + 默认总线脚 + 禁用/慎用脚资料 | 我可以生成待审核的 board definition 草稿 | 还不能直接进入正式自动接线 |")
    lines.append("| Level 3：正式可用 | Level 2 + schematic/硬件手册 + 板载外设占用核验 + 测试通过 | 可以晋升正式 `boards/<skill_board_id>.json` | 无 |")
    lines.append("")
    lines.append("所以，如果你能给我“板卡相关 HTML 页面 + pinout 图片”，这对第一轮非常有用，已经够做初步版本的资料包。")
    lines.append("但要让系统自动分配 GPIO，仍然需要继续核验禁用脚、板载外设占用和默认总线脚。")
    lines.append("")
    lines.append("## generic firmware target 要特别小心")
    lines.append("")
    lines.append("下面这类官方 slug 常常不是一块具体板，而是通用固件目标：")
    lines.append("")
    lines.append("```text")
    lines.append("ESP32_GENERIC")
    lines.append("ESP32_GENERIC_S2")
    lines.append("ESP32_GENERIC_S3")
    lines.append("ESP32_GENERIC_C3")
    lines.append("ESP32_GENERIC_C6")
    lines.append("ESP8266_GENERIC")
    lines.append("SAMD_GENERIC_D21X18")
    lines.append("SAMD_GENERIC_D51X19")
    lines.append("SAMD_GENERIC_D51X20")
    lines.append("```")
    lines.append("")
    lines.append("这种情况下，Excel 里必须填“具体板卡型号”。")
    lines.append("例如 `ESP32_GENERIC_S3` 不能直接等于所有 ESP32-S3 板；你需要明确是 `ESP32-S3 DevKitC-1`、`Waveshare ESP32-S3-Pico`，还是别的具体板。")
    lines.append("")
    lines.append("## 小白执行示例")
    lines.append("")
    lines.append("以 `ESP32_GENERIC_S3` 为例：")
    lines.append("")
    lines.append("1. 打开 `_official_pending/ESP32_GENERIC_S3.json`。")
    lines.append("2. 复制 `source.detail_url` 到 Excel。")
    lines.append("3. 打开 `source.more_info_url`，如果只是 Espressif 模块页面，备注写“generic，不是具体开发板”。")
    lines.append("4. 找一个具体板，例如 `ESP32-S3 DevKitC-1` 的官方产品页。")
    lines.append("5. 找 `ESP32-S3 DevKitC-1 pinout` 图片或 PDF，填到 pinout 列。")
    lines.append("6. 找 schematic PDF，填到 schematic 列。")
    lines.append("7. 如果只找到 pinout，没有 schematic，收集状态写“有 pin 图”，不要写“可初审”。")
    lines.append("8. 如果 pinout + schematic + 禁用脚说明都有，收集状态写“可初审”。")
    lines.append("")
    lines.append("## 原始资料要求")
    lines.append("")
    lines.append("每块板请尽量提供下面资料；可以是 PDF、图片、网页链接、商品页、GitHub 链接或实物照片。")
    lines.append("")
    lines.append("1. 板卡正反面高清图片，最好能看清丝印和 GPIO 标号。")
    lines.append("2. 官方 pinout 图或厂商引脚图。")
    lines.append("3. 原理图 schematic PDF，或厂商 hardware design 文件。")
    lines.append("4. 厂商产品页、购买页、资料页，用于确认这是不是一个具体物理板，而不是 generic firmware target。")
    lines.append("5. 默认 I2C/SPI/UART/I2S 推荐引脚。")
    lines.append("6. 禁用/慎用 GPIO：启动脚、flash/PSRAM 占用脚、USB/JTAG/晶振/板载外设占用脚、输入专用脚、ADC/WiFi 冲突脚。")
    lines.append("7. 板载外设清单：LED、RGB LED、按钮、屏幕、SD 卡、传感器、蜂鸣器、电池管理、USB-UART 芯片等，以及它们占用的 GPIO。")
    lines.append("8. 电压和供电说明：逻辑电平、5V/3V3 引脚、电流限制、电池接口。")
    lines.append("9. 如果官方 slug 对应多个变体，请说明你要支持哪一个具体型号和内存版本。")
    lines.append("10. 如果你已经有实物，请提供板卡照片和你确认过的可用 GPIO。")
    lines.append("")
    lines.append("## 核验通过后我会做什么")
    lines.append("")
    lines.append("核验通过的板卡才会从 `_official_pending` 晋升为正式 skill board definition：")
    lines.append("")
    lines.append("```text")
    lines.append("G:\\MicroPython_Skills\\upy-analyze-plugin\\boards\\<skill_board_id>.json")
    lines.append("```")
    lines.append("")
    lines.append("正式 JSON 必须补齐：")
    lines.append("")
    lines.append("```text")
    lines.append("id")
    lines.append("display_name")
    lines.append("mcu")
    lines.append("chip_family")
    lines.append("firmware.url / firmware.port / firmware.board_name")
    lines.append("specs")
    lines.append("onboard_peripherals")
    lines.append("pin_layout.default_bus_pins")
    lines.append("pin_layout.restricted_gpio")
    lines.append("pin_layout.pin_options")
    lines.append("```")
    lines.append("")
    lines.append("如果是官方 MicroPython board 还要同步 backend mapping：")
    lines.append("")
    lines.append("```text")
    lines.append("official_board_slug -> local_board_id / skill_board_id / chip_family")
    lines.append("```")
    lines.append("")
    lines.append("## 特别注意")
    lines.append("")
    lines.append("- `ESP32_GENERIC`、`ESP32_GENERIC_S3`、`ESP32_GENERIC_C3` 这类名字经常是通用 firmware target，不一定等于某一块具体开发板。需要你确认要支持的具体板型。")
    lines.append("- 没有真实 pinout 的板卡只能保持 `official_firmware_only`，不能标成 `builtin_pin_layout`。")
    lines.append("- `_official_pending` 里的 JSON 不应该直接复制到顶层 `boards/*.json`。")
    lines.append("- 新 chip_family，例如 `rp2350`、`stm32`、`esp32c6`，还要补 `matching-rules.json`。")
    lines.append("")
    lines.append("## 端口分布")
    lines.append("")
    lines.append("| port | count |")
    lines.append("| --- | ---: |")
    for port, count in manifest["counts_by_port"].items():
        lines.append(f"| `{port}` | {count} |")
    lines.append("")
    lines.append("## 待核验板卡清单")
    lines.append("")
    lines.append("| official slug | display name | vendor | port | inferred mcu | pending JSON |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in manifest["boards"]:
        lines.append(
            f"| `{item['official_board_slug']}` | {escape_md(item['display_name'])} | "
            f"{escape_md(item['vendor'])} | `{item['port'] or 'unknown'}` | `{item['mcu_inferred'] or 'unknown'}` | "
            f"`_official_pending/{item['file']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def escape_md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def render_collection_csv(manifest: dict[str, Any]) -> str:
    output = StringIO()
    fieldnames = [
        "official_slug",
        "display_name",
        "vendor",
        "port",
        "inferred_mcu",
        "pending_json",
        "收集状态",
        "具体板卡型号",
        "官方MicroPython页面",
        "厂商产品页HTML",
        "GitHub或source页面",
        "板卡图片URL或文件名",
        "pinout图片URL或文件名",
        "schematic_PDF_URL或文件名",
        "datasheet或hardware_PDF",
        "默认I2C",
        "默认SPI",
        "默认UART",
        "禁用或慎用GPIO",
        "板载外设占用",
        "电压说明",
        "是否generic_target",
        "备注",
        "收集人",
        "最后更新时间",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for item in manifest["boards"]:
        writer.writerow(
            {
                "official_slug": item["official_board_slug"],
                "display_name": item["display_name"],
                "vendor": item["vendor"],
                "port": item["port"],
                "inferred_mcu": item["mcu_inferred"],
                "pending_json": f"_official_pending/{item['file']}",
                "收集状态": "未开始",
                "具体板卡型号": "",
                "官方MicroPython页面": item["detail_url"],
                "厂商产品页HTML": "",
                "GitHub或source页面": "",
                "板卡图片URL或文件名": item["image_url"],
                "pinout图片URL或文件名": "",
                "schematic_PDF_URL或文件名": "",
                "datasheet或hardware_PDF": "",
                "默认I2C": "",
                "默认SPI": "",
                "默认UART": "",
                "禁用或慎用GPIO": "",
                "板载外设占用": "",
                "电压说明": "",
                "是否generic_target": "不确定",
                "备注": "",
                "收集人": "",
                "最后更新时间": "",
            }
        )
    return output.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-cache", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("upy-analyze-plugin/boards/_official_pending"))
    parser.add_argument("--course-md", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sleep", type=float, default=0.02)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--fallback-cache", type=Path)
    args = parser.parse_args()

    used_cache = args.from_cache
    if args.from_cache:
        fetched_at, boards, errors = load_cached_boards(args.from_cache)
    else:
        fetched_at, boards, errors = fetch_boards(
            args.limit,
            args.sleep,
            workers=args.workers,
            timeout=args.timeout,
            fallback_cache=args.fallback_cache,
        )

    if args.limit is not None:
        boards = boards[: args.limit]
    manifest = write_outputs(boards, errors, fetched_at, args.output_dir, args.course_md, used_cache)
    print(json.dumps({k: manifest[k] for k in ("fetched_at", "board_count", "error_count", "output_dir")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
