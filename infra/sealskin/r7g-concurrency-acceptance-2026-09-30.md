# R7G · 启动并发、代理更新与停止互斥

日期：2026-09-30。结论：三组真实 API / Docker 检查通过，未修改产品代码或生产部署。固定控制器为 `sha256:37345e2fa5d92379719ffb8398795fb12d115d76e0f583df361e35db8793130a`；Relay/Worker 沿用[恢复验收](r7g-controller-recovery-acceptance-2026-09-30.md)的精确镜像。

| 检查 | 真实结果 |
| --- | --- |
| 两个 Home、每 Home 四个同 operation 启动请求同时到达 | 每 Home 一个 200、三个 409；各只有一个 Session、Worker 和 reservation，两个 endpoint lease ID 不同；HTTPS 可用，四类 Worker 绕过明确拒绝 |
| monitor 正持 Home 锁更新规则时发起 stop | 请求保持等待；该 Home 的 Worker/Relay 仍运行，pending 保留；另一个 Home 的 API 查询和 HTTPS 完成。解除有界 QA gate 后，更新先回滚，正常 stop 返回 204；原 Worker/Relay/Guard 均消失，reservation 与资源清零 |
| 原 Home 停止后创建新代次，再发送旧 stop | 新 operation/Worker/lease，revision 从 1 开始；旧请求返回 409，新 Worker 保持；peer 的 Session、Worker/Guard/Relay ID、PID、StartedAt、镜像与网络模式保持，两个 Home 的连接与绕过拒绝正常 |

运行器为 [check-dynamic-concurrency.py](checks/check-dynamic-concurrency.py)，在 `check-dynamic-upstream.py prepare` 后运行。八个请求使用独立加密会话并在同一 barrier 起跑；结果记录实际响应和时间。monitor 的暂停点来自已证明归属的 Relay 的真实规则调用，最长 30 秒，释放旧调用按失败返回，不迟到应用。没有直接修改 pending、lease 或内核规则来制造成功结果。

本轮复用当前空闲 QA 基础环境：先保存公网准备的策略、应用定义、凭据和 allow 配置，再使用私有 DNS/认证代理夹具。完成后生命周期清理全部代次和三个私有夹具，保存的七份 QA 文件逐字节恢复，两个应用通过完整 PUT 恢复并读回一致，公网 DNS 未改动。公网基础控制器、权威及远端端点仍等待 DEV-084 维护范围答复，不能把本次私有资源清零写成公网已清理或验证通过。

证据在忽略目录 `runtime/r7g-public-20260930/concurrency/`、`private-concurrency-dynamic/` 和 `concurrency-run.log`；`public-restored.json` 保存恢复核对。产品动态 patch 仍匹配已验收 manifest，沿用 140 网络/DNS、557 控制器和 107 QA 工具回归，不重复宣称本轮重跑。

该检查证明限定请求数、两个 Home 与一个真实 monitor/stop 竞争窗口下的互斥和归属保护，不提供容量上限或大规模压力结论。它也不替代公网自然漂移认证、目标客户端或生产维护。R7G 继续旧静态代次的控制器升级/回退兼容及公网/最终发布准备。

本轮最终清理：公网 DNS UDP/TCP 外部复查仍超时，未应用主机规则。随后删除本轮 QA 名称并递增 serial、恢复权威原停止状态；两个公网进程正常停止并精确 purge，基础 QA 容器/网络/代次均清零，显示 tmpfs 移除。本地公网 bundle 的凭据/私钥/归档删除，私有测试证据及退役 Store 密钥保留。IPv4 入站规则与生产快照均保持，见私有 `final-status.json`；公网验收仍为 NOT_RUN。
