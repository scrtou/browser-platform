# R6E · 自定义指纹生成与验收作业

状态：已收尾（候选，未部署）。开始日期：2026-09-18。结束日期：2026-09-19。

## 目标与范围

- 用户要求 / 对应计划：[R6 远程浏览器管理面](R6-2026-09-16-environment-management.md)、[管理面规格第 2 版](../specs/proxy-environment/management.md#指纹配置)、[环境规格 46.2/46.3](../specs/proxy-environment/specification.md#462-高层字段与引擎能力)、[R6 计划](../roadmap.md#r6)（第 5 步）。
- 本项交付：管理员只提交高层字段（locale、languages、timezone、screen、DPR、window）；服务端在隔离容器中一次生成完整产物，再执行完整 `acceptance.py --phase all --recreations 10`；通过后产物与报告以 `source=custom`、`status=accepted` 追加进环境目录并可绑定到新浏览器；失败保留报告与失败码、不发布。一次只运行一个作业；主机可用内存不足时排队并提示。
- 明确不在本项：`geolocation=from_proxy_on_create`、非 Linux `osFamily`、DPR≠1（当前适配器只验证 X11/DPR 1，按 `UNSUPPORTED_CAPABILITY` 拒绝）；真实客户端/生产组合（R6F）。
- 验证范围：Go 单元/HTTP 测试、主机 Python 单元测试（fake 执行器）、以及一次真实隔离作业（固定 r9 镜像、独立 QA 网络与 QA 代理夹具、10 次重建）；不操作生产二进制、真实 Home、Session 或生产环境目录。
- 前置项及其收尾记录：[R6D](R6D-2026-09-18-proxy-drafts.md) 已于 2026-09-18 收尾并提交（`4546423`）。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [Camoufox 组件说明](../../infra/camoufox/README.md)、`environment.py generate`、`acceptance.py` | 生成只在固定镜像内运行一次 BrowserForge，产物原子创建拒绝覆盖；完整验收需要内部 QA 网络上名为 `profile-relay` 的 SOCKS5 夹具（R4B `window-r8/run-replay.py` 与 `checks/qa-artifact-proxy.py`），10 次重建约 3 分钟；报告 `status=pass`/`phase=all` 才能被正常 Worker 接受。 |
| 固定生成器（镜像内 `camoufox/fingerprints.py`） | BrowserForge 的 Screen 约束是尽力而为：12 次抽样有 1 次得到 1600×900 而非请求的 1920×1080，此时 `environment.py` 以 `ENVIRONMENT_SPEC_MISMATCH` 拒绝产物；作业执行器需有界重试生成而不是修改产物。 |
| `adapter/internal/profile/management.go`（R6C 目录） | `validAcceptedArtifact` 与 `validateDefinition` 只接受 `source=frozen`，需放开为 `frozen|custom`；`FileEnvironmentCatalog` 每次读取文件，不缓存。 |
| Adapter 进程边界 | Adapter 是主机 systemd 用户服务，不使用 Docker；SealSkin 是唯一 Worker/Home 生命周期所有者；现有验收工具在主机以 Docker 组权限运行一次性 QA 容器。 |
| 已有工作区改动、运行版本 | 开始时工作区干净（`4546423`）；生产 Adapter 仍为 candidate-4。 |

## 实施与偏差

设计决定（实施前）：

1. 作业由独立的主机端执行器 `infra/camoufox/environment-job.py` 执行（与 `acceptance.py` 同样的 Docker 组权限、同样的固定镜像与容器限制）；Adapter 只向私有 spool 目录写入作业请求并读取状态，不执行 Docker，也不新增第二个 Worker 生命周期所有者。差异登记为 [DEV-051](../deviations/DEV-2026-09-18-051-environment-job-runner.md)。
2. 作业目录状态：`queue/` → `running/` → `done/`；执行器持文件锁一次只处理一个作业，开始前检查主机可用内存（默认 2 GiB），不足时保持排队并写入 `HOST_MEMORY_LOW` 提示。
3. 生成→验收→发布：生成在只读根、无网络、1.5 CPU/1536 MiB 的固定镜像中执行，生成结果与规格不符（`ENVIRONMENT_SPEC_MISMATCH`）时最多重试 3 次；验收使用一次性内部网络 + QA 代理夹具，报告写入独立证据目录；通过后以模板应用定义派生新应用模板并原子追加目录条目（同 ID 拒绝覆盖）。
4. 目录条目 `source=custom` 与 `frozen` 在 Adapter 侧同等对待；产物 ID 为 `env-custom-<job>`，应用/浏览器仍绑定精确 SHA-256 与镜像摘要。

偏差文件链接：[DEV-051](../deviations/DEV-2026-09-18-051-environment-job-runner.md)，已解决为候选。实施中另确认：固定生成器 12 次抽样有 1 次不满足屏幕约束，执行器以有界重试处理；`prepare-sealskin.py` 抽出 `build_definition` 供目录模板复用，既有 3 项准备器测试保持。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 高层字段校验（46.2） | `profile/environment_jobs.go`、执行器 `read_request`/`validate_spec` | Go：14 类无效字段拒绝、派生规格固定字段；执行器：无效/超能力请求在生成前失败并写稳定码 | 候选隔离验证 |
| 一次一个作业、内存不足排队提示 | 执行器 spool 锁与 `available_memory_mib`、Adapter 排队上限 4 | 执行器测试：锁占用返回 locked、最早优先、`HOST_MEMORY_LOW` 保持排队后可继续；Go：第 5 个排队拒绝、完成后释放 | 候选隔离验证 |
| 隔离生成、完整验收、失败保留不发布 | 执行器 `generate`/`Fixture`/`run_acceptance`/`process` | 执行器测试：规格不符有界重试、其他失败立即失败、验收失败保留产物/报告/日志且无目录条目、夹具失败同样处理；真实作业：只读根/无网络生成 1 次、10 次重建验收通过、夹具与网络清理 | 候选隔离验证；执行器未装为服务 |
| 通过后进入目录、可绑定新浏览器 | 执行器 `append_catalog`/`catalog_entry`、`management.go` | 执行器测试：条目字段、挂载/环境/标签、同 ID 不覆盖、目录版本校验；Go：`custom` 条目可创建浏览器、未验证来源拒绝、文件目录读取执行器条目；真实作业目录条目 SHA 与文件一致 | 候选隔离验证；真实客户端使用自定义产物未测 |
| 面板提交/列表、管理员边界、脱敏 | `httpapi/manage.go` | Go：表单解析与通知、JSON 列表不含设备值、未登录 404、未启用 501/隐藏区块、目录下拉 | 候选隔离验证；真实网关 reauth 边界沿用 R6B 既有测试 |

证据：[R6E 验收](../../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md)；私有目录 `infra/sealskin/runtime/r6e-custom-fingerprint-2026-09-18/`（Go 测试/race 日志、主机 Python 日志、真实作业 spool/目录/执行器日志、result.json）。全模块 249 项 Go 测试、vet、gofmt、checks 镜像 race 与主机 21 项 Python 测试通过。

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确（[R6E 验收](../../infra/sealskin/custom-fingerprint-acceptance-2026-09-18.md)）。
- [x] 相关偏差已处理并复核（DEV-051 已解决为候选）；执行器安装与真实客户端明确归 R6F。
- [x] 更新设计/规格/组件/用户或运维说明：管理面规格、规格索引、Adapter README、Camoufox README、配置示例；运维说明不变（执行器未部署，用法在组件说明）。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理（夹具容器与两个网络已删除，spool/目录只在被忽略的运行目录）、回滚材料（无生产变更）、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：候选代码、执行器与隔离验收完成，未部署生产。下一步：按顺序选取 R6F；真实客户端、执行器安装、DIRECT 生产前置与部署仍归 R6F，不得据此部署。
