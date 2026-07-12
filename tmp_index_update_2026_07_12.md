
## 2026-07-12 更新：GenDriver / Skill 接力资料补充

本索引原始内容是 2026-07-11 的资料地图。2026-07-12 已经补充了 Skill 侧的 GenDriver 字段决策、`upy-gen-driver-plugin` 二次核对和板卡新增接入资料；下次新会话需要把下面这些文档纳入优先阅读。

### 新增优先阅读文档

1. `G:\blockless-plugin-course(1)\Skill工程师GenDriver字段决策与Erson确认问题-2026-07-12.md`
   - 以末尾“更正：冷门驱动生成应归属 upy-gen-driver-plugin”和“二次核对”两节为准。
   - 前面旧的 `upy-generate-plugin` 分析和旧版 Erson 话术只作为历史记录，不作为最终对外口径。
   - 已确认冷门驱动生成主体应是 `G:\MicroPython_Skills\upy-gen-driver-plugin`，不是 `upy-generate-plugin`。

2. `G:\blockless-plugin-course(1)\Skill工程师GenDriver字段规范化待办-2026-07-12.md`
   - Skill 工程师最小可执行清单：`select-hw` 写出 `devices[].driver.status="cold_driver_required"`。
   - 保留 `driver.source="cold-driver"` 作为来源分类，不把它当 workflow gate。

3. `G:\blockless-plugin-course(1)\GenDriver冷门驱动状态字段与云端调度下一步该做什么-2026-07-12.md`
   - 拆分 Skill / Backend / Extension / Packaging / GenDriver contract 的后续处理顺序。
   - 用来决定哪些事情是 Skill 侧当前能做的，哪些需要 Erson / cloud/backend 确认。

4. `G:\blockless-plugin-course(1)\Skill负责人板卡新增当前工作清单-2026-07-12.md`
   - 板卡新增方向的当前执行清单。

5. `G:\blockless-plugin-course(1)\板卡新增接入流程与当前代码证据分析-2026-07-12.md`
   - 板卡新增流程和本地代码证据。

6. `G:\blockless-plugin-course(1)\MicroPython官方板卡待核验资料清单-2026-07-12.md`
   - 官方 MicroPython board 待核验资料清单。

### 当前最终 GenDriver 口径

```text
canonical gate field:
  devices[].driver.status

source classification:
  driver.source = "cold-driver"

workflow status:
  driver.status = "cold_driver_required"

Skill-side minimum:
  select-hw must normalize source="cold-driver" into status="cold_driver_required"
  while preserving source.

cold-driver owner:
  upy-gen-driver-plugin owns missing/cold driver generation.

generate behavior:
  upy-generate-plugin should only consume ready/local drivers, or block deploy-ready success
  and emit partial/next_action when cold_driver_required is still unresolved.

cloud/backend behavior:
  before generate, route cold_driver_required to upy-gen-driver-plugin
  and hold generate until a verified ready driver exists.
```

### 更新后的 GenDriver 阅读顺序

如果下次新会话只关心 GenDriver / cold-driver blocker，建议按这个顺序读：

```text
1. G:\blockless-plugin-course(1)\本地参考资料总索引与新会话接力说明-2026-07-11.md
2. G:\blockless-plugin-course(1)\GenDriver冷门驱动状态字段与云端调度阻塞说明-2026-07-11.md
3. G:\blockless-plugin-course(1)\Skill工程师GenDriver字段决策与Erson确认问题-2026-07-12.md
4. G:\blockless-plugin-course(1)\GenDriver冷门驱动状态字段与云端调度下一步该做什么-2026-07-12.md
5. G:\blockless-plugin-course(1)\Skill工程师GenDriver字段规范化待办-2026-07-12.md
6. G:\MicroPython_Skills\upy-select-hw-plugin\scripts\select_hw_manifest.py
7. G:\MicroPython_Skills\upy-gen-driver-plugin\SKILL.md
8. G:\MicroPython_Skills\upy-gen-driver-plugin\sample\start_phase.upy_gen_driver_plugin.pipeline.json
9. G:\MicroPython_Skills\upy-gen-driver-plugin\sample\phase_complete.upy_gen_driver_plugin.success.json
10. G:\MicroPython_Skills\upy-generate-plugin\scripts\download_drivers.py
```

注意：`F:\mpy-hardware-extension` 不是当前 Skill 工程师要修改的仓库。当前 Skill 侧优先处理 `G:\MicroPython_Skills`，插件 / backend / cloud 的调度与 submodule bump 需要由对应 owner 处理。

### 更新后的板卡资料阅读顺序

如果下次新会话只关心板卡新增 / 官方 board mapping，建议按这个顺序读：

```text
1. G:\blockless-plugin-course(1)\板卡双JSON配置与官方映射改造说明-2026-07-11.md
2. G:\blockless-plugin-course(1)\板卡新增接入流程与当前代码证据分析-2026-07-12.md
3. G:\blockless-plugin-course(1)\Skill负责人板卡新增当前工作清单-2026-07-12.md
4. G:\blockless-plugin-course(1)\MicroPython官方板卡待核验资料清单-2026-07-12.md
5. G:\MicroPython_Skills\upy-analyze-plugin\boards
6. G:\MicroPython_Skills\upy-analyze-plugin\boards\matching-rules.json
```

### 给新会话的补充提示

```text
索引原始阅读顺序是 2026-07-11 版本。处理 GenDriver 时，必须继续阅读 2026-07-12 的 Skill工程师GenDriver字段决策与Erson确认问题文档，并以其中“更正”和“二次核对”部分为最新结论。

不要把 cold-driver 生成归到 upy-generate-plugin；正确 owner 是 upy-gen-driver-plugin。upy-generate-plugin 只负责在 unresolved cold_driver_required 时阻止 deploy-ready success 或输出 partial/next_action。

当前 Skill 工程师不改 F:\mpy-hardware-extension，只改 G:\MicroPython_Skills。需要兼容插件调用和本地 skill 调用测试两种情况，并持续关注 session/checkpoint/resume/cancel/retry/timeout/idempotency/protocol/capability/error/artifact/permission prompt 这些协议面。
```
