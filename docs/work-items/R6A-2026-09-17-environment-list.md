# R6A · 授权环境列表与只读环境摘要

状态：已收尾（候选代码与 Go 隔离测试完成；未部署生产）。登记日期：2026-09-17。开始日期：2026-09-17。结束日期：2026-09-17。

> 2026-09-17 收尾后用户补充：管理面板需要管理员账号密码，浏览器入口用各自账号密码。本项按第 1 版设计对任意登录账号放行 `/manage/`，与此不符，已登记 [DEV-045](../deviations/DEV-2026-09-17-045-manage-list-role.md)，由 R6B 修复；本候选在修复前不进入发布包。

## 目标与范围

- 用户要求 / 对应计划：用户于 2026-09-17 在 R4B 收尾后要求“继续下一项计划”。对应 [R6 计划](../roadmap.md#r6) 与 [环境管理面规格](../specs/proxy-environment/management.md#实施顺序) 的第 1 个子项：“先做授权 Profile 列表和只读环境摘要，验证权限边界”。父项 [R6 设计工作项](R6-2026-09-16-environment-management.md) 保持其余三项（关闭入口、指纹选择、代理草稿）未完成。
- 本项交付与完成条件（保留父计划要求）：
  1. 登录后的账号只能列出自己获授权的 Profile；未登录、跨账号、禁用账号和注销后不能读取列表，错误响应不泄漏未授权 Profile 是否存在。
  2. 每个条目只包含有限摘要：Profile 标识/标签、固定入口路径、当前账号对该 Profile 的能力、应用与 Home 名、语言/时区/显示模式、网络模式与策略标识、journal 状态，以及带采样时间和有效期的健康结果和环境产物身份。不返回 operation、Session、bootstrap、幂等键、策略摘要或错误文本，不返回 resolved config。
  3. 列表只读：不触发健康采集、启动、恢复或停止；无缓存报告时明确标为未观测，过期报告标为 stale 且整体为 unknown。
  4. 旧配置和固定 Profile 入口保持兼容；未启用 `access` 的旧本机配置不暴露列表。
  5. Go 单元/HTTP 测试覆盖上述权限、脱敏、只读与错误路径；`go vet` 与涉及包 race 通过；组件说明、规格、设计、进度、计划和索引更新后收尾。
- 本次验证、部署与客户端范围：Adapter 代码与 Go 测试（真实网关 + HTTP 处理链 + 假生命周期）；不改动 SealSkin、Caddy、账号表格式、生产配置或生产二进制，不部署生产。真实浏览器/Trilium 客户端和生产候选归 R6 第 5 步的组合 QA。
- 前置项及其收尾记录：[R4B](R4B-2026-09-14-target-client-migration.md) 已于 2026-09-17 收尾；[R2](R2-2026-09-13-boot-recovery.md) 保留退出登录与 Debian 13 待外部条件，用户已决定继续。运行基线：生产 Adapter candidate-4（SHA-256 `7e7ab79e…`）、控制器 `0.3.2-entry-auth-v1-2ba57382ce75c8f9`。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [进度](../progress.md)、[计划 R6](../roadmap.md#r6)、[设计 R6 管理面](../design.md#r6-远程浏览器管理面)、[管理面规格](../specs/proxy-environment/management.md) | 规格要求 `GET /manage/environments` 只返回授权 Profile 的标签、状态和有限环境摘要；实施顺序第 1 步只做列表与权限边界 |
| [入口登录说明](../../infra/sealskin/entry-auth/README.md)、[R5D 验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)、[R4B 验收](../../infra/sealskin/target-client-migration-acceptance-2026-09-15.md) | 生产已启用登录、Profile 授权、CSRF/Origin、显示交接；前置 Caddy 把两个域名的全部路径转发 Adapter，新路径不需要改 Caddy |
| [`access/gateway.go`](../../adapter/internal/access/gateway.go) `serveEntry` / `allowed` / `indexTemplate` | 网关只对 `/auth/*`、`/healthz`、`/readyz`、`GET /bootstrap/*` 和 `/browser/{id}/…` 放行；其他路径对已登录用户也返回 404。根页只列出授权 Profile 链接。账号表 `Account{ID, PasswordHash, Profiles, Disabled}` 没有能力字段 |
| [`httpapi/server.go`](../../adapter/internal/httpapi/server.go) | 路由 `entry / health / start / bootstrap`；`profileService` 接口只有 Ensure/BootstrapTarget/Health；公开健康用 `CachedOnly` 且经 `Public()` 去掉 operation/Session |
| [`profile/health.go`](../../adapter/internal/profile/health.go)、[`profile/display_access.go`](../../adapter/internal/profile/display_access.go) | 健康缓存 60 秒有效，`AsOf` 把过期报告标为 stale/unknown；报告含 `Environment{ID, ArtifactSHA256}`、`NetworkMode`、绑定摘要与恢复提示。只读检查可直接读 journal（store 自带 flock），不取 Profile 锁 |
| [`profile/service.go`](../../adapter/internal/profile/service.go) `Definition` | 有 `language/timezone/wayland_mode/network_policy_id/application_id/home_name`，没有标签字段；配置加载 `DisallowUnknownFields`，新增可选字段向后兼容 |
| [`safelog`](../../adapter/internal/safelog/safelog.go) | 新日志消息必须登记在允许列表，否则被抑制 |
| 已有工作区改动、运行版本与生效范围 | 开始时 `git status --short` 为空（`61ba102`）。生产 Adapter 二进制 `~/.local/lib/browser-platform/profile-adapter` SHA-256 `7e7ab79e…` 与 candidate-4 一致；本项不替换它。主机与 checks 镜像均无 Go，按官方 SHA-256 校验安装 Go 1.27.1 到 `~/.local/toolchains/`（与 candidate-4 相同版本） |

## 设计决定

- **授权来源不变**：继续使用 R5D 账号表的 Profile 授权；本项把“已授权”解释为 `view` 与 `start` 两项能力并在响应中显式给出 `capabilities`，账号表格式保持 version 1。更细的 `stop`/`configure_proxy`/`select_environment` 授权字段在首次需要它们的 R6B（关闭入口）实现，不在本项修改生产账号表格式。
- **路径与职责**：网关负责认证与授权，新增对 `GET /manage/` 与 `GET /manage/environments` 的登录检查并把主体与授权 Profile 列表放入请求上下文；`httpapi` 只按该列表逐个读取摘要并渲染。没有 `access` 时两个路径返回 404，不把全部 Profile 暴露给无登录部署。
- **摘要来源**：`profile.Service.Environment` 读取定义、journal 绑定和 `CachedOnly` 健康缓存；从不调用观测、启动、恢复或停止。健康缺失 → `observed=false`；lifecycle 未启用 → 同样未观测但列表仍可用。
- **可选标签**：Profile 定义增加可选 `label`（≤ 64 个可打印字符）；生产配置未设置时页面显示 Profile ID，不改生产配置。
- **页面**：`/manage/` 为无脚本 HTML，CSP `default-src 'none'`，含各条目固定入口链接、JSON 链接和退出登录表单；`/` 根页增加到 `/manage/` 的链接，其他行为不变。

## 实施与偏差

- `profile/environment.go`：`EnvironmentSummary`/`EnvironmentHealth` 与 `Service.Environment`；读定义、原子 journal（不取 Profile 锁）和 `CachedOnly` 健康缓存，`ErrHealthUnavailable`/`ErrLifecycleDisabled` 视为未观测，其他错误上抛；受管理代次的缓存报告为 DIRECT 时网络模式显示 `direct`。
- `profile/service.go`：`Definition.Label`（可选，≤ 64 个可打印字符、无首尾空白）、`DisplayLabel()`；配置层沿用 `DisallowUnknownFields`，旧配置不受影响。
- `access/gateway.go`：`Grant{profile_id, capabilities}`、`ManagePath`、`grants()`（按账号表 + 已配置 Profile，稳定排序）、`Grants()/Subject()/ContextWithGrants()`；`serveEntry` 对 `/manage/` 与 `/manage/environments` 在登录后只放行 GET/HEAD 并附加授权；首页增加管理链接。固定入口的 `allowed` 检查与交接逻辑未改。
- `httpapi/manage.go` + `server.go`：`GET /manage/{$}`、`GET /manage/environments`；无授权上下文即 404；摘要失败时保留行、不输出错误文本；页面无脚本，CSP `default-src 'none'; form-action 'self'`，`no-store`。`profileService` 接口新增 `Environment`。
- `safelog`：登记 `environment summary unavailable`、`render environment list` 两个固定日志事件。
- 工具链：主机与 checks 镜像均无 Go；下载官方 go1.27.1 归档并核对 SHA-256 后安装到 `~/.local/toolchains/`，race 在 checks 镜像内（有 gcc）以只读源码、无网络运行。
- 偏差记录：经核对未发现设计与代码冲突，未建立 DEV 记录。规格中的 `profile_access` 修订/能力字段本项没有落到账号表；这是设计的第 1 步范围，不是偏差，在 R6B 需要 `stop` 能力时再扩展。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 只列出授权 Profile，不泄漏存在性（第 1 版；第 2 版要求仅管理员，见 DEV-045） | `access.serveEntry`、`grants()` | `access/manage_test.go`：未登录 303（页面）/401（JSON）、POST 405、其他路径 404、跨账号不出现、禁用/账号表缺失/注销后 401；`httpapi/manage_gateway_test.go` 真实网关端到端 alice/bob 分别只见自己的授权 | 通过（Go 测试）；真实浏览器/Trilium 未测 |
| 有限摘要与脱敏 | `profile.Environment`、`httpapi/manage.go` | `environment_test.go` JSON 键/值扫描无 operation/session_id/bootstrap/idempotency/sha256/last_error；`manage_test.go` 摘要失败不输出错误文本、页面不显示完整产物摘要 | 通过 |
| 只读、不触发采集 | `HealthOptions{CachedOnly: true}` | 假生命周期 observe/launch/stop/resume 计数不变；过期缓存不触发采集；端到端 Ensure/Health 调用为 0 | 通过 |
| 无 access 不暴露 | `httpapi/manage.go` | 无网关时 `/manage/`、`/manage/environments`、`/manage/other` 404，`/manage` 仅 307 到 `/manage/` | 通过 |
| 兼容 | 配置加载、旧固定入口测试 | 全模块 138 项测试、vet、race 通过；生产配置在新代码下只读加载成功（两 Profile 均无 label，显示 ID） | 通过；生产未替换二进制 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为（上表；规格第 1 步范围内没有遗漏项，能力字段留给后续子项）。
- [x] 完成本项必要验证：[R6A 验收](../../infra/sealskin/environment-list-acceptance-2026-09-17.md)；私有证据 `infra/sealskin/runtime/r6a-environment-list-2026-09-17/`（候选二进制、构建清单、测试/race 日志）。
- [x] 相关偏差：经核对未发现；未完成项（真实客户端、组合 QA、部署）明确归管理面第 5 步。
- [x] 更新 Adapter 说明、入口登录说明、管理面规格、设计、Trilium 客户端说明。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围（未部署）。
- [x] 更新开发计划：R6A 收尾，下一子项关闭入口未开始。
- [x] 核对：无 QA 容器/网络/Home 创建（只有 Go 测试与一次性 race 容器 `--rm`），生产二进制/配置/账号表/Home 未变；回滚不适用；链接与 whitespace 静态检查通过。
- [x] 更新本记录与工作项索引。

收尾结论：已收尾。候选代码与隔离测试完成，未部署生产。2026-09-17 设计修订为第 2 版后本项仍是第 1 步，列表将在后续子项增加 `enabled`/修订/代理摘要/入口 URL 列。下一步：R6B（Profile 目录、账号角色与关闭按钮），按流程重新选取后才开始。
