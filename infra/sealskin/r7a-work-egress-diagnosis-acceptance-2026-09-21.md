# R7A · Work 分层出网诊断与健康模型验收 — 2026-09-21

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R7A 工作项](../../docs/work-items/R7A-2026-09-21-work-egress-diagnosis.md) · [R7 v4](../../docs/browser-workspace-plan.md) · [DEV-061](../../docs/deviations/DEV-2026-09-20-061-work-egress-unobserved.md)

日期：2026-09-21，UTC。状态：**代码、只读生产诊断与隔离自动化通过，未部署生产**。本项没有停止、启动或重建浏览器，没有修改 Home、Profile 目录、账号、Session、应用或网络策略。

## 版本与范围

| 对象 | 版本 / 证据 |
| --- | --- |
| Adapter 源码 | 工作区 `health.go` SHA-256 `fbe89695…`；新增未管理出站语义及回归测试 |
| 工具链 | 固定 Go 1.27.1；race 使用既有 checks 镜像 `sha256:ac6c880d…`、只读源码、无网络 |
| 运行时证据 | 被忽略目录 `infra/sealskin/runtime/r7-design-2026-09-20/` 的 Work inspect、health、拓扑与 IPv4 路由；2026-09-21 再从运行 Adapter 私有 socket 只读复核 |
| 生产影响 | 无；当前运行二进制仍为 R6H `fe4e13c4…`，本候选未安装 |

## 诊断结论

2026-09-20 运行时证据显示 Work 为 1 record / 1 Worker、浏览器和显示通过，但没有 network policy、Relay、Guard 或受管理网络资源；Worker 只连接 internal bridge，IPv4 路由表没有默认路由。因此原报告中的 `healthy + PROXY_NOT_CONFIGURED` 只证明进程与显示，不证明 DNS、HTTPS 或公网出口。

2026-09-21 复核时 Work 已由此前管理动作停用并安全停止，当前为 0 record / 0 Worker / 0 resource，健康状态 `offline / PROFILE_STOPPED`；本项没有重新启动不受管理的旧代次。停止前的运行证据仍用于确认旧健康语义，当前停止态用于确认没有生产占用。

## 实现与结果

- 没有策略的运行代次现在报告 `network_mode=unmanaged`。
- `proxy` 保持 `not_applicable / PROXY_NOT_CONFIGURED`，同时新增非必需但降级的 `egress=warn / EGRESS_NOT_CONFIGURED`；浏览器和显示正常时整体为 `degraded`，不再是 `healthy`。
- 配置已指向新策略但当前代次尚未采用时，新增 `EGRESS_UNMANAGED_GENERATION`，保持下一代次生效语义。
- 恢复提示说明运行/显示与公网连通性分开，并要求从已验收代理或受管理 DIRECT 中选择；提示不自动停止、启动或应用网络。
- 浏览器退出、显示故障、Guard/namespace 故障和实际代理/DIRECT 故障继续优先于未配置提示。

## 自动化

| 检查 | 结果 |
| --- | --- |
| `go test ./...` | PASS，全部 Adapter 包 |
| `go vet ./...` | PASS |
| `gofmt -l .` | PASS，无输出 |
| `go test -race -p 1 -count=1 ./internal/profile ./internal/httpapi ./internal/control` | PASS；离线 checks 镜像中运行 |
| `git diff --check` | PASS |

新增/修订测试覆盖：未管理运行代次降级、稳定失败码、公开报告脱敏、零 Stop/Launch 副作用、旧代次尚未采用策略、管理摘要继承状态、停用但仍运行的生命周期兼容，以及控制面恢复后仍不误报 healthy。

## 未测与下一步

本项没有为 Work 建立公网路径，没有执行浏览器导航、DNS/TCP/TLS/HTTPS 探针，也没有部署候选。R7B 需要在隔离 QA 中选择并验收受管理 DIRECT 或独立代理策略，证明无直连回退、停止/重建与 Home 保持后，才可在授权发布阶段应用到生产 Work。
