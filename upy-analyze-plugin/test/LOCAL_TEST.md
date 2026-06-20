# `upy-analyze-plugin` 本机 mock 测试说明

## 目的

在没有真实插件宿主的情况下，先验证 analyze 的协议链是否顺畅。

当前验证范围：

- `approval_request`
- `status_update`
- `script_run`
- `phase_complete`

## 当前文件

- `SKILL.md`
- `scripts/init_manifest.py`
- `mock_plugin.py`
- `analyze_runner.py`
- `sample/*.json`

## 当前驱动搜索口径

本地 mock 演练已经跟随新版规则：

- 先区分 `builtin_runtime` 和“具体器件驱动”
- 具体器件驱动通过 `pkg_guide_adapter` 模拟 `upy-pkg-guide` 结果
- 真实服务端流程应调用 `upy-pkg-guide`，本地 adapter 只用于确定性 mock 演练
- `micropython_lib` 主要用于 `aioble` 这类官方生态通用库/中间件
- 像“土壤传感器”这类大类器件，应先拆实现族，例如 `ADC` / `Modbus` / `I2C`

## mock_plugin.py 当前行为

### approval_request

- `device_confirm`
  - 自动返回 `confirm`
  - 自动选中默认选项
- `requirement_supplement`
  - 自动返回 `confirm`
  - 自动保留默认选项
- `alternative_device`
  - 自动返回 `accept_alt1`

### status_update

- 打印到 `stderr`，便于观察时间线

### script_run

- 当前只支持 `python`
- 会真实执行脚本
- 把 `stdout/stderr` 包装成 `script_result`

### phase_complete

- 打印结果和 `summary`

## 建议测试场景

### 总 smoke 测试

```text
python test/smoke_tests.py
```

覆盖：

- 测试模块导入
- `sample/*.json` 格式
- `phase_complete.manifest_content` 可被 `scripts/init_manifest.py` 校验
- runner/mock 桥接能走到 `phase_complete`

### 场景 A：happy path

目标：

- 完整经过
  - 意图拆解
  - 器件确认
  - requirement_supplement
  - 驱动搜索
  - manifest 校验
  - `phase_complete(success)`

### 场景 B：系统推荐器件无驱动

目标：

- 触发 `alternative_device`
- mock 自动选 `accept_alt1`
- 更新后的 devices 列表应体现替代结果

### 场景 C：用户指定器件无驱动

目标：

- 不触发 `alternative_device`
- 直接在 manifest 中打 `cold-driver` 标记

### 场景 D：土壤类器件分实现族

目标：

- 输入土壤相关需求
- 根据描述区分 `ADC` / `RS485/Modbus`
- 其中具体器件驱动由 adapter 模拟 `upy-pkg-guide` 查询结果

### 场景 E：manifest 校验失败

目标：

- `scripts/init_manifest.py` 返回 `status=fail`
- analyze 不应输出错误的 success 结果

## 当前局限

`mock_plugin.py` 不是完整插件替身，只是最小协议测试器。

后续仍可继续补：

- 用户补充信息后重新分析
- 更完整的脚本运行样例
- 更复杂的失败恢复路径
