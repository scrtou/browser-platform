# R7G · 动态端点与 Secret Store 组合验收

日期：2026-09-30。结论：三组真实 QA 检查通过，产品源码未变，未部署生产。控制器、Relay 和 Worker 使用[恢复验收](r7g-controller-recovery-acceptance-2026-09-30.md)的相同精确镜像；本轮新建独立加密 Store、密钥、授权版本和 tmpfs。

| 场景 | 实测结果 |
| --- | --- |
| 两个动态 Home 使用 Secret Store | 每个 Home 使用独立授权的 secret ID 与专属 tmpfs 目录；Relay 只读挂载，目录 0700、凭据文件 0600；Worker 不挂载凭据，Worker/Relay 均不挂载 Store/主密钥，容器配置和 reservation 不含凭据值 |
| 真实 DNS/监视器切换端点 | 两个 Home 从 A/revision 1 切到 B/revision 2；凭据目录及 credential lease 字节摘要不变，endpoint lease 独立更新；原 HTTPS 连接与新连接正常，Session/Worker/Guard/Relay 进程身份保持，四类绕过拒绝 |
| monitor 持 Home 锁时撤销其中一个 secret | 先持久化撤销并把 credential lease 改为 revoked，Relay 在清理取得 Home 锁前退出，原长连接实际 EOF/客户端退出，Worker 绕过被拒绝；另一个 Home 仍可连接。解除有界 gate 后撤销返回 200，`egress_blocked`、`cleanup_complete` 均为 true，目标代次和凭据目录消失；原引用重新启动返回 409 `SECRET_REVOKED`，peer 租约与连接保持 |

运行器为 [check-dynamic-secrets.py](checks/check-dynamic-secrets.py)。它复用私有动态 DNS/认证代理夹具，以已固定摘要的 `secret_store.py` 初始化和写入 QA Store，通过真实管理撤销 API 执行故障关闭。未读取生产凭据，也未直接修改 tombstone、credential lease、endpoint lease 或 pending 来制造结果。

两种租约职责分别核对：endpoint lease 控制新连接选择哪个上游地址；credential lease 控制该代次是否仍获准出站。动态 monitor 持锁时，撤销仍须先使凭据租约失效并关闭 Relay；等待 Home 锁的只是正常清理，不能因此延迟阻断。测试使用真实规则调用 gate，释放旧调用按失败返回，不能迟到应用。

全部代次和私有代理/DNS 夹具经生命周期清理，凭据 tmpfs 确认空后卸载移除。QA 控制器恢复原四个挂载，公网准备的策略/应用/凭据/allow 配置恢复；本轮 Store、密钥、撤销记录离线保留于忽略目录，不混入公网策略或生产。该保留是私有 QA 证据，不宣称密钥已销毁。

证据根为忽略目录 `runtime/r7g-public-20260930/secret-combination/`、`private-secret-dynamic/` 和对应运行/恢复日志；`store-cleanup.json` 与 `public-restored.json` 保存收尾结果。重启拒绝产生的失败启动日志通过其新 operation 精确清理，未借用旧代次的 stop 请求。

本轮没有修改产品代码，仍使用已通过 140 网络/DNS、557 控制器、107 QA 工具回归的候选，不声称重复运行全量回归。自动化客户端在真实浏览器 Worker 中运行，未进行 GUI 或目标 Mac/Trilium 验收。结果不替代生产 Home/Store 迁移、加密备份/异机恢复或公网商业供应方自然漂移。

R7G 公网认证和最终发布材料仍未完成；DEV-084 的主机入站维护范围继续等待答复，客户端按用户要求暂缓。

本轮最终清理：公网 DNS UDP/TCP 外部复查仍超时，未应用主机规则。随后删除本轮 QA 名称并递增 serial、恢复权威原停止状态；两个公网进程正常停止并精确 purge，基础 QA 容器/网络/代次均清零，显示 tmpfs 移除。本地公网 bundle 的凭据/私钥/归档删除，私有测试证据及退役 Store 密钥保留。IPv4 入站规则与生产快照均保持，见私有 `final-status.json`；公网验收仍为 NOT_RUN。
