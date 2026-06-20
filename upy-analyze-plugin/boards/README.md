# `upy-analyze-plugin/boards`

这个目录保存 `upy-analyze-plugin` 自己使用的板卡元数据。

## 当前策略

- 插件化版 `analyze` 不再只把 `boards/` 当占位目录
- 当前已同步原版 `G:\MicroPython_Skills\upy-analyze\boards` 的板卡 JSON
- 后续插件侧如果需要扩字段，只在本目录继续演进

## 这些板卡数据的用途

主要用于承接 `pre_selected_board` 相关输入契约，包括：

- `id`
- `display_name`
- `mcu`
- `chip_family`
- `firmware_url`

以及后续为：

- 插件端板卡选择器
- `select-hw` 下游衔接
- 本机交互模拟入口

提供统一的板卡基础数据。

## 当前原则

- 原 skill `upy-analyze` 保持不动
- 插件化 skill `upy-analyze-plugin` 维护自己的板卡资产副本
- 如果未来插件版板卡 schema 发生变化，以本目录版本为准
