# Files 栏开启记录（2026-09-13）

Personal / Work 已提供 **Files → Upload Files**。上传目标为 `/config/Desktop`；用户需再在远程网站选择文件。Mac / Trilium 的原生文件选择尚待用户确认。

随后已叠加[截图直接粘贴](screenshot-paste-acceptance-2026-09-13.md)，无需先保存截图；用户已在 Mac / Trilium 上确认截图测试正常，Files 原生文件选择仍待单独确认。当前前端资源摘要以该记录为准。本文保留 Files 功能初次部署的证据与事件。

当前还包含 [原生反向文字复制](native-copy-acceptance-2026-09-13.md)，完整客户端的最新资源摘要与回滚以该记录为准。

## 生效配置

通过现有加密管理员 API，仅修改 `firefox-personal`、`firefox-work` 应用定义中的两个环境项：

```text
SELKIES_UI_SIDEBAR_SHOW_FILES=true
SELKIES_FILE_TRANSFERS=upload
```

镜像、网络、环境产物、应用权限、Home 和 Adapter 绑定保持原值；独立 `camoufox-personal-r4` 应用未修改。桌面加固、Apps 隐藏与命令禁用继续生效。

两个现存 Worker 仍是旧 Wayland 会话，后续 Personal 新会话的 X11 基线不会自动迁移它们。为使当前页面立即显示上传入口，使用 [静态更新脚本](enable-files-sidebar-live.py) 生成新的带内容摘要的 JS 文件，并原子更新 HTML 引用。脚本只接受已验证的前端 SHA-256，修改 Files 可见性并隐藏下载按钮，未改变后端授权。

新资源为 `index-files-upload-165a23abbbf5bad5.js`，SHA-256 为 `165a23abbbf5bad5b0b1677ab5bdebad4ab72c9c2cf914e7f088baacba77df9d`。原 JS 保留，HTML 备份位于各 Worker 的 `/var/lib/browser-platform/files-sidebar/index.html`。新文件名使刷新后的客户端加载新资源。

[启动 hook](files-sidebar-upload-only.sh) 已安装到两个现存 Worker 的 `/custom-cont-init.d/90-browser-platform-files`，所有者为 root、权限 `0755`；它在桌面加固初始化后写入上述两个 s6 环境项。容器重启时上游会重建静态目录，随后启动的 Selkies 直接采用显式配置。后续新建 Worker 则由应用定义提供配置。

## 验证与重载事件

- 隔离 X11 会话：Files 按钮上传、剪贴板权限 denied、PNG 摘要核对通过；串流重载保留浏览器进程，custom-init 设置经过该隔离容器重启验证。
- 初次更新 Work 时发现，其旧 Wayland 会话的 Selkies 重载会连带重启 Firefox。检查脚本自动回滚该次设置，并停止后续重载。Work 的 Home、Worker 容器和 Session 绑定保留；不能声明整个操作过程中浏览器均未重启。
- 补充独立 `firefox-work` Wayland cleanroom 验证：保持后端原来的 Files 隐藏设置，仅更新静态页面后 Files 与上传按钮可见；通过实际文件选择事件上传 PNG，服务端文件大小和 SHA-256 相符。静态更新前后的 Firefox、labwc、Xwayland 和 Selkies PID／启动时间一致。
- 最终对现存 Work、Personal 的静态更新均未再重启服务。两个固定入口、两个经过公网认证的 Session HTML 和新 JS 均返回 200，JS 摘要符合预期；请求未连接 WebSocket 或操作用户页面。
- Docker 配置、启动时间、镜像、网络、mounts 以及 Adapter 配置与绑定摘要均保持一致。当前入口仍是原 Firefox，未切换到 Camoufox。

证据：[X11 上传与重启](runtime/files-sidebar-acceptance-2026-09-13/image-upload.json)、[Wayland 无重启上传](runtime/files-sidebar-wayland-acceptance-2026-09-13/image-upload.json)、[实际更新记录](runtime/files-sidebar-rollout-2026-09-13/rollout.json)、[公网资源检查](runtime/files-sidebar-rollout-2026-09-13/public-http-checks.json)。QA 使用 Chromium 151 / Linux；临时会话均已清理。这些目录被 Git 忽略，部署备份应单独保留。

## 回滚

应用原始记录及两个环境列表的回滚补丁保存在权限为 `0700` 的 `runtime/files-sidebar-rollout-2026-09-13/`，配置快照文件为 `0600`。通过管理员 API 提交 `rollback-patches.json` 中的环境补丁即可恢复后续 Worker 的设置，不覆盖其他应用字段。

现存 Worker 可将上述 HTML 备份恢复为 `/usr/share/selkies/web/index.html`，并删除本次安装的 custom-init hook；s6 环境文件的原始内容在各 Worker 对应的 `*.before-live.json` 中。静态页面回滚无需重启 Selkies。**不要在旧 Wayland 会话中为这个界面改动重载串流服务**；用户刷新页面即可加载恢复后的版本。
