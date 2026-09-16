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

生产 Work 使用另一份固定 LinuxServer Firefox/Wayland 镜像，不沿用本目录的 X11 环境产物。R4B 已在该精确旧镜像之上生成正常退出与显示认证候选，并通过控制器停止、s6 停止/resume、入口、错误材料和秘密边界验收；候选尚未替换生产 Work。版本与限制见 [正常退出层](../browser-runtime/README.md) 和 [R4B 阶段验收](../sealskin/target-client-migration-acceptance-2026-09-15.md)。
