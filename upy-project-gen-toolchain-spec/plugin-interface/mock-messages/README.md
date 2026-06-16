# Mock Messages

本目录存放各消息类型的 JSON 样本，供插件端工程师独立开发测试时使用。

## 使用方式

插件端工程师可以在不连接服务器的情况下，直接用这些 JSON 文件测试 UI 渲染：

```javascript
// 测试审批卡片渲染
const approvalMsg = require('./approval-request.json');
webview.postMessage(approvalMsg);

// 测试阶段完成面板
const completeMsg = require('./phase-complete.json');
webview.postMessage(completeMsg);
```

## 文件列表

| 文件 | 对应消息类型 | 状态 |
|------|------------|------|
| `approval-request.json` | approval_request | ✅ 已创建 — 器件确认卡片 (device_confirm_001) |
| `status-update.json` | status_update | ✅ 已创建 — 9 条样例，含 info/success/warn/error 四种 level |
| `device-command.json` | device_command | ✅ 已创建 — 6 条样例，含 exec/cp/mkdir/ls/soft_reset/run |
| `file-operation.json` | file_operation | ✅ 已创建 — 6 条样例，含 write/read/append/mkdir/list/delete |
| `script-run.json` | script_run | ✅ 已创建 — 6 条样例，含 flake8/init_manifest/pack_driver/extract_pdf/run_on_device/flash_device |
| `phase-complete.json` | phase_complete | ✅ 已创建 — 完整 analyze 阶段结果，含 table/file_tree/markdown 三种 artifact |
| `stream.json` | stream | ✅ 已创建 — 7 条样例，含 device_output 和 script_stdout 两种 stream_type |

每个 skill 的接口文档定稿后，同步补充该 skill 特有的 mock 消息样本到本目录。
