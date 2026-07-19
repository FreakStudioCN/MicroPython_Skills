# Official MicroPython Board Source Index

整理批次: 2026-07-17
精简批次: 2026-07-17 raw-assets-condensed

本目录只保留官方板卡资料主索引、整理说明和小型审计报告归档。正式 select-hw 板卡定义仍在上级 `boards/*.json`。

## Active Files

- `MicroPython官方板卡资料源索引.csv`: 223 块 MicroPython 官方板卡的资料源索引。保留官方页、GitHub source、厂商页、板卡图片 URL、pinout URL/source、正式 JSON、firmware、source 文件解析状态、HTML/OCR 摘要和人工复核项。
- `_archive_20260717/official_pending_cleanup_manifest_20260717.json`: 2026-07-17 初次归档清单。
- `_archive_20260717/raw_asset_condense_manifest_20260717.json`: 原始素材精简清单。
- `_archive_20260717/reports_20260717.zip`: HTML 失败清单、截图 OCR 摘要、正式发布报告和最终增强报告。

## Raw Assets

原始 pinout 图片、厂商页面截图、旧 pending JSON 和历史 CSV 备份已不在本目录保留。主 CSV 已保留源 URL、source 路径、OCR 摘要、质量等级和待复核项；正式板卡内容以 `boards/*.json` 为准。

需要重新复核视觉素材时，从 CSV 中的 `板卡图片URL或文件名`、`pinout图片URL或文件名`、`厂商产品页HTML`、`GitHub或source页面` 重新抓取。

## Notes

- `features` 仍以 MicroPython 官方 `board.json.features` 为高层能力线索。
- `onboard_peripherals` 和引脚占用以正式 `boards/*.json` 为准；缺 pin 映射的外设不会形成硬冲突。
- generic target 保留为通用 target 语义，以 MicroPython source 目录为主要依据。
- 后续新增/校验板卡时，优先更新本目录主 CSV，再重新运行官方 source/HTML/pinout 审计和正式 JSON 生成脚本。
