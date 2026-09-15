# 工作流程指导

[文档导航](README.md) · [当前进度](progress.md) · [开发计划](roadmap.md) · [工作项记录](work-items/README.md) · [设计偏差](deviations/README.md)

每次工作按 **阅读 → 核对代码 → 明确本项范围 → 实施并记录偏差 → 验收复核 → 更新文档、进度和计划 → 结束本项** 的顺序执行。上一项没有完成收尾，不开始下一项计划。此流程适用于开发者和编程助手，仓库入口约定见 [AGENTS.md](../AGENTS.md)。

先确认本次任务范围。只要求编写文档、流程或方案时，按该范围交付和收尾；流程中“开始下一项”是顺序约束，不代表自动扩大本次任务。预读草稿标为待启动，不表示已经开始功能实施。

## 1. 先读文档，确定当前事实

| 顺序 | 阅读内容 | 需要确认的事 |
| --- | --- | --- |
| 1 | [文档导航](README.md)、[开发进度](progress.md) | 最近记录日期、线上版本、现有会话与新会话范围、正在进行的工作项 |
| 2 | [工作项索引](work-items/README.md)、[开发计划](roadmap.md) | 上一项是否收尾，当前优先级、依赖、交付要求和未完成条件 |
| 3 | [开发背景](background.md)、[架构与决策](design.md) | 目标、范围、单一生命周期所有权、Home 独占、网络与凭据边界 |
| 4 | 本项涉及的 [规格](specs/proxy-environment/README.md)、[设计偏差](deviations/README.md) | 要实现的契约、对应验收编号、已知差异与处理结论 |
| 5 | 对应组件 README、[验收索引](acceptance/README.md) 中最新且适用的报告 | 可重复的操作、既有结果、未测范围、部署和回滚限制 |
| 6 | 涉及用户操作时读 [Trilium 指南](trilium-client.md)，涉及部署时读 [运维说明](operations.md) | 用户实际路径、维护影响和恢复方法 |

首次进入项目完整阅读背景与架构；后续任务先看当前事实与变化，再补读相关部分。历史快照只用于追溯，不作为当前执行顺序。源码、线上状态和文档不一致时，先记录证据与适用范围，再决定处理方式。

## 2. 再看代码，从入口跟到实际行为

先用 `git status --short` 确认已有改动，再用 `rg --files` 和 `rg -n` 定位文件、调用方与测试。不要一上来覆盖配置、重建容器或修改真实 Home。

通用阅读顺序：**配置与进程入口 → 请求入口 → 业务状态与归属检查 → 外部调用/实际副作用 → 返回与错误处理 → 测试 → 部署和 QA 工具**。

| 范围 | 建议代码阅读顺序 |
| --- | --- |
| Adapter 启动与配置 | [main.go](../adapter/cmd/profile-adapter/main.go) → [config.go](../adapter/internal/config/config.go) → [service.go](../adapter/internal/profile/service.go) |
| 固定入口与页面 | [HTTP 路由](../adapter/internal/httpapi/server.go) → [Profile 服务](../adapter/internal/profile/service.go) → [SealSkin 客户端](../adapter/internal/sealskin/client.go) → [入口测试](../adapter/internal/httpapi/server_test.go) |
| 入口登录与显示授权 | [访问契约](../infra/sealskin/entry-auth/README.md) → [账号文件/派生值](../adapter/internal/access/users.go)、[登录与交接](../adapter/internal/access/gateway.go) → [当前业务绑定](../adapter/internal/profile/display_access.go) → [HTTP/WebSocket 代理](../adapter/internal/access/proxy.go) → [账号管理](../adapter/cmd/profile-accounts/main.go)、[授权测试](../adapter/internal/access/security_test.go)；再检查版本化 patch 中 Session 密封、`session_runtime`、私有头的 `session_gate`、最终日志/HTTP 错误边界、两层 Caddy 与加密备份 |
| Worker 显示认证与入口 QA | [显示契约](../infra/browser-access/README.md) → [材料验证](../infra/browser-access/session_access.py)、[固定上游安装](../infra/browser-access/install.py) → [真实客户端](../infra/sealskin/checks/entry-auth-client.py)、[运行器](../infra/sealskin/checks/run-entry-auth.py) → [错误材料拒绝](../infra/sealskin/checks/check-entry-worker-rejection.py)、[运行扫描](../infra/sealskin/checks/check-entry-runtime.py)、[清理](../infra/sealskin/checks/cleanup-entry-auth.py) → [发布候选](../infra/sealskin/entry-auth/prepare-release.py)；核对真实入口、恢复、秘密所在路径和失败保留 |
| 占用、停止和恢复 | [状态存储](../adapter/internal/state/store.go) → [生命周期核对](../adapter/internal/profile/lifecycle.go) → [运维 socket](../adapter/internal/control/control.go) → [生命周期 API](../adapter/internal/sealskin/lifecycle.go) → [生命周期测试](../adapter/internal/profile/lifecycle_test.go) |
| 受管理网络与 Guard | [生命周期补丁说明](../infra/sealskin/lifecycle/README.md) → [版本化 patch](../infra/sealskin/lifecycle/profile-lifecycle.patch) → [Guard 初始化器](../relay/network-guard.py) → [网络测试](../adapter/internal/profile/network_test.go) → [真实网络 QA](../infra/sealskin/lifecycle/check-network-live.py) |
| Proxy Relay | [Relay 配置](../relay/internal/proxy/config.go) → [上游选择与 TLS](../relay/internal/proxy/upstream.go) → [CONNECT](../relay/internal/proxy/http.go) → [内部 SOCKS5 与隧道](../relay/internal/proxy/server.go) → [多协议测试](../relay/internal/proxy/protocol_test.go) → [镜像构建](../relay/build-guarded-image.py) |
| 受管理 DIRECT | [DIRECT 契约](../infra/sealskin/lifecycle/direct-network.md) → [生命周期 patch](../infra/sealskin/lifecycle/profile-lifecycle.patch) 中的 `network_direct`、准备/恢复/健康调用链 → [地址与证据校验](../relay/internal/proxy/direct.go)、[DNS 报文解析](../relay/internal/proxy/direct_dns.go) → [Guard](../relay/network-guard.py) → [Adapter 初始页与绑定](../adapter/internal/profile/service.go)、[出站健康](../adapter/internal/profile/health.go) → [实际双 Home QA](../infra/sealskin/checks/check-direct-network.py) |
| 运行时一致性 | [契约](../infra/sealskin/lifecycle/runtime-coherence.md) → patch 中 `coherence_policy/report/runtime/exec`、`browser_observe` 及 launch/resume/Session gate → [Relay 门槛](../relay/internal/proxy/coherence.go) → [Adapter 发放与报告](../adapter/internal/profile/coherence.go)、[加密客户端](../adapter/internal/sealskin/coherence.go) → [固定入口 QA](../infra/sealskin/checks/check-coherence-entry.py)、[故障/恢复](../infra/sealskin/checks/check-coherence-recovery.py)、[隔离](../infra/sealskin/checks/check-coherence-isolation.py)、[双 Profile 轮换](../infra/sealskin/checks/check-coherence-rotation.py)；核对实际页面、完整绑定、到期/故障阻断和历史原子更新 |
| 代理引导 DNS 与 TTL | [DNS 契约](../infra/sealskin/lifecycle/bootstrap-dns.md) → [生命周期 patch](../infra/sealskin/lifecycle/profile-lifecycle.patch) 的 `network_dns` / prepare / reservation / resume → [依赖锁](../infra/sealskin/lifecycle/python-dependencies.json)、[准备器](../infra/sealskin/lifecycle/prepare.py)、[安装器](../infra/sealskin/lifecycle/install.py) → [引导 QA](../infra/sealskin/checks/check-bootstrap-dns.py)、[公开采样](../infra/sealskin/checks/check-public-dns-ttl.py)与[证据检查](../infra/sealskin/checks/test_public_dns_ttl.py) → [精确递归入口](../infra/sealskin/checks/public-dns-authority/dispatch.py)及[实际入口检查](../infra/sealskin/checks/public-dns-authority/check-dispatch.py) |
| 公开 DNS 测试端点 | [端点说明](../infra/sealskin/checks/public-dns-endpoint/README.md) → [打包器](../infra/sealskin/checks/public-dns-endpoint/prepare.py)、[受限网站/代理](../infra/sealskin/checks/public-dns-endpoint/endpoint.py)、[协议检查](../infra/sealskin/checks/public-dns-endpoint/check.py)、[精确部署管理](../infra/sealskin/checks/public-dns-endpoint/manage.py) → [正常浏览器](../infra/sealskin/checks/check-public-dns-browser.py)、[持续连接/失败页](../infra/sealskin/checks/check-public-dns-fault.py) → [DIRECT DNS wire](../infra/sealskin/checks/public-dns-wire.py)、[跨重启网桥](../infra/sealskin/checks/public-dns-bridge-wire.py)及[帧/清理检查](../infra/sealskin/checks/check-public-dns-bridge.py)；分别核对网络内容与资源清理 |
| Secret Store 与加密恢复 | [存储契约与操作](../infra/sealskin/lifecycle/secret-store.md) → [版本化 patch](../infra/sealskin/lifecycle/profile-lifecycle.patch) 中的 `secret_store` / `secret_runtime` 与启动/停止/恢复调用链 → [Relay 租约](../relay/internal/proxy/lease.go) → [加密备份](../infra/sealskin/lifecycle/secure-backup.py)、[原格式测试](../infra/sealskin/lifecycle/test_secure_backup.py)、[旧格式与 CLI 测试](../infra/sealskin/lifecycle/test_secure_backup_legacy.py) → [真实凭据检查](../infra/sealskin/checks/check-secret-store.py)、[新环境恢复](../infra/sealskin/checks/check-secret-backup.py)；旧生产另核对 Adapter 可选 journal 身份、控制 socket 的归属验证与精确 Home 挂载，再读 [维护准备](../infra/sealskin/ADMIN-linger-and-boot.md) |
| 浏览器正常退出 | [退出层说明](../infra/browser-runtime/README.md) → [X11 关闭与进程确认](../infra/browser-runtime/browser-shutdown.py) → [s6 服务图安装](../infra/browser-runtime/install.py) → [生命周期 patch](../infra/sealskin/lifecycle/profile-lifecycle.patch) → [真实关闭与存储检查](../infra/sealskin/checks/check-browser-shutdown.py) |
| Firefox 环境 | [Worker 说明](../infra/firefox-proxy/README.md) → 该目录的 Dockerfile、入口与配置 → [浏览器网络检查](../infra/sealskin/checks/check-network-browser.py) |
| Camoufox | [组件说明](../infra/camoufox/README.md) → 按说明定位构建、冻结产物、启动校验与重放代码 → [已有验收](../infra/camoufox/acceptance-2026-09-12.md) |
| 截图与反向复制 | [客户端说明](trilium-client.md) → 对应 [验收记录](acceptance/README.md) → [截图安装器](../infra/sealskin/checks/screenshot-paste-installer.py)、[截图 QA](../infra/sealskin/checks/screenshot-paste-client.py)、[反向复制 QA](../infra/sealskin/checks/native-copy-client.py) → 记录所指的版本化客户端代码 |

SealSkin 修改以版本化 patch 和固定上游摘要为依据。需要阅读展开后的 Python 源码时，在独立目录按准备器生成，不把运行容器里的临时修改当成唯一实现。

阅读后在工作项中记下真实调用链、哪些部分已经实现、哪些只有规格，以及需要保留的行为。不要把 `healthz`、容器 running、`network_phase` 或一次 HTTP 200 等同于完整运行健康。

## 3. 建立一个可验收的工作项

在 [docs/work-items/](work-items/README.md) 用 [模板](work-items/template.md) 创建记录，名称使用 `计划编号-日期-主题.md`，并登记索引。

开始实施前写明：对应计划、目标/范围、设计与代码入口、完成条件、验证环境、已有改动、偏差记录位置、部署影响和需要更新的文档。然后将进度与计划中的当前工作标为进行中。

一个大计划可以预先拆成顺序明确的子项，但必须公开保留父计划尚未完成的条件；不得在测试失败后偷偷缩小范围。当前项未收尾时，独立分析与必要准备可以继续，不能切换到下一项功能实施。

## 4. 实施过程中及时记录偏差

发现差异后，先在 [docs/deviations/](deviations/README.md) 建立记录并链接工作项，再继续依赖该决定的修改。记录应包含设计预期、实测/源码事实、证据位置、影响、处理方案和需要更新的文档。

| 情况 | 处理方式 |
| --- | --- |
| 实现违反仍有效的设计 | 按设计修复代码/配置，保留失败与修复证据 |
| 设计与当前技术事实或已有决策冲突 | 说明原因与权衡，先明确采用的契约，再同步设计、规格和计划 |
| 只是计划中的能力尚未实现 | 在工作项中记录缺口；不自动把正常待办称为设计偏差 |
| 证据不足，尚不能判断 | 标记待核对，保留 unknown 和现有占用；不能宣称通过 |
| 涉及范围、数据处理或维护影响的实质变化 | 完成可独立进行的分析与准备，按现有授权处理需要用户决定的部分；等待期间记录状态 |

每次确定处理方式就更新相关文档，不把全部差异留到实施结束才补写。偏差记录保留事实与决策历史，不用“修改设计”掩盖未通过的验收。

## 5. 实施后再次核对与验证

逐条比较 **原始任务 → 计划完成条件 → 设计/规格 → 代码与配置 → 实际运行结果**，确认没有遗漏要求，也没有把 QA 结果扩大为生产或用户已验证。

- 执行与变更相称的检查。代码行为变更覆盖必要的正常、失败、并发/恢复路径；纯文档或低影响可逆修改使用静态检查，不机械新增测试。
- 外部调用与状态变更要核对超时、失败、幂等、归属和数据保留；涉及网络必须验证无直连回退，不能只看网页结果。
- 需要真实运行证据时使用独立 QA 资源，并记录清理结果。生产部署与用户客户端复测分别记录；未部署或未测保持明确状态。
- 验收报告写明版本/摘要、环境、场景、结果、范围与回滚入口，按 [验收规则](acceptance/README.md) 保存脱敏证据。
- 检查 `git diff --check`、文档相对链接/锚点、示例与代码的一致性，以及是否意外修改其他工作。

## 6. 更新文档、进度与计划，再结束本项

| 必须核对的材料 | 更新内容 |
| --- | --- |
| 设计、规格、组件 README | 最终行为、契约、操作与限制；不适用时写明没有变化 |
| 偏差记录与索引 | 最终处理、验证、状态及关联文档；未处理项仍保持打开 |
| 验收报告与索引 | 实际结果及证据范围；失败和未测不能填 PASS |
| [开发进度](progress.md) | 本项完成到代码/QA/部署/用户验证中的哪一步，当前生效范围 |
| [开发计划](roadmap.md) | 已完成条件、剩余工作、依赖与下一项；保留父计划未完成条件 |
| 工作项与索引 | 收尾检查结果、明确未完成项、下一项是否具备开始条件 |

只有本项约定的完成条件达到、影响交付的偏差处理完毕、证据和文档更新完成，才将工作项标为 **已收尾**。若交付范围仅是设计或离线实现，记录这一范围；不能把未部署版本写成线上完成。

条件未达到则保持 **进行中 / 待验证 / 待外部条件**，说明缺口与继续步骤，不开始下一项计划。收尾后，从更新后的进度、计划和工作项索引重新选取下一项，而不是沿用过期清单。

本次仅建立流程的执行示例见 [流程落地记录](work-items/DOCS-2026-09-13-workflow.md)；R1 功能计划保持待启动。
