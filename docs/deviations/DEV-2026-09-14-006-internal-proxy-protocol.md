# DEV-2026-09-14-006 · 内部转接协议的规格映射

状态：已解决（设计映射与隔离验证，未部署生产）。发现日期：2026-09-14。关联工作项：[R5A](../work-items/R5A-2026-09-14-proxy-protocols.md)。

## 设计预期与实际事实

[规格 45.2](../specs/proxy-environment/specification.md#452-协议认证与转接器) 原图使用内部 HTTP CONNECT；[48.1](../specs/proxy-environment/specification.md#481-网络拓扑与执行边界)、现行 Firefox/Camoufox 配置、Relay 和 Guard 实际使用专属内部 SOCKS5 TCP 1080。已有正常浏览器/受限网络证据验证的是 SOCKS5 路径，不能声称实现了内部 HTTP 监听。

## 影响与处理决定

修订设计的当前实现映射：Worker → 无上游凭据的内部 SOCKS5 CONNECT → Relay → 所声明的 HTTP/HTTPS/SOCKS5 上游。浏览器把网站域名交给 Relay，再原样交上游；内部协议不改变上游认证范围。HTTP/HTTPS 上游对 HTTP、HTTPS、WebSocket 的 TCP 连接统一使用 CONNECT，上游必须允许目标端口；不支持仅接受 absolute-form HTTP 请求的代理。

保留单 Profile 所有权、认证、TLS、DNS 与默认拒绝验收，不因映射改变降低 P02/N 组条件。DIRECT 与原 Chromium 发布要求仍待对应计划完成，不由此修订删除。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 规格 45.2 / 当前设计 | 已明确内部 SOCKS5 映射和 HTTP 上游 CONNECT 语义 |
| Relay / 网络集成 | 六种组合的浏览器 HTTP/HTTPS/WS/WSS 与内部 SOCKS5 请求、上游域名请求已留证；恢复与整体验收继续由 R5A 核对 |
| 进度 / 计划 / 工作项 | R5A 进行中，完整父条件保留 |

## 最终复核

已逐项核对实际 Relay、浏览器配置和受控上游观测，内部 SOCKS5 → 上游 SOCKS5/HTTP(S) CONNECT 的映射一致。规格、设计和组件说明保持同一契约；这不提供内部 HTTP 监听，不替代 DIRECT 或 Chromium 的待交付条件。
