# R7G1 · 动态代理热切换发布

状态：已收尾并部署。开始/完成：2026-10-02。父项：[R7G](R7G-2026-09-27-dynamic-upstream-hot-switch.md)。

## 授权、范围与完成条件

用户明确要求完成剩余工作并直接部署动态代理；商业供应方尚不可测试。此最新授权替代父项旧的禁止部署条件；自然漂移保持未测，不作为此次发布门槛。R6AP 已收尾（55e2f97），当前仅实施本项。

在精确现用 R6W 控制器上叠加动态能力，保留 R6W 代理授权、R6J1 日志及全部显示/会话 overlay。发布控制器与新建网络策略所用 Relay；既有静态代次及其镜像/配置不转换，真实 Home、Session、凭据和操作日志保持。Adapter 与 runner 不变。

完成条件：源代码差异可重现；完整候选回归、真实认证 DNS 切换/失败关闭、pending 恢复、静态升级和动态清理后回退通过；部署前后现存容器身份/Session/目录/凭据一致；实际安装文件与镜像匹配；文档、回滚入口、恢复增量和 Git 提交完成。

## 代码地图与验证

`prepare.py` 固定上游及五个补丁 → `api.py:lifespan` 启动 monitor → `network_runtime.prepare/restore` capability 分支 → `dynamic_upstream.refresh/_recover_pending` 的同 Home 锁、候选探测和 lease/nft 原子事务 → Relay `endpoint.go/upstream.go` 新连接读取。旧 IP/DIRECT/无 capability 镜像保留静态行为。现存策略拥有 relay_image，须核对新建入口的默认值才算部署生效。

版本基线为 `server-2026.10.02.2` 的 97 个实际安装文件与 R6W 镜像。独立 `prepare-network-qa.py` 资源执行集成；完整控制器测试使用精确候选源码，生产只读保护与有限控制器替换。禁止生产故障注入或重启真实 Worker。私有证据：`infra/sealskin/runtime/r7g1-deployment-20261002/`。

## 文档清单与收尾

更新 R7G/R7G1 工作项及索引、动态设计/规格、生命周期与 Relay README、验收报告与索引、progress/roadmap、剩余执行表、部署/回退说明。历史证据保留；发现偏差立即登记。供应方自然漂移为外部未测范围，不扩充为 PASS。

- [x] 精确源码与回归
- [x] 真实隔离集成、恢复与回退
- [x] 保护部署与实际生效核对
- [x] 文档、恢复材料、Git 与 QA 清理

构建偏差：[DEV-129](../deviations/DEV-2026-10-02-129-relay-apk-version-retention.md)。

收尾：原需求/设计/4 文件实际改动/571 回归/22 实机/保护部署逐项复核通过；DEV-129 已解决，文档和恢复增量完成。详见[部署验收](../../infra/sealskin/r7g1-deployment-acceptance-2026-10-02.md)。供应方自然漂移及此次未做的 GUI 热切换观察保留为外部后续，非本次发布门槛。下一项共享 journald 预算。
