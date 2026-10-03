# Firefox Proxy Worker

[文档导航](../../docs/README.md) · [开发进度](../../docs/progress.md) · [网络生命周期](../sealskin/lifecycle/README.md)

该镜像基于固定摘要的 LinuxServer Firefox，在镜像层锁定浏览器代理设置。Firefox 只连接当前 Profile 网络中的 `profile-relay:1080`，SOCKS5 域名解析交给上游，DoH 和 WebRTC 被关闭。

当前 [environment.json](environment.json) 是原生 Firefox 的台湾基线产物。入口脚本在 `/init` 之前校验文件 SHA-256、环境 ID、locale、languages、timezone 和 1920×1080 屏幕参数；缺失或漂移会让容器退出。固定屏幕目前要求 `PIXELFLUX_WAYLAND=false`，因为本次固定版本的 Wayland/labwc 路径实测始终向页面暴露 1280×720。

当前产物 SHA-256 为 `3213e8aab48de79560ec1d34ff9524d6a517a16e080e1b95066d3c1b6d192d24`。SealSkin 应用定义必须同时设置 `BROWSER_PLATFORM_ARTIFACT_SHA256`；重建或修改产物后先更新不可变版本和摘要，再切换 Profile。

镜像包含内部 Relay 名称和端口，不包含上游代理地址或凭据。静态基线使用 `profile-relay` Docker 网络 alias；受管理 Personal 由 SealSkin 的生命周期补丁分配 Relay，并用固定地址映射该名称，Worker 不能访问 Docker DNS。具体拓扑和凭据边界见 [网络生命周期](../sealskin/lifecycle/README.md)。

```bash
docker build \
  --tag browser-platform/firefox-proxy:env-tw-firefox-baseline-r1 \
  infra/firefox-proxy
```

仅锁定 Firefox 配置还不构成 egress kill switch。静态基线限制 Worker 只接对应 `internal` 网络；受管理 Personal 进一步共享已安装 ACL 的 Guard 命名空间，阻止同网段管理端口访问。不能再加入默认 bridge 或其他具有公网路由的网络。存量会话的实际生效范围见 [开发进度](../../docs/progress.md#deployment)。

生产 Work 使用另一份固定 LinuxServer Firefox/Wayland 镜像，不沿用本目录的 X11 环境产物。R4B 已在该精确旧镜像之上部署正常退出与显示认证层。R7B 发现该兼容镜像本身没有 Relay 锁定配置，因此由 [Work 受管理网络层](../work-firefox-managed/README.md) 以该精确镜像为父层、复用本目录两个权威 Firefox 配置文件生成候选；真实 DIRECT 页面、无绕过、网关故障和三类存储换代恢复已通过，但候选尚未绑定生产。版本与边界见 [R7B 验收](../sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md)。


R6R 新增原生 Firefox155.0.1 的通用模板生成，代码及固定桌面镜像在[environment-engines](../environment-engines/README.md)。它以 `firefox` 目标和独立 `.firefox` Home 登记，不迁移或替换本组件历史 Work/legacy 浏览器。

R6R已限定部署并收尾，完整范围和未验证项见[三引擎验收](../sealskin/r6r-multi-engine-acceptance-2026-10-01.md)。

R6S原生Firefox155自定义产物v3支持共享fixed/DPR1与auto/system，固定模式可用独立小窗口；自动模式按系统DPI返回DPR。此能力不改变原生设备特征，不迁移旧Work Home。见[多引擎组件](../environment-engines/README.md)。
