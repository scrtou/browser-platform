# Trilium 使用与客户端验收

[文档导航](README.md) · [开发进度](progress.md) · [运维与恢复](operations.md) · [验收索引](acceptance/README.md)

## 接入地址

在 Trilium 的 WebView 笔记中保存固定 Profile 地址：

| Profile | URL |
| --- | --- |
| Work | <https://mybrowser.azhen.de/browser/work/> |
| Personal | <https://mybrowser.azhen.de/browser/personal/> |

`https://mysession.azhen.de/` 承载 SealSkin 会话与显示通道。入口会自动跳转并授权，不把 Session URL 保存到永久笔记。Work 现使用带正常退出和显示认证能力的兼容 Firefox/Wayland 代次；Personal 已切换到 r9/fill-r10、新 Home 与受管理代理。旧 Personal、r7 和 Work Home、加密备份及回退材料仍保留；部署范围见 [开发进度](progress.md#deployment)。

[入口登录](../infra/sealskin/entry-auth/README.md) 已随 R4B 上线。仍保存上述固定地址；首次进入或登录到期时先登录，再进入获授权的 Profile。入口首页可退出登录，退出会断开该登录的画面，浏览器数据保留。再次登录后打开固定入口可重新连接；打开第二个完整画面会接管前一个画面的控制。服务器端生产登录、交接与最终 Session 已通过；用户也已在目标 Mac/Trilium 确认正式登录、Personal 铺满/点击/图片预览和 Work 打开正常。R6F 已把管理面安全子集部署到 `/manage/`；2026-09-19 用户在目标 Mac/Trilium 使用原 `owner` 账号成功进入，页面显示 Personal/Work、账号管理和修改/停启/安全关闭操作，并完成名称/起始页可逆修改、账号创建及普通账号边界实测。新增/归档删除、代理和自定义指纹随后只在维护窗口对临时 Profile 做过服务器端组合验证，未在 Mac/Trilium 上验收；未触发生产 Personal/Work 的停用、启用或安全关闭。

## 常用操作

<a id="r4b-独立实机验收"></a>
### R4B 独立实机验收

本轮临时入口曾为 <https://mybrowser.azhen.de/browser/network-qa-browser/>，使用 r9 Camoufox 环境和 `fill-r10` 客户端。用户已确认视觉铺满且点击映射正常；未横向展开时会出现非等比拉伸，字体看起来细长，这是固定分辨率取舍。实机确认结束后该入口的专用路由已删除、临时账号禁用、运行资源和明文访问材料清理；独立 QA Home 与验收证据保留。该地址当前不再提供本次测试服务。

验收时依次点击五个彩色按钮，输入中文/emoji/补充平面汉字，检查输入法候选和取消；再测试文字双向传递、截图粘贴、Files 选择/拖放、标签页/导航及断网后恢复重载。点击「复制验收资料（F9）」保存文字报告，按 [矩阵](client-matrix.md) 记录通过、失败和未测。QA 当时只开放该入口、登录路径及精确 QA Session 的显示路径，Work 路由保持；R4B 已完成专用路由、账号、浏览器、网络和显示材料清理。

本次补测重点是固定画面铺满：用户已确认 fill-r10 在当前 Trilium 视区没有黑色留边并且彩色按钮点击正常，但观察到未横向展开时字体变细长；这是把固定 1920×1080 画面映射到非 16:9 视区的显示缩放。截图预览已经由用户在上一代次确认可见，Linux fill-r10 也已复验实际 320×160 图片像素。若再次核对截图，点击页面下方「截圖貼上區」再按 ⌘V，直接核对显示出的图片；只有右下角成功提示还不能确认页面已收到图片。请只用测试截图；F9 报告会增加实际图片的类型、尺寸和摘要，无需上传截图到项目记录。Linux 的窗口、坐标、上传、断线恢复和图片像素对照已通过，Mac 的 fill-r10 视觉和点击映射已确认。

以下常用操作的历史证据仍按各自环境适用。

| 要做什么 | 操作说明 |
| --- | --- |
| 本机文字或截图粘贴到远程 | [主动按 ⌘V 粘贴](#截图直接粘贴不用先保存文件) |
| 远程文字复制到本机 | [选中文字后 ⌘C，等待成功提示](#远程文字原生复制到本机) |
| 通过侧栏中转文字 | [Clipboard 面板](#macos-的手动文本传递) |
| 上传本机已有图片/文件 | [Files → Upload Files](#图片上传与-files-栏) |
| 浏览器误关后恢复 | [入口恢复提示 / 远程桌面右键 → FireFox](#关闭远程-firefox-后出现黑框) |
| 了解文字大小与客户端权限 | [大文本](#文字长度与大文本)、[权限限制](#trilium-01050-的剪贴板限制) |

## 当前用户验收

2026-09-13，用户使用 Trilium 0.105.0、macOS Sequoia 15.1，反馈如下。当时两个固定入口均对应原 Firefox Profile。

| 项目 | 用户反馈 |
| --- | --- |
| Personal / Work 入口和画面 | 均可正常查看 |
| 中文输入 | 正常 |
| 缩放、滚动 | 正常 |
| 恢复会话 | 正常 |
| Clipboard 面板双向文本传递 | 用户在 Mac 上复测通过 |
| 自动剪贴板同步 | 受 Trilium WebView 权限限制，尚未启用 |
| 截图直接粘贴 | X11 / Wayland 隔离测试通过；用户在 Mac / Trilium 上复测确认正常 |
| 本机文字原生粘贴到远程 | 用户复测确认正常 |
| 远程文字原生复制到本机 | 已部署；X11 / Wayland 隔离回归通过，用户在 Mac / Trilium 上确认反向文字复制可用 |
| Files 栏与图片上传 | 两个入口已开启，隔离测试通过；Mac / Trilium 文件选择待用户复测 |

该轮尚未提供显示缩放比例、输入法名称与 screen/DPR 分项。恢复会话的反馈不能替代主机重启等故障验收。入口修复与回归见 [入口验收](../infra/sealskin/entry-acceptance-2026-09-13.md)。

2026-09-14 新增 [客户端分项矩阵](client-matrix.md)：Camoufox 的 Linux 隔离验收覆盖三组尺寸/DPR、坐标、Unicode、导航/标签页、文件上传与断线后重载，以及完整原生复制/截图回归；该轮的 Mac 分项留给 R4B。

2026-09-15，用户补充 macOS 15.1 (24B83) / Trilium 0.105.0、本机 1280×800、正常显示、macOS 系统中文输入法，并确认 r7 QA 的基础输入/候选取消、双向文字、Files 按钮选择/Finder 拖放、后退/前进、新标签页和断网恢复重载通过。用户反馈窗口偏小、截图仅看到成功提示；r9 已修复窗口并补上图片预览区，原入口留供复测。远端报告的 1920×1080 / DPR 1 不代表 Mac 本机参数。

2026-09-16，用户复测 r9 后确认五个按钮可点击、页面可见图片预览，但固定画面没有铺满 Trilium 视区，并指出 Work 页面显示正常。检查发现远端窗口本身已铺满，留边来自客户端对固定 16:9 串流的等比缩放；独立 QA 已切到 `fill-r10`，改为完整视区映射并通过 Linux 多尺寸坐标回归。用户随后确认 fill-r10 已铺满且点击正常，但 Trilium 未横向展开时字体显得细长、分辨率观感与 Work 不同；这是固定远端画面被非等比映射的结果，作为固定分辨率取舍保留。

2026-09-19，用户提供目标 Mac/Trilium 的生产管理面截图。截图中 `owner` 显示为启用的 `admin`，Personal 与 Work 的固定入口、运行状态、修订和账号分配均可见；Work 健康为 `healthy`，Personal 为非阻断的 `unknown / PROXY_UPSTREAM_UNKNOWN`。同一时点服务器只读复核确认 Personal 的入口、控制面、Session、Worker、浏览器和显示均通过，只有上游探测端点超时，`blocking=false`；重复强制探测结果相同，不能据此判断代理失效。截图 SHA-256 与详细报告只保存在忽略的私有证据目录，不把图片或账号画面提交到公开仓库。

随后用户在同一生产管理面提交 Personal 名称修改，页面显示新名称“个人浏览器测试”，并显示“修订 2”。服务器端核对确认 `profiles.json` 的 Profile 目录 revision 为 2，Personal 记录 `revision=2`、`status=ready`、`disabled=false`、`updated_by=owner`，起始页仍为 `https://example.com/`；Work 保持 revision 1。Personal/Work 的运行绑定和容器未被该修改触碰，health/ready 仍为 200。名称修改实测通过；停用、启用、安全关闭和账号密码类操作仍未执行。

随后用户在 Mac/Trilium 中将 Personal 起始页临时改为 `https://example.org/`，保存后再恢复为 `https://example.com/`。服务器端核对确认 Profile 目录 revision 从 2 增至 4，Personal 最终 `revision=4`、起始页为原值、状态为 ready 且未禁用；Work 仍为 revision 1。两次修改均未改变 Personal/Work 的 Session、容器或网络绑定，health/ready 仍为 200。起始页修改与恢复实测通过；停用、启用、安全关闭和账号密码类操作仍未执行。

用户随后通过管理面创建入口账号 `test`。服务器端核对确认账号表保持 version 2、共 2 个账号：`owner` 为启用的 `admin`，仍分配 Personal/Work；`test` 为启用的普通用户，仅分配 Personal。密码内容未读取或写入公开记录，Personal/Work 运行绑定、容器和 health/ready 未受影响。创建账号实测通过。

用户随后使用 `test` 完成普通账号边界实测：可以进入 Personal 固定入口；访问 `/manage/` 被拒绝；管理面列表中不可见 Work。服务器只读核对确认两个 Profile 仍为 running，`health=200`、`ready=200`，账号授权与启用状态未被改变。普通账号三项边界测试通过。

## 关闭远程 Firefox 后出现黑框

2026-09-13，用户关闭 Work 的 Firefox 后刷新页面，看到黑框。检查确认 Firefox 主进程已退出，而原 Worker、labwc、Xwayland 和 Selkies 仍正常运行。固定入口复用存活的 Session；当前桌面 autostart 只在桌面启动时执行一次，重新加载 Trilium 页面不会重新启动已经退出的 Firefox。

已在原 Work Worker 内，以原用户 `abc`、`HOME=/config` 和现存 Xwayland 的桌面环境重新执行 `/usr/bin/firefox`。确认 Firefox 窗口可见、已最大化且获得焦点，持有原 Profile 的锁；Work 桌面与串流、Personal 全部进程、容器及 Home 挂载、Adapter 配置与绑定均保持不变。过程没有检查网页内容，也不代表所有标签页已恢复；需要时可在 Firefox 的 History → Restore Previous Session 中恢复上次浏览状态。证据见恢复记录（本机 `infra/sealskin/runtime/work-browser-recovery-2026-09-13/after.json`）。

再次误关时可以自行重开。已核对当前 Work / Personal 的实际 labwc 配置：桌面空白处右键会打开 `root-menu`，其中保留 **FireFox** 启动项，命令为 `/usr/bin/firefox`。

1. 在黑框内的远程桌面空白处点右键；Mac 触控板可双指点按。
2. 选择 **FireFox**，浏览器会在当前会话和原 Profile 中重新打开。
3. 若需要找回旧标签页，使用 Firefox 的 **History → Restore Previous Session**。

此方法适用于浏览器窗口已关闭、桌面连接仍正常的情况，无需重启 Worker。菜单配置核对后，用户按上述方法复测并确认“测试正常了”，自行重开路径已通过用户验收。日常离开时切换或关闭 Trilium 中的笔记即可保留远程浏览器窗口；Firefox 退出后的自动重开尚未实现。

2026-09-13 起固定入口会先做只读健康预检：检测到浏览器已退出、显示通道不可用或代理链路故障时，入口不再直接跳转，而是显示恢复步骤，并保留「继续进入会话」按钮；点「重新检查」可强制重新采集。预检超时、控制面不可用或状态未知时仍按原方式自动进入会话，不会因此新建或重建浏览器。该提示页已在隔离 QA 与线上入口（无故障、自动进入）验证，**在 Trilium WebView 中的显示与操作待用户复测**；验收记录见 [健康验收](../infra/sealskin/health-acceptance-2026-09-13.md)。

## Trilium 0.105.0 的剪贴板限制

官方 [WebView 实现](https://github.com/TriliumNext/Trilium/blob/v0.105.0/apps/client/src/widgets/type_widgets/WebView.tsx) 使用独立的 `persist:webview` Electron Session。[权限策略](https://github.com/TriliumNext/Trilium/blob/v0.105.0/apps/desktop/src/services/web_contents_security.ts#L126) 对 guest 仅允许 `fullscreen`；`clipboard-read` 和 `clipboard-sanitized-write` 均被拒绝，请求和权限查询都应用这一策略。增加服务端 HTTP 响应头不能授予被 Electron 主进程拒绝的权限。

当前 Selkies 在窗口获焦时使用 `navigator.clipboard.read/readText` 读取本机剪贴板，在收到远程内容后使用 `write/writeText` 写入本机剪贴板，所以自动同步会受此限制。其 WebSocket 模式仍将远程文本显示在 Clipboard 面板中；面板文字框使用原生编辑操作，失去焦点时将内容发送至远程剪贴板。

这一限制针对 Async Clipboard API。用户主动触发的原生 `paste` / `copy` 事件仍可传递数据；项目已在 Selkies 网页中补充这两条路径，没有修改 Trilium。

远程→本机当前只支持纯文本。反向图片、HTML/RTF 与其他二进制没有可靠的已交付路径；本机→远程截图支持不代表反向也支持。Linux Electron 探针中，原生 Copy 可写 HTML，但 File 或 image MIME 字符串没有生成系统可读图片；当前远程桥接也未传递 HTML。Files 栏只提供上传，不能用于从远程下载。细节与限制见 [R4A 非文本结论](../infra/sealskin/client-migration-acceptance-2026-09-14.md#非文本能力决定)。

## 能否开启自动同步权限

2026-09-13 核对官方 releases，最新稳定版仍为 [v0.105.0](https://github.com/TriliumNext/Trilium/releases/tag/v0.105.0)。该版本的 [安全设置](https://github.com/TriliumNext/Trilium/blob/v0.105.0/apps/desktop/src/services/security_settings.ts) 只提供后端脚本、SQL 控制台和局域网访问开关，没有 WebView 剪贴板开关；当日检查的 main 分支也仍对 guest 仅允许 `fullscreen`。

启用权限需要修改本机 Trilium 的 Electron 主进程策略。建议只给 `persist:webview` 中 **origin 精确等于 `https://mysession.azhen.de`** 的请求开放 `clipboard-read` 与 `clipboard-sanitized-write`；该域名承载 Selkies，固定入口域名 `mybrowser.azhen.de` 不需要剪贴板权限。权限请求和权限查询应共用同一条按 origin 授权的规则，并验证请求所属 WebView；其他来源及其他权限继续沿用原策略。

不能仅在 `guest` 的集合中添加权限名称：现有 `isPermissionAllowedForOrigin` 还会把非全屏权限限制为 Trilium 自身的 app origin，需要一起调整。网站响应头、Note 属性和 macOS 系统设置无法覆盖 Electron 主进程的拒绝决定。

这一路径需要构建并按 macOS 的应用签名要求分发定制客户端，后续官方升级时需重新检查补丁兼容性。完成授权后仍需在用户 Mac 上回归自动同步和快捷键。目前只完成方案核对，**尚未修改或安装 Trilium 客户端补丁**。主动复制与粘贴使用本页记录的原生事件路径，手动面板继续保留。

## macOS 的手动文本传递

点击远程画面最左侧中央的蓝色竖条，打开 Selkies 侧栏，再展开 **Clipboard / 剪贴板**。这里的面板属于本机显示客户端。

本机 → 远程：

1. 在 Mac 应用中用 **⌘C** 复制文字。
2. 在 Clipboard 面板文字框中用 **⌘V** 粘贴；如需替换旧内容，先用 **⌘A** 全选。
3. 点击远程浏览器的目标输入框，让面板失去焦点并发送内容，再按 **Control+V** 粘贴。

远程 → 本机：

1. 在远程浏览器中选中文字，按 **Control+C**。
2. 在 Clipboard 面板中确认收到文字，再选中它并按 **⌘C**。
3. 回到 Mac 应用，用 **⌘V** 粘贴。

这里的 Control 是 Mac 键盘上的 **⌃ Control**。远程 Linux 浏览器使用 Control 快捷键，面板文字框使用 macOS 原生 Command 快捷键。上述面板路径保留；远程画面的 **⌘V** 原生粘贴入口见下文“截图直接粘贴”。

## 远程文字原生复制到本机

2026-09-13 已为 Work / Personal 增加原生反向文字复制。先重新加载 **Trilium 的 WebView**，然后：

1. 在远程 Firefox 网页中选中文字，按 **Command+C**。
2. 等待右下角显示“文字已复制到本机”。若提示“再按一次 ⌘C”，保持远程画面获焦并再按一次。
3. 回到本机应用，按 **Command+V** 粘贴。

无需打开侧栏或使用在线便签中转。**Control+C** 继续只复制到远程 Linux 剪贴板；使用旧面板流程时仍按上一节操作。

**远程 Firefox 右键菜单的“复制”和网页里的复制按钮也只更新远程剪贴板**。这些远程操作不会产生本机的原生 `copy` 事件，因此不会触发上述反向复制流程。本机编辑菜单送达当前远程输入层的原生 Copy 与远程右键菜单不同。要把文字带回 Mac，可使用上述 Command+C 流程，或在 Clipboard 面板中选中已收到的文字后按 Command+C。

客户端先发送远程 Control+C，再等待服务端传回文字。收到与已知缓存不同的文字后，仅在本次操作的 4 秒期限及浏览器用户操作授权内尝试原生复制。超过期限，或远程剪贴板内容未变化时，需要再次主动复制；不会只等待固定时间就自动写入缓存文字。焦点、选区操作或连接改变会取消等待。复制未成功时请保留当前选区并按提示重试。

当前反向路径支持 **25 MiB 以内的纯文本**，需要当前客户端有控制权且 Clipboard 的远程传出已开启。文字只保存在当前客户端的会话内存中；不调用 Async Clipboard 写入 API。原生菜单 Copy 也可处理已就绪的文字，不要求收到 DOM 的按键事件。

独立 X11 / Wayland 会话通过了中文、多行、emoji、1,200,015 字节分块文本、原生菜单复制、已知旧值拒绝、延迟确认、焦点取消、断线及只读限制的检查；现有截图与文字粘贴也通过回归。另在 Electron 43.4.0 中验证了与 Trilium 相同的 guest 权限拒绝策略下，原生 Copy 事件可写入文字。用户随后在 macOS Sequoia 15.1 / Trilium 0.105.0 上反馈“反向文字可以了”，确认原生反向文字复制主流程可用；上述大文本、异常及菜单场景仍以隔离测试为证据，未逐项完成用户实测。部署摘要、测试方法和回滚见 [反向复制记录](../infra/sealskin/native-copy-acceptance-2026-09-13.md)。

## 截图直接粘贴，不用先保存文件

2026-09-13 已为 Personal / Work 补充用户主动粘贴入口。先重新加载 Trilium 中的远程页面，让 Selkies 客户端加载更新，然后：

1. 在 Mac 上按 **Control + Shift + Command + 4**，框选截图，图片直接进入系统剪贴板。
2. 点击远程网页中支持图片粘贴的输入框，例如聊天输入框。
3. 按 **Command + V**，等待右下角粘贴提示并确认网页中的图片或附件预览。

此路径无需打开 Files，也无需手动开启 Image Support。没有本机保存图片、文件选择或远程 Desktop 中转步骤；图片经远程剪贴板交给 Firefox 的原生 `paste` 事件。目标网站需要支持粘贴图片，后续发送由用户确认。**Control + V** 继续粘贴远程 Linux 剪贴板，原有手动文本面板仍可用；新增的 **Command + V** 也支持本机文字。

实现读取用户主动触发的 `paste` 事件中的 `clipboardData`，不调用 Async Clipboard API，不更改 Trilium 权限策略。单次上限 **25 MiB**，支持 PNG、JPEG、WebP、BMP。为确认传递完成，仅在图片粘贴期间临时启用 Selkies 的二进制剪贴板回传，逐字节匹配收到的内容后触发远程 Control+V，随后恢复用户当前的 Image Support 设置。需要当前客户端具有控制权且 Clipboard 双向传递开启。连接断开、焦点或操作位置改变、确认超时均不触发自动粘贴。

独立的原 Firefox Wayland 和 Personal 代理 X11 会话均通过：客户端 Clipboard API `denied`，可信原生图片粘贴事件，2,470,507 字节 PNG 分块传输，远程 Firefox 接收图片的尺寸与完整 RGBA 像素 SHA-256 一致；中文文字、原有面板及普通键盘输入回归通过。另已模拟 Mac 键位，修正上游 Command 转 Alt 导致 X11 菜单抢走焦点的问题，并验证 Command+A/C 和持续按住 Command 跨粘贴操作。新建会话和一次性 QA Worker 重启后也加载相同前端摘要。此次截图功能部署仅更新两个 Worker 的静态文件，Firefox、桌面和 Selkies 进程均保留。

QA 客户端是 Chromium 151 / Linux，使用原生浏览器粘贴命令在该平台执行带 Meta 修饰键的粘贴动作。用户随后在 **Trilium 0.105.0 / macOS Sequoia 15.1** 上复测并确认“测试正常”，截图直接粘贴已通过目标客户端验收。该反馈不覆盖 Files 的原生文件选择与拖放。部署、证据与回滚见 [截图粘贴记录](../infra/sealskin/screenshot-paste-acceptance-2026-09-13.md)。

## 图片上传与 Files 栏

2026-09-13 已按用户要求为 Personal / Work 开启 **Files → Upload Files**。刷新 Trilium 中的远程页面后：

1. 打开左侧蓝色拉条，展开 **Files**，点击 **Upload Files**。
2. 选择 Mac 上已有的 PNG/JPG 文件，等待上传完成。剪贴板截图可使用上一节的直接粘贴入口。
3. 在远程 Firefox 的目标网站点击“上传图片”。
4. 在远程文件选择框中按 **Control+L**，输入 `/config/Desktop/` 并回车，选择刚上传的图片。

侧栏上传只将文件传入远程电脑，需要继续在目标网站选择该文件。也可将 Finder 中的文件拖到远程画面中央上传。这两个路径不调用系统 Clipboard API，也不需要开启 Clipboard 面板的 Image Support。当前 Files 栏提供上传按钮。

此前 Files 被桌面加固初始化脚本注入的 `SELKIES_UI_SIDEBAR_SHOW_FILES=false` 隐藏；该值不出现在 Docker 的初始 Env 中，需要核对 Selkies 进程环境。两个应用定义显式设置 `SELKIES_UI_SIDEBAR_SHOW_FILES=true`、`SELKIES_FILE_TRANSFERS=upload`，保留 `HARDEN_DESKTOP=true`。该轮两个 Worker 均为旧 Wayland 会话，使用静态页面更新立即显示 Files；额外的 custom-init hook 为其后续启动设置相同环境。配置、验证与回滚见 [Files 开启记录](../infra/sealskin/files-sidebar-acceptance-2026-09-13.md)。

初次采用串流重载时，旧 Work 的 Wayland 桌面连带重启了 Firefox；该次设置已回滚，Home 和 Session 绑定保留。最终静态更新没有再重启两个 Worker 的浏览器、桌面或串流进程。不能把 X11 下的串流重载验收用于证明旧 Wayland 浏览器进程不受影响。

隔离 Wayland 会话已验证：Clipboard 读写权限均为 denied 时，Files 栏可见，点击 Upload Files 触发文件选择，PNG 上传后的大小和 SHA-256 完全匹配。见按钮上传验证（本机 `infra/sealskin/runtime/files-sidebar-wayland-acceptance-2026-09-13/image-upload.json`）。此前独立测试也通过了图片拖放验证（本机 `infra/sealskin/runtime/image-drop-acceptance-2026-09-13/image-upload.json`）。2026-09-15 用户已确认 r7 QA 的 Mac / Trilium Files 选择和 Finder 拖放均成功；r9 的 Linux 选择/拖放及远端文件摘要复测也通过，版本范围见 [矩阵](client-matrix.md)。

## 文字长度与大文本

2026-09-13 检查正在运行的固定 Firefox 基础镜像：侧栏 `dashboardClipboardTextarea` 没有设置 `maxlength`，当前 WebSocket 纯文本接收路径也没有配置总字数或总字节数上限。客户端与服务端都按 UTF-8 编码处理文字；达到 **750 KiB（768,000 字节）** 后自动分块，接收完整后再合并并核对总字节数。

使用同一 Selkies 基线的独立 QA 会话，已完成 **400,000 个汉字、1,200,000 字节 UTF-8 文本** 的往返：本机文字框 → Clipboard 面板 → 远程浏览器，追加 7 个 ASCII 字符后再经面板复制回本机，完整内容匹配。测试客户端为 Chromium 151.0.7922.34 / Linux，Async Clipboard 读写权限仍为 denied。报告见大文本验证（本机 `infra/sealskin/runtime/clipboard-large-text-2026-09-13/clipboard.json`）；该量级尚未在用户的 macOS / Trilium 上单独复测。

未设置总量上限不代表任意大小均可传递。当前 X11 文本读取等待为 1 秒，写入后等待 xclip 退出为 2 秒；更大内容还受浏览器渲染、内存和传输状态影响。若大文本超时或卡顿，可改用文件传递。代码中另一个 10 MiB 上限用于从文件管理器剪贴板读取图片文件，不适用于此处的纯文本路径。

## 隔离验证及边界

2026-09-13 创建独立 `camoufox-personal-r4` cleanroom 会话，其 Selkies 来自与现有 Personal/Work 相同的固定 Firefox 基础镜像。使用 Chromium 151.0.7922.34 的 Linux 客户端，通过 HTTPS 访问 Session，将该 origin 的 Async Clipboard 读写权限都设为 `denied`，并确认实际 `readText`、`writeText` 均返回 `NotAllowedError`。

测试通过原生文字框快捷键复制中文、粘贴至 Clipboard 面板、在远程浏览器粘贴并追加文本，再复制回面板和本机文字框。双向完整文本均匹配。该测试没有调用授权的 Clipboard API 来代替被测路径。

结果见本机验证报告（`infra/sealskin/runtime/clipboard-acceptance-2026-09-13/clipboard.json`），界面截图保存在同目录。此目录被 Git 忽略，部署备份需单独保留。测试没有修改原 Worker、应用定义或 Trilium 权限；原容器和 Adapter 绑定保持一致，临时 Worker 与带授权参数的 Session 文件均已清理。

隔离测试证明了权限被拒绝时 Selkies 手动面板的文本路径可行。用户随后按上述操作在 **Trilium 0.105.0 / macOS Sequoia 15.1** 上复测并确认通过，手动面板文本路径已完成目标客户端验收；自动同步仍受客户端权限策略限制。

## 2026-10-02 · R6AR 共享缩放已部署

按远程浏览器保存界面缩放百分比：管理页或远程 UI Scaling 修改，刷新/新客户端共用。支持 auto@system 和旧 Wayland Work；0 跟随客户端默认，100–300、步长 25。固定 DPR1/auto@1 不接受非零。不同已打开页面需要刷新；并发修改遇到冲突提示时刷新重试。保持比例/铺满继续仅用于固定画面。

新 Adapter `8fb90eb2…` 已通过旧 Work 和三引擎 30 个真实显示场景；生产 Home、会话、Worker 与配置保持。回退旧 Adapter 前须通过新版本正常重置非零百分比并核对新增字段已消失，不能覆盖旧目录。新 Mac/Trilium 精确硬件组合未据此补造验证。详见 [验收](../infra/sealskin/r6ar-display-persistence-acceptance-2026-10-02.md)。
