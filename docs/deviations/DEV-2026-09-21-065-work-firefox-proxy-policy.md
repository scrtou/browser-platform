# DEV-065 · Work Firefox 镜像缺少受管理代理配置

状态：已解决（候选实现与隔离验收；未部署生产）。日期：2026-09-21。
关联：[R7B](../work-items/R7B-2026-09-21-managed-work-egress.md)、[DEV-061](DEV-2026-09-20-061-work-egress-unobserved.md)。

R7B 第四轮隔离 QA 已证明 DIRECT Relay、Guard、Worker namespace 和经 Relay 的 HTTPS 探针均为通过，但生产兼容 Work Firefox 导航公网返回浏览器错误。只读核对 Worker Profile 和应用定义确认：现行 Work 兼容镜像及其只读挂载没有 Firefox SOCKS 配置。即使为应用绑定受管理策略，浏览器仍尝试直连；Guard 正确 fail-closed，因此页面不能访问公网。

这补充了 DEV-061 的根因：旧 Work 不仅没有 network policy / Relay / Guard，也没有让浏览器只使用 generation Relay 的配置。不能通过给 Worker 增加公网 bridge、放宽 Guard 或复用 Personal Home/镜像来绕过。

决定：新增最小 Work Firefox 受管理网络层，以已验收的精确 Work Wayland/正常退出/显示认证镜像为父层，只加入与现行 Firefox Proxy 相同的锁定配置：`profile-relay:1080` SOCKS5、远端 DNS、禁用 DoH 与 WebRTC 直连候选。离线构建器要求完整 image ID、父镜像能力标签、父层前缀和内容摘要，临时上下文不包含运行目录或秘密。候选仍须通过独立 DIRECT 公网页面、无绕过、网关故障、正常停止、换代持久化和清理验收；生产绑定只在 R7F 发布门槛内执行。

最终结果：固定候选 `sha256:895907b7…` 的第六轮全部检查和 QA 清理通过；生产 Work 仍使用旧定义且保持停止。偏差按“候选实现”解决，线上生效范围明确留给 R7F。
