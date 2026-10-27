# Chrome 与飞书编辑要点

先按[连接与会话复用](chrome-connection.md)复用或建立可用连接并核实目标。以下以随包脚本的 `ev()`、`click()`、`cdp()` 为例，其他工具使用自己的等效接口，无需切换连接。选择器与内部接口来自 2026-10-27 本机实测，不保证平台内部接口永久不变。

## 正文、光标与对象

- 用 `ev('document.body.innerText')` 或 DOM（文档对象模型）定位读取实际页面，不打印 Cookie（浏览器会话数据）、授权令牌或整个浏览器存储。
- 飞书正文真实可编辑区可查 `.zone-container[contenteditable="true"]`；只查 `[contenteditable]` 会误中不可编辑容器。标题、正文、表格单元格、图片图题是不同区域。
- 对已确定的元素读取 `getBoundingClientRect()`，用 `click()` 聚焦；必要时用页面 `Range`（文本选区）选择准确范围，再执行 `cdp('Input.insertText',{text:'实际内容'},sid)`。先读回选区与焦点，避免写入标题栏或另一张图片。
- 飞书有虚拟渲染：未找到 DOM 不代表内容不存在。先点击目录 `.catalogue__item-title` 的准确文本，再在 `.bear-web-x-container` 滚动，按实际对象重新定位。
- 每步重新读取 DOM。稳定块标识可用 `[data-record-id="本次读取的标识"]`，刷新后不能沿用临时模型编号或旧坐标。

## 原生图题：必须真的绑定图片

1. 选中目标图片并显示图片工具栏或右键菜单，选择“图片说明／图题”。本机原生菜单定位为 `.block-toolbar__overlay .panel-menu-item[data-name="caption"]`；它只有图标，按可见文字搜索可能找不到。
2. 工具栏可能仍绑定上一张图。先核实新出现的 `.caption-editor` 所属 `[data-record-id]`，必须是目标图片，然后聚焦输入。不要仅凭当前滚动位置猜测。
3. 实测原生编辑器为 `.caption-editor[contenteditable="true"]`，外层图片出现 `.image-block.with-caption`，占位提示为“輸入圖片說明”。将图号、题名、简短说明写在这里；双语可分四行。较长的业务解释留在所属正文，不能把整节搬进图题。
4. 输入后离开编辑区，让原生编辑器提交。逐图读回，确认原生图题非空、图号和内容一致，再移除字面匹配的旧普通图题段落，避免重复或误删业务正文。
5. 保存并刷新，检查原生图题仍存在，实际页面显示正确，图文对应且未产生新目录项。仅有空 `image.caption` 字段不算完成。

## 结构读取及保存

- 实测页面有 `PageMain.editor.blockManager`。根模型 `rootBlockModel.snapshot.children` 才是正文阅读顺序；`allBlockModels` 数组不是顺序，图片说明属于图片内部内容。
- 结构快照应包含富文本、图片、原生表格、引用和树顺序。内部模型接口只用于已核实的页面版本，优先原生界面；确需结构修改时先用原生操作确认真实结构，限定对象、校验旧值并保留回退快照。
- `PageMain.hasUncommittedData()` 为本机实测的待保存检查；返回 false 仍需刷新读回和实际查看，不能单凭此值宣布完整交付。
- 控制连接异常时，先检查服务端是否保存了操作，再决定是否继续；超时不能自动重发上传、创建或删除。

协议参考：[CDP 概述](https://chromedevtools.github.io/devtools-protocol/)、[Target 域](https://chromedevtools.github.io/devtools-protocol/tot/Target/)。本机路径、选择器和飞书模型来自现场操作，不是 Chrome 协议保证。
