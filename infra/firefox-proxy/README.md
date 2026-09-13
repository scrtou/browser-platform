# Firefox Proxy Worker

该镜像基于固定摘要的 LinuxServer Firefox，在镜像层锁定浏览器代理设置。Firefox 只连接当前 Profile 网络中的 `profile-relay:1080`，SOCKS5 域名解析交给上游，DoH 和 WebRTC 被关闭。

当前 [environment.json](environment.json) 是原生 Firefox 的台湾基线产物。入口脚本在 `/init` 之前校验文件 SHA-256、环境 ID、locale、languages、timezone 和 1920×1080 屏幕参数；缺失或漂移会让容器退出。固定屏幕目前要求 `PIXELFLUX_WAYLAND=false`，因为本次固定版本的 Wayland/labwc 路径实测始终向页面暴露 1280×720。

当前产物 SHA-256 为 `3213e8aab48de79560ec1d34ff9524d6a517a16e080e1b95066d3c1b6d192d24`。SealSkin 应用定义必须同时设置 `BROWSER_PLATFORM_ARTIFACT_SHA256`；重建或修改产物后先更新不可变版本和摘要，再切换 Profile。

镜像包含内部 Relay alias 和端口，不包含上游代理地址或凭据。不同 Profile 在各自的 Docker `internal` 网络内使用相同的 `profile-relay` DNS alias；实际 Relay 和 Secret 由 SealSkin 外部的 Profile 网络编排提供。

```bash
docker build \
  --tag browser-platform/firefox-proxy:env-tw-firefox-baseline-r1 \
  infra/firefox-proxy
```

仅锁定 Firefox 配置还不构成 egress kill switch。Worker 必须只加入对应的 `internal` Profile 网络；不能再加入默认 bridge 或其他具有公网路由的网络。
