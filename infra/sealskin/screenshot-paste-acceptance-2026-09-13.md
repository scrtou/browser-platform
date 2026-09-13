# 截图直接粘贴记录（2026-09-13）

Personal / Work 已增加从本机剪贴板直接向远程网页粘贴截图的入口，无需先将截图保存成本机文件。Mac 操作：重新加载 Trilium 中的远程页面，按 **Control + Shift + Command + 4** 框选截图，点击远程网页的目标输入框后按 **Command + V**。目标网页需支持粘贴图片；确认图片预览后再发送。

用户随后在 **Trilium 0.105.0 / macOS Sequoia 15.1** 上确认“测试正常”，截图直接粘贴已完成目标客户端验收。

随后已叠加 [原生反向文字复制](native-copy-acceptance-2026-09-13.md)，用户也确认本机文字可直接粘贴到远程。当前完整客户端的资源摘要和回滚以反向复制记录为准；本文保留截图功能初次部署的产物和证据。

## 实现与范围

[客户端代码](screenshot-paste.js) 在 Selkies 键盘捕获处理器之前注册原生粘贴监听，只处理远程画面 `overlayInput` 的可信 `paste` 事件。Command+V 放行浏览器本机粘贴动作；Control+V 保留原有远程 Linux 剪贴板语义。侧栏文本输入、中文输入和 Files 上传继续沿用原路径。

Mac 的 Command 按下先延迟转发，避免上游先发送 Alt 后让 X11 的 Firefox 菜单抢走焦点。确认是粘贴时不转发这个修饰键；其他普通 Command 组合按上游的 Control 快捷键语义转发。Command+A/C 和跨粘贴持续按住 Command 的回归均通过。

用户主动提供的图片由 `ClipboardEvent.clipboardData` 读取，使用 Selkies 原有 WebSocket 剪贴板协议传送，不调用 `navigator.clipboard`，不写本机或远程截图文件。接收 PNG、JPEG、WebP、BMP，单次最多 25 MiB；750 KiB 起分块。图片传递临时启用服务端二进制剪贴板回传，逐字节核对后才发送远程 Control+V。临时设置复制最后实际发送的客户端 SETTINGS，仅变更 `enable_binary_clipboard`，结束时恢复用户当前偏好；不会因重新推导 X11 分辨率设置而带入其他变化。

只允许当前主显示器的控制客户端、开启的双向剪贴板和当前连接。没有确认、断线、焦点或点击位置改变时不自动粘贴；共享只读客户端、禁用的剪贴板和合成事件不会传输图片。粘贴动作只交给网页，代码不按 Enter 或提交表单。Trilium 的权限策略和自动剪贴板同步状态没有改变。

## 固定产物与部署

[安装器](enable-screenshot-paste.py) 只接受固定上游前端 SHA-256 `12d75adb19371bece1fb077efb9bf198a79f03e3e09255b7a310c08fde3bb088`，同时保留先前 Files 可见、下载按钮隐藏的修补。它生成新文件并原子替换 HTML 引用，不覆盖原 JS、不重启服务。未知上游或被修改的当前 JS 会被拒绝。

- 前端资源：`index-native-paste-9af1f4f2e9f39388.js`
- 完整 SHA-256：`9af1f4f2e9f393882897f4230ce3417adcb63defea5f849e33f6dee722d87456`
- 客户端补充脚本 SHA-256：`9a0e1a68741b3a7c02f550a858d77906e462d10270b56ef9e43ad649af609af5`
- 部署目录：`runtime/client-addons/screenshot-paste-v1-8f0fad3d74d97461/`

部署目录包含安装器、客户端代码、[启动 hook](screenshot-paste-init.sh) 和逐文件摘要 `bundle.json`。目录名称摘要取 `bundle.json.files` 的按键排序、紧凑 JSON 的 SHA-256 前 16 位。该目录内容发布后不再修改；升级应生成新目录并重新验收，不覆盖已挂载的版本。

两个应用定义仅在 `provider_config.docker_overrides.mounts` 中增加两项只读 bind mount：

| 内容 | Worker 路径 |
| --- | --- |
| 上述版本化目录 | `/opt/browser-platform/selkies-paste` |
| 目录中的 `screenshot-paste-init.sh` | `/custom-cont-init.d/95-browser-platform-paste` |

这保留了 SealSkin 提供的 Home volumes。镜像、Personal internal 网络、冻结环境、应用权限和其他应用字段保持原值；Camoufox 应用未改变。LinuxServer 的 `init-custom-files` 依赖链在 `init-nginx` 和 `init-selkies-config` 之后，因此静态目录重建后会重新应用补丁。hook 失败会记录错误并保留原页面，不代表整个 Worker 会停止；浏览器环境自身的冻结校验仍由原入口执行。

两个现存旧 Wayland Worker 使用本地 root 所有的相同文件与启动 hook。实际部署只复制文件和执行安装器；既有 `/custom-cont-init.d/90-browser-platform-files` 原样保留。Firefox、labwc、Xwayland、Selkies 的 PID 与启动 ticks、Docker 配置、容器启动时间和 Adapter 绑定均一致。此次截图功能部署没有重现此前 Files 任务中的 Work 串流重载事件。

## 验证与实际边界

[客户端验收脚本](checks/screenshot-paste-client.py) 使用真实 Chromium 系统剪贴板和远程 Firefox [接收页面](checks/screenshot-paste-fixture.html)。测试源 PNG 仅在内存生成；准备剪贴板的 fixture origin 有写权限，实际 Session origin 的读写权限均为 `denied`，且 API 调用实际返回 `NotAllowedError`。成功路径使用浏览器原生粘贴命令，未用合成 ClipboardEvent 代替用户粘贴。

| 验证 | 结果 |
| --- | --- |
| 旧 Firefox Wayland / Personal 代理 X11 | 均通过 |
| 本机与远程原生图片 paste 事件 | `isTrusted=true`，MIME `image/png` |
| 小 PNG 与分块 PNG | 远程尺寸和完整 RGBA 像素 SHA-256 与源图一致 |
| 分块 PNG | 本机粘贴事件及远程 Firefox 接收大小均为 2,470,507 字节 |
| 中文、多行、emoji 原生文字粘贴 | 通过 |
| 原有 Clipboard 面板 Control+V、普通键盘输入 | 通过 |
| Mac 键位模拟：Command+A/C、跨粘贴持续按住 Command | 通过；截图粘贴不发送远程 Alt |
| 截断确认回传并切换焦点 | 没有提前或迟到的自动粘贴 |
| 禁用剪贴板、断线、共享只读客户端、合成事件 | 没有剪贴板写入或粘贴按键 |
| 临时 SETTINGS | 只改变二进制剪贴板选项，恢复原偏好 |
| 新建两个应用的会话 | 只读挂载与正确资源 SHA-256 均通过 |
| 一次性 QA Worker 重启 | 两种桌面均重新生成正确资源，公网 HTML / JS 返回 200 |
| 安装器 | Files 版本升级、幂等、拒绝未知和被篡改资源通过 |
| Trilium 0.105.0 / macOS Sequoia 15.1 | 用户复测截图直接粘贴，确认正常 |

PNG 在 Chromium 系统剪贴板中会重新编码，因此准备源文件的压缩字节数与原生粘贴事件可能不同。测试同时检查完整像素摘要；传到 Selkies 后的确认则逐字节匹配实际粘贴得到的图片。

QA 使用 Chromium 151.0.7922.34 / Linux，通过原生编辑命令在 Linux 上执行带 Meta 修饰键的粘贴，并用客户端 `MacIntel` 平台模拟执行 Selkies 的 Mac 键盘分支。首次补查在 X11 复现了上游 Alt 映射抢走粘贴焦点的问题，最终版本已修正并通过两种桌面的完整回归。这些检查证明了权限被拒绝时的原生图片路径和远程完整性；随后用户的实际 Mac / Trilium 复测补齐了目标客户端的截图验收，但不覆盖 Files 原生文件选择与拖放。自动化验收未连接现有两个用户会话的 WebSocket，也未操作其中网页；公网检查只读取 HTML 与静态资源。一次性 QA Worker、授权 Session 文件已清理。

证据保存在 Git 忽略的目录，备份部署时需单独保留：

- [Wayland 与 Mac 键位端到端验证](runtime/screenshot-paste-wayland-mac-mapping-2026-09-13-release/screenshot-paste.json)
- [Personal 代理 X11 与 Mac 键位端到端验证](runtime/screenshot-paste-x11-mac-mapping-2026-09-13-release/screenshot-paste.json)
- [应用配置、现存 Worker 更新、启动与重启记录](runtime/screenshot-paste-rollout-2026-09-13/)

源码检查可运行：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 infra/sealskin/checks/screenshot-paste-installer.py \
  --frontend infra/camoufox/.build/selkies-client.js
```

## 回滚

现存 Worker 的旧 Files 页面备份在 `/var/lib/browser-platform/screenshot-paste/index.before.html`，主机上另有 `runtime/screenshot-paste-rollout-2026-09-13/{work,personal}.before.html`。将其原子恢复到 `/usr/share/selkies/web/index.html`，移除此次新增的 `95-browser-platform-paste` hook，即可在客户端重新加载后恢复。原 Files hook 保留；静态回滚不需要重载 Selkies。

新会话配置的回滚补丁位于同一私有证据目录中的 `rollback-patches.json`，只恢复原 mounts 列表，保留网络和其他 Docker 配置。管理员 API 的字典深合并会留下空的 mounts 数组，其运行语义与此前没有额外挂载一致。先解除两个应用对版本目录的引用，待使用它的 Worker 都不再需要时再移除部署目录。不要为回滚这个界面功能重启现有用户浏览器。
