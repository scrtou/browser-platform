# DEV-2026-09-13-003 · IPv6 抓包方向归属

状态：已解决（2026-09-14，采集修复与完整重跑通过）。工作项：[R4A](../work-items/R4A-2026-09-13-client-migration-qa.md)。

预期：网络验收的出站记录只包含 Worker 命名空间实际发出的包；所有实际网站出站仍必须满足 Relay TCP/显示回复白名单，IPv6 不可放行。

事实：Camoufox 受管理网络的功能、拒绝计数和故障用例通过，但最终包元数据断言失败，记录了一条链路本地源到 `ff02::2` 的 ICMPv6。`network-wire.py` 使用 AF_PACKET `recv()`；IPv4 检查源为 Worker IPv4，IPv6 没有来源或收发方向检查，因此收到的链路组播也会被写入 `outbound`。QA Guard 的 `/proc/net/if_inet6` 仅有 loopback，尚需用内核提供的包方向完成归属复核。

私有证据：`infra/sealskin/runtime/r4-client-migration-2026-09-13/browser-wire.jsonl`、`check-network.log`、`wire-origin-check.json`。本次失败证据保留；不修改旧验收报告的当时结论。

处理：采集工具改用 AF_PACKET `sll_pkttype == PACKET_OUTGOING` 归属出站，收到的 IPv6 保留在 `receivedIPv6`。受控独立 QA sender 发出的 3 个组播报文被标记为 packetType=2，修复后均记为收到、没有误算为出站。原失败包没有保存方向字段，无法追认其来源；旧失败证据完整保留。

复核：`wire-direction-controlled.jsonl` 保存受控方向验证；`network-v2/browser-network-results.json` 的 11 项正常 Camoufox 检查全部通过，`network-v2/browser-wire.jsonl` 的 84 条出站流全部满足原白名单，同时另记收到的 IPv6 组播。没有放宽 IPv6 或网站出站断言，隔离实现未改。见 [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md#camoufox-网络)；生命周期 QA 说明与验收索引已同步。
