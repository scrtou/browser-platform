# 原生反向文字复制记录（2026-09-13）

Work / Personal 已部署远程文字复制到本机的原生路径。无需修改 Trilium，也无需在线便签中转。重新加载 Trilium 的 WebView 后，在远程网页选中文字并按 **⌘C**，等待“文字已复制到本机”，再回本机应用按 **⌘V**。若提示再按一次 ⌘C，应保持远程画面获焦并再次操作。

用户已确认本机截图与文字原生粘贴到远程正常，随后在 macOS Sequoia 15.1 / Trilium 0.105.0 上反馈“反向文字可以了”，确认原生反向文字复制主流程可用。以下大文本、异常及菜单等分项记录为隔离测试及部署验证，未逐项完成用户实测。

## 实现与边界

[客户端代码](screenshot-paste.js) 处理远程画面 `overlayInput` 中的可信复制动作。⌘C 先发送远程 Control+C，收到服务端传回的文字后，通过原生 `copy` 事件的 `clipboardData.setData` 写入本机。不会调用 `navigator.clipboard.writeText` 作为这条路径的实现，也不会授予 Trilium 新权限。原有上游自动同步代码仍会被 Trilium 的策略拒绝。

原生事件必须同步填写剪贴板，而远程返回是异步的。有可用用户操作授权、且结果在本次请求的 **4 秒**期限内返回时，通过 `document.execCommand('copy')` 触发原生复制；授权失效、响应较慢时，保存就绪文字并提示再次 ⌘C。Electron 菜单发出的原生 Copy 即使没有 DOM keydown，也可同步填写已就绪文字。

当前协议没有复制操作 ID。与已知缓存相同的回传值不足以证明远程已经处理本次按键，因此不会等固定时间后自动导出缓存；若内容未变化，用户需再次操作以明确复制当前远程剪贴板。这里验证的是已知旧值不会被当作新结果，不是为上游协议增加了操作级确认。

文本上限 **25 MiB**，只处理当前 WebSocket、主显示器的控制客户端，且远程传出必须开启。断线、焦点或操作位置改变会取消等待并显示提示。二次确认前若服务端内容改变，也会丢弃旧的就绪状态。合成复制事件不会执行传递。

在文字未就绪时，原生 Copy 不会被取消成一个空的剪贴板写入；只有实际填入文字时才取消默认操作。反向图片复制没有加入本次实现。Control+C/V 的原有远程语义、Clipboard 面板、Files 栏和本机截图/文字 ⌘V 均保留。

远程 Firefox 的右键“复制”和网页里的复制按钮只更新远程剪贴板，不会产生本机原生 Copy 事件，因此不会自动走这条反向复制路径。这里验证的原生菜单 Copy 指本机编辑命令，不是远程 Firefox 的右键菜单。

## 固定产物与部署

- 前端资源：`index-native-paste-8ba09dffca2869ec.js`
- 完整 SHA-256：`8ba09dffca2869ec4d249381f97da79c23d27b8f711cbbedad60d0fcae2ef637`
- `screenshot-paste.js` SHA-256：`79e600c65d9b5037b0c7b1e71daa928f967aecdc6ae5b0971d3dc189bb4d9e6c`
- 版本目录：`runtime/client-addons/native-clipboard-v1-ea96c7eb79871a52/`

[安装器](enable-screenshot-paste.py) 继续只接受已固定的上游前端及已记录的已知版本，生成新资源并原子替换 HTML。此次仅新增反向复制桥接，不修改上游后端或启动浏览器的配置。

两个既有旧 Wayland Worker 更新 `/opt/browser-platform/selkies-paste` 中的安装文件并执行原启动 hook。Firefox、labwc、Xwayland、Selkies 的 PID 与启动 ticks，Docker 配置、容器启动时间及 Adapter 配置/绑定均保持不变；原 Files hook 和截图 hook 保留。

`firefox-work` 与 `firefox-personal` 应用只将两个已有的只读挂载改为新版本目录，目标仍为 `/opt/browser-platform/selkies-paste` 和 `/custom-cont-init.d/95-browser-platform-paste`。完整应用记录检查确认其他字段未改变，Camoufox 应用未改变。两个新应用会话及一次性 QA Worker 的重启均加载相同摘要；只有这些隔离 QA Worker 被重启。

## 验证

[端到端脚本](checks/native-copy-client.py) 使用真实远程 Firefox [文本页面](checks/native-copy-fixture.html) 与 Chromium 151.0.7922.34 / Linux 客户端，通过 `MacIntel` 分支和原生平台编辑命令检查 ⌘C。Session origin 的读写权限均为 `denied`，Async Clipboard API 实际返回 `NotAllowedError`。

| 验证 | 结果 |
| --- | --- |
| X11 / Wayland 中文、多行、emoji | 均通过，原生 Copy 事件 `isTrusted=true` |
| 分块文本 | 1,200,015 字节，完整 UTF-8 内容与 SHA-256 一致 |
| 剪贴板同值 | 首次不自动导出缓存，二次原生复制成功 |
| 已知旧值回传 | 不计为新复制完成，后续新值成功 |
| 超过本次操作期限 | 不自动写入，再次原生复制成功 |
| 原生编辑命令无 keydown | 可启动复制及完成二次确认；等待时保留原本机内容 |
| 焦点改变、断线 | 取消，不在之后写入本机剪贴板 |
| 禁用远程传出、共享只读客户端 | 不注入复制按键、不写入本机剪贴板 |
| 仅禁用传入 | 反向复制仍可用 |
| 合成 copy / keydown | 不传递 |
| 截图及原有输入回归 | 两种桌面的图片完整性、分块、中文、手动面板、Mac 键位与取消限制均通过 |
| 新应用启动、QA 重启、两个真实入口 | HTML / JS 为 200，最终摘要一致 |

文本摘要：`50855992f22c92bfff34a05dbf96fcdbdb4df73223c48bb0636b12ca0bc400f8`。

另外下载并核对了官方 Electron **43.4.0**（Trilium 0.105.0 的依赖版本），在 `persist:webview` 中保留 `contextIsolation=true`、`sandbox=true`、`nodeIntegration=false`，权限只允许 fullscreen。API 被拒绝时，原生编辑 Copy 可通过事件写入文字；空的默认 Copy 保留已有内容。注入用户操作授权后，0、200、1500 ms 的延后原生复制成功，5500 ms 时授权过期且原内容保留。**这一 Electron 探针的操作授权由测试 API 注入，未通过该探针验证实际系统按键路由，也不是完整 Trilium 测试。**

端到端测试的 WebSocket 由 Playwright 路由，因此延迟案例用于验证本次请求的固定期限；浏览器真实授权过期由不经过该路由的独立探针验证。不能把模拟 Mac 键位或 Electron 权限探针当作实际 macOS / Trilium 已验收。

证据均位于 Git 忽略目录，部署备份时需单独保留：

- [X11 反向复制](runtime/native-copy-x11-2026-09-13-final/native-copy.json)
- [Wayland 反向复制](runtime/native-copy-wayland-2026-09-13-final/native-copy.json)
- [X11 原有粘贴回归](runtime/native-copy-forward-x11-2026-09-13/screenshot-paste.json)
- [Wayland 原有粘贴回归](runtime/native-copy-forward-wayland-2026-09-13/screenshot-paste.json)
- [Electron 权限与原生事件探针](runtime/native-copy-rollout-2026-09-13/capability/final-report.json)
- [部署、进程保留与新会话记录](runtime/native-copy-rollout-2026-09-13/)

未连接现有用户会话的 WebSocket，也未读取用户网页或实际剪贴板。测试会话与客户端均隔离，测试 Worker 和带授权参数的 Session 文件已清理。

## 回滚

此次更新前的完整客户端文件分别保存在私有部署目录的 `work.backup/` 和 `personal.backup/`。恢复对应的 `index.html`、安装器、客户端脚本、`bundle.json` 和 manifest，即可回到已验收的单向原生粘贴版本；Files 和截图 hook 本次未改变。HTML 应原子替换并保持可读权限，之后重新加载客户端即可。

后续新会话的应用挂载回滚使用同目录的 `rollback-patches.json`；它只恢复原 mounts，其他应用字段保留。**不需要重载 Selkies、重启桌面或重启原 Worker。** 新版本资源可暂时保留，解除所有引用后再清理。
