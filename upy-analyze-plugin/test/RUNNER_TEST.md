# `upy-analyze-plugin` runner 演练说明

## 目标

用最小 `analyze_runner.py` 把：

- sample 输入
- `mock_plugin.py`
- `scripts/init_manifest.py`

串成一条可本机演练的 analyze 协议链。

## 当前定位

`analyze_runner.py` 不是完整服务端 analyze 实现。

它当前主要负责：

1. 读取 `sample/start_phase.analyze.json`
2. 输出最小 `status_update`
3. 输出 `approval_request(device_confirm)`
4. 接收 `approval_response`
5. 按需输出 `approval_request(requirement_supplement)`
6. 输出驱动搜索进度
7. 条件触发 `approval_request(alternative_device)`
8. 输出 `script_run(init_manifest.py)`
9. 接收 `script_result`
10. 完成本地 manifest 校验
11. 输出 `phase_complete`

重点是先把协议链跑通。

## 当前驱动搜索展示口径

runner 现在按新版规则展示：

- `builtin_runtime` 表示底层运行时/外设能力可用
- 对 `I2C / SPI / UART` 具体器件，会额外提示“仍应继续优先检查 upypi”
- `micropython_lib` 表示官方生态通用库/中间件
- `upypi / awesome-micropython / github` 表示具体器件驱动来源

## 当前可演练方式

正确方式：

```text
python test/run_local_mock_session.py
```

完整 smoke 检查：

```text
python test/smoke_tests.py
```

不要直接用：

```text
python test/analyze_runner.py | python test/mock_plugin.py
```

因为这只是单向管道，不是双向协议桥接。

## 当前演练范围

当前 runner 已覆盖：

- happy path
- 器件确认卡片
- requirement_supplement
- 驱动搜索进度
- alternative_device 基础分支
- cold-driver 基础分支
- manifest 校验
- 成功结束

当前还未完全覆盖：

- 真实 `upy-pkg-guide` skill 调用与网络查询
- 用户补充信息后重新分析的复杂路径
- 更复杂的失败恢复路径
- boards 深度消费与选型规则参与

## 怎么理解它

当前最有价值的点不是“它已经是完整 analyze 服务”，而是：

- 协议消息顺序已经有了
- mock 插件对接位已经有了
- manifest 校验环节已经串进来了
- alternative 和 cold-driver 两类入口分支已经能演练

也就是说，`upy-analyze-plugin` 已经从“静态文档”进入“可演练结构”。
