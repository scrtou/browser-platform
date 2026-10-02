# R7G 动态代理端点热切换候选验收（2026-09-27）

状态：隔离 QA 通过；未部署生产。

## 范围

验证候选 `dynamic-upstream.patch` 在固定 SealSkin R6D 上游树中的动态域名路径：控制器刷新批准 DNS 观测，Guard 以旧/新地址集合过渡，Relay 通过原子 endpoint lease 为新连接读取新 IPv4；Worker generation、已建立连接和静态兼容路径保持不变。

动态模式仅在非数值 `upstream_host` 且 Relay 镜像带 `io.browser-platform.dynamic-upstream=1` 时启用。未声明 capability 的镜像继续使用旧的静态冻结地址；DIRECT 和数值 IPv4 不进入动态路径。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| 固定上游树应用补丁 | `git apply --check` 通过；准备器 payload/manifest 包含动态补丁和 `dynamic_upstream.py` |
| Python 编译 | patched QA tree `python3 -m compileall` 通过 |
| SealSkin 网络运行时 + DNS 专项 | 134 passed（运行时动态切换、双 A 轮换、pending 恢复、探测失败回滚、同 IP 保留时刷新 DNS 证据、清理和静态兼容） |
| SealSkin 完整 server/tests | 551 passed，3 个只读挂载 pytest cache warning |
| Relay Go 单元测试 | `go test ./...` 通过（固定 Go 1.27.1） |
| Relay 静态检查 | `go vet ./...` 通过 |
| Guard Python 单元测试 | `relay/test_network_guard.py` 17 passed（checks 镜像） |
| 隔离 Docker/nft 规则过渡 | 临时 privileged Relay namespace（eth0/eth1）中实际执行旧地址 → 双地址 → 新地址三次 `nft --check`/apply；最终规则仅保留新地址；无序地址注入返回失败且旧规则保留 |
| Relay 双上游连接切换 | 固定 Go Relay 二进制连接两个临时 HTTP 代理容器：切换 lease 后新 SOCKS5 连接命中 B，切换前已建立连接继续命中 A（`A → B → A`）；容器、网络和 lease 已清理 |
| Relay Go race | Docker `golang:1.27`（gcc）中 `go test -race ./...` 通过 |

## 故障与回滚边界

- DNS、TCP 预检、Relay `PROXY_OK` 探测或 Guard 应用失败时保留旧 lease/规则；回滚规则失败则停止 Relay，Worker 不获得直连路径。
- 控制器在副作用前持久化 `endpoint.pending`；重启后先恢复旧 lease/旧规则，再接受新刷新。
- Relay 不解析动态域名；lease 缺失、篡改、ID/端口/revision 不符时拒绝新建上游连接。
- 当前证据使用临时 FakeDocker、独立 privileged Docker namespace 和两个模拟 HTTP 代理容器；不代表 Personal/Work 生产部署、真实公网动态 DNS 委派或真实客户端验收。nft QA 验证规则事务和 fail-closed 保留，模拟代理不代表真实公网端点。

## 2026-09-28 增量复验

从干净 R6D 基线重新应用 `dynamic-upstream.patch`，新增真实 UDP wire 夹具双 A 轮换测试：首次回答 `192.0.2.10`（TTL 12），下一次回答 `192.0.2.11`（TTL 27），分别核对 `selected_ipv4`、完整地址集合、TTL、`expires_at` 和两次 UDP 查询事件。固定 checks 镜像中网络/DNS 与运行时专项为 134 passed；完整 `server/tests` 为 551 passed。该夹具验证不等同于真实公网 DNS 委派或客户端验收。

同日对外部公开动态域名样本做只读核对：两台 Cloudflare 权威 NS 与 1.1.1.1、8.8.8.8、9.9.9.9 返回一致的当前 A 记录，权威 TTL 为 120 秒并正常递减；与此前观测地址不同，确认存在地址漂移。该域名不属于本项目或用户，未执行 DNS 修改、代理认证或客户端流量验证，因此不计入热切换客户端验收。

2026-09-29 再次只读观察到供应方自然漂移：两台权威 NS 和三个递归解析器一致返回新的 A 记录，TTL 仍为 120 秒；当前地址的 TCP/60011 可达，上一轮地址不可达。该结果证明外部端点确实会自然变化并且新地址监听代理端口，但未进行 SOCKS5 认证、Worker/Relay 接管或旧连接/新连接对照，因此仍不计入端到端热切换通过。

## 清理与后续

QA 使用临时树和独立测试资源，未启动、停止、重启或修改生产 Personal/Work/Home、Session、账号和凭据。R7G 工作项仍需在供应方自然 A 记录变化时完成端到端客户端观察；nft 实机过渡、失败回滚、模拟双上游切换和 Go race 已完成。R7F 生产发布仍按原顺序，不能由本候选验收代替。


2026-09-30 后续：[真实控制器集成](r7g-controller-integration-acceptance-2026-09-30.md) 已补齐批准 DNS/认证 SOCKS5/双 Worker。该轮发现并修复此前 FakeDocker 未覆盖的停止签名/恢复归属问题（DEV-082）；本报告旧故障测试不代表修复前真实 Docker 已完成停止。用户明确选择先推进 R7G 隔离开发，R7F 待验收条件保持，生产仍未部署。
