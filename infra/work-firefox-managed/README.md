# Work Firefox 受管理网络层

[文档导航](../../docs/README.md) · [Work 受管理出网工作项](../../docs/work-items/R7B-2026-09-21-managed-work-egress.md) · [Firefox Proxy](../firefox-proxy/README.md)

本目录在精确、已验收的 Work Firefox/Wayland 退出与显示认证镜像之上增加最小网络配置层，不更换 Firefox、桌面、Selkies、正常退出或显示认证实现。Firefox 被锁定为只连接当前 generation 的 `profile-relay:1080` SOCKS5，域名解析交给 Relay，禁用 DoH 和 WebRTC 直连候选。Worker 仍必须共享 Guard 网络命名空间；浏览器配置本身不能替代 Guard 的 fail-closed 规则。

构建器只接受本机完整 `sha256:` image ID，要求父镜像已有正常退出和 Session 显示认证标签，离线构建后核对父层前缀并生成不可覆盖的输入摘要标签。网络配置复用 [Firefox Proxy](../firefox-proxy/README.md) 的权威文件，临时构建上下文只包含 Dockerfile 与这两个公开配置，不向 Docker daemon 发送仓库运行目录或秘密材料。

```bash
python3 infra/work-firefox-managed/build-image.py \
  --base-image sha256:ec848635e68db2d1c805fcf9972ef4586bcd86a9ed14b2075b0c5a40fbbc503f \
  --tag-prefix browser-platform/firefox:work-wayland-managed-r1 \
  --output infra/sealskin/runtime/r7b-work-egress-2026-09-21/work-managed-image.json
```

产物只是候选镜像；必须再通过 R7B 的独立 Firefox/Wayland DIRECT 验收，并在 R7F 固定发布包、回退和生产维护门槛内绑定，不能直接替换运行中的应用。
