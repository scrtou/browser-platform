# DEV-013 · QA TLS 握手阻塞接收循环

状态：已解决（QA 工具与隔离复测）。关联 [R5C2](../work-items/R5C2-2026-09-14-approved-dns-ttl.md)。发现/解决日期：2026-09-14。

## 预期与事实

私有 Observer 应能接收独立 HTTPS/DoH/HTTPS CONNECT 检查，沉默的 TLS 客户端不应挡住其他请求。`network-observer.py` 将监听 socket 直接包装成 `SSLSocket`，默认在 `accept()` 内同步握手；即使 HTTP 服务使用 ThreadingHTTPServer，握手仍先于请求线程，且没有独立超时。

R5C2 DIRECT 回归出现一次 DoH fetch 超时：DNS 回答已到达，Observer 没有对应 HTTP 请求。随后相同浏览器的有界 DoH 诊断成功。进一步在现有 QA Observer 内复现：先确认正常 TLS，再保持一个仅建立 TCP 的连接，第二个正常 TLS 握手在 1 秒后超时。证据为私有 `direct-regression/dns_faults-1/`、`direct-doh-diagnostic.json` 和 `observer-handshake-before.json`；不是生产流量或正式公开 DNS 证据。

## 处理

选择修复 QA 实现：监听 socket 保持普通 TCP，接受后包装但不立即握手，在各自请求线程中完成 TLS；握手最多 5 秒，之后的 QA 请求 socket 最多空闲 30 秒。覆盖 HTTPS、IPv6 HTTPS、DoT 和 HTTPS 上游监听。新增真实 TLS 并发检查，并在独立 Observer 重启后重跑失败阶段和相关正常浏览器路径，保留首轮失败。

不改变产品 Relay/Worker 的网络 ACL、凭据或超时契约，不降低 DoH 和网络验收条件。两个真实 TLS 测试通过，覆盖 HTTP/TCP 两类服务的并发握手与沉默连接到期关闭；原 QA Observer 重启后，同一复现中的第二个 TLS 握手约 4 ms 成功。最终候选的 DIRECT DoH、DNS 故障、存储恢复及完整引导 DNS 浏览器检查通过。

后续证据为私有 `observer-handshake-after.json`、`direct-regression-final/` 和 `bootstrap-final/`，见 [阶段报告](../../infra/sealskin/approved-dns-ttl-acceptance-2026-09-14.md)。首轮失败继续保留；这不补齐公开 DNS 委派/递归/TTL 的外部条件。
