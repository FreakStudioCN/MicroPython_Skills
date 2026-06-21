# select-hw Phase Log

Sample select-hw phase log.

## Runtime Context

- `artifact_root`: `.` (cwd)
- `artifact_root_mode`: `cwd`
- `session_root`: `sessions/022ad742-3269-42e9-ac20-c14f477ecdf2`
- `resource_root`: `<runtime-provided>`

## Step Timeline

| Step ID | Level | Message |
|---------|-------|---------|
| upstream_manifest_loaded | info | 已读取 analyze manifest_content |
| board_matching | info | 正在根据 MCU 偏好和需求匹配板卡 |
| board_definition_loaded | info | 已加载 upy-analyze-plugin/boards/esp32-c3-devkitm.json |
| board_selected | success | 已确认 ESP32-C3-DevKitM-1 |
| firmware_check | info | 正在核验 MicroPython 固件 |
| firmware_ok | success | 固件入口 ESP32_GENERIC_C3 可用 |
| pin_assignment | info | 正在分配 I2C/GPIO/I2S/电源引脚 |
| pin_assignment_draft_ready | info | 引脚方案草稿已生成 |
| pin_assignment_done | success | 引脚分配完成 |
| bom_ready | success | BOM 已生成 |
| manifest_validation | info | 正在运行 select_hw_manifest.py 校验 |

## 资源引用

All paths below are repository-relative:

- `upy-analyze-plugin/boards`
- `upy-select-hw-plugin/scripts/select_hw_manifest.py`
- `upy-project-gen-toolchain-spec/scripts/workflow_time.py`

## 产物

All artifact paths are relative to artifact_root under artifact_root_mode=cwd:

- `sessions/<session_id>/select_hw_draft.json`
- `sessions/<session_id>/select_hw_validated.json`
- `sessions/<session_id>/phase_complete.select_hw.json`
- `sessions/<session_id>/pin_assignment_log.md`
- `sessions/<session_id>/select_hw_phase_log.md`
