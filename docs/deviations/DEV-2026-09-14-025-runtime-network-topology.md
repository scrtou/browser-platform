# DEV-025 · 运行中网络拓扑漂移未必触发实例暂停

状态：已修复并通过隔离验收（候选 4；未部署生产）。工作项：[R5C3](../work-items/R5C3-2026-09-14-runtime-coherence.md)。

预期：实际出口绕过或隔离边界改变时，先关闭网站门槛并暂停精确 QA Worker，保留 Home 和故障状态；不能仅关闭已被绕过的 Relay。

源码事实：候选 3 的 `network_facts()` 核对 Worker namespace、能力和 nft 摘要，但没有逐次检查 Guard 必须只连接本代次 internal 网络、Relay 必须只连接 internal/egress。Guard 的固定 inspector 在发现额外网卡时拒绝执行；该异常会进入普通 UNKNOWN 分支，可能不执行暂停。恢复路径已有拓扑检查，不能替代运行中检查。

处理：按设计修复。先保存候选 3 的独立 QA 故障证据，再为采样增加实际网络 ID、地址、隔离属性和资源归属检查；已证实的漂移返回必需 FAIL 并暂停精确 Worker，不把 inspector 异常当作隔离已生效。发现故障后先恢复 QA 网络限制，再正常停止；不操作生产容器。使用新固定候选保存修复后的验收，原候选和结果不改写。

待验证：额外 egress 的实际 HTTPS 绕过、修复后 UNHEALTHY/暂停、后续 UNKNOWN 不清除故障，以及规则漂移与正常采样回归。详细材料放在被忽略的 R5C3 runtime 目录。影响运行时契约、规格 H04、工作项与验收报告。

候选 3 的真实结果：`topology-fault-2/result.json` 为 `CONFIRMED_GAP`。原生 socket 直接完成受控 HTTPS，控制器返回 UNKNOWN / allowed=false，但未自动暂停；测试工具立即暂停 QA Worker、恢复原拓扑和规则后正常停止，清理 PASS。第一轮请求缺少 Host 端口而未取得 HTTP 响应，作为 FAILED 保留。修复已加入额外网卡、地址/ID、IPv6、归属和外来成员的 15 类拒绝测试，等待候选 4 实测。

修复验收：候选 4 `topology-fault-1/` 再次实际完成受控 HTTPS 绕过，控制器确认拓扑漂移后自动暂停精确 Worker，返回 UNHEALTHY / allowed=false；后续 UNKNOWN 保留故障。`rules-fault-1/` 仅改变 nft、仍无公网路由，也正确暂停。两项都在 Worker 保持 paused 时恢复原网络和规则，再经正常生命周期停止，清理 PASS。详细证据均位于被忽略的 `infra/sealskin/runtime/r5c3-coherence-2026-09-14/`，不代表生产已更新。

最终候选 6 `topology-fault-1/` 再次确认真实 HTTPS 绕过、自动暂停、故障保留以及先恢复限制后正常停止，清理 PASS；仅规则漂移仍按上述候选 4 证据引用。
