# Skill 接口文档索引

每个 skill 一份接口文档，按 `_template.md` 格式填写。

| # | Skill | Phase | 文档状态 | 填写人 | 备注 |
|---|-------|-------|---------|--------|------|
| 1 | upy-analyze | Phase 1 | ✅ 已定稿 | — | 需求解析 + 驱动搜索 |
| 2 | upy-select-hw | Phase 2 | ✅ 已定稿 | — | MCU 选型 + 引脚分配 + BOM |
| 3 | upy-scaffold | Phase 3 | ✅ 已定稿 | — | 项目骨架生成 |
| 4 | upy-generate | Phase 4 | ✅ 已定稿 | — | 业务代码生成（最重） |
| 5 | upy-simulate | Phase 4.5 | ✅ 已定稿 | — | PC 端全流程模拟 |
| 6 | upy-deploy | Phase 5 | ✅ 已定稿 | — | 烧录运行 |
| 7 | upy-autofix | Phase 6 | ✅ 已定稿 | — | 自动修复编排 |
| 8 | upy-wiring | Phase 7a | ✅ 已定稿 | — | 接线图生成 |
| 9 | upy-diagram | Phase 7b | ✅ 已定稿 | — | 架构图生成 |
| 10 | upy-gen-driver | 异常路径 | ✅ 已定稿 | — | 冷门硬件驱动生成 |
| 11 | upy-publish | 收尾 | ⚠ 待填写 | — | 驱动规范打包 + 发布 upypi |
| 12 | upy-firmware-wrapper | 非 Phase | ⚠ 待填写 | — | 固件 API Wrapper 包编写规范 |

状态说明：⚠ 待填写 → 📝 填写中 → ✅ 已定稿 → 🔄 需修订

## 填写顺序建议

不需要按 Phase 顺序。建议按**插件端依赖优先级**：

1. **先填 upy-analyze** — 包含第一个 approval_request（器件确认卡片），插件端可以据此开发审批卡片组件
2. **再填 upy-deploy** — 包含 device_command 和 stream，插件端可以据此开发设备透传和终端面板
3. **然后填 upy-generate** — 包含大量 status_update + file_operation，验证进度时间线和文件操作
4. 其余按需填充

这样插件端在最早阶段就能开发出最核心的 UI 组件。
