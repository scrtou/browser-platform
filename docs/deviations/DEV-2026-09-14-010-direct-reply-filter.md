# DEV-010 · DIRECT 私网拒绝规则误挡 SOCKS5 回包

状态：已解决（代码/独立 QA，未部署）。发现及解决日期：2026-09-14。所属工作项：[R5C1](../work-items/R5C1-2026-09-14-direct-isolation.md)。

DIRECT 仍须允许 Worker 经专属内部 SOCKS5 网关联网，同时拒绝网关主动连接私网目标。核对首个候选的 `network-guard.py` 时发现，DIRECT 的 output 链将私网目标拒绝放在已建立连接放行之前，网关向内网 Worker 返回 SYN-ACK 和 SOCKS5 响应也会被拒绝。原规则字段测试未覆盖真实双向连接；已通过的 Go/Python 测试不能证明这条网络路径可用。

选择修复实现：在私网目标拒绝之前，仅允许发往本代次内网、源端口为 1080、属于已建立连接回复方向的报文。继续拒绝新的私网连接，不改变 Worker 权限、DNS 例外、宿主机地址保护或父验收条件。先以独立 QA 复现，再验证真实 SOCKS5 回包与私网隔离；旧候选镜像和失败证据保留。

证据目录：`infra/sealskin/runtime/r5c1-direct-2026-09-14/`。原复现 `reply-repro-*` 记录预检 503、8 个回包被丢弃且没有 Worker；修复后的 `guard-v1-399a552251bb0c5a` 通过两个正常 Camoufox 的 HTTP/HTTPS/WS/WSS、每套 20 类 SOCKS 目标拒绝、Worker/网关各 19 项绕过和四个命名空间包方向检查。长期进程仍丢弃全部 capabilities，源端口 1080 不能用于主动私网连接。最终结果见 [R5C1 验收](../../infra/sealskin/direct-network-acceptance-2026-09-14.md)。旧失败证据和镜像保留，生产未部署。
