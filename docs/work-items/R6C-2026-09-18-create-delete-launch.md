# R6C · 新增删除浏览器、Home 归档与 launch plan

状态：已收尾（候选，未部署）。开始日期：2026-09-18。结束日期：2026-09-18。

## 目标与范围

- 用户要求 / 对应计划：[R6 远程浏览器管理面](R6-2026-09-16-environment-management.md)、[R6C 计划](../roadmap.md#r6)。
- 本项交付：管理员可通过 Adapter 创建和删除受管理浏览器；创建固定 Profile/Home/application 绑定，接受已登记的固化环境与 DIRECT/现有不可变网络策略引用；删除复用已验证 Stop，确认运行资源为空后归档 Home、删除 SealSkin 应用并保留审计记录；固定入口启动使用一次性、按账号和 Profile 修订绑定的 launch plan。
- 明确不在本项：Secret Store 代理草稿/探针（R6D）、自定义指纹生成作业（R6E）、生产 DIRECT 部署、真实 Home/Trilium 组合与生产候选（R6F）。
- 验证范围：Go 单元/HTTP 测试、静态检查和隔离的 fake SealSkin 管理 API；不操作生产二进制、真实 Home、Session 或 Docker。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [管理面规格](../specs/proxy-environment/management.md)、[工作流程](../workflow.md) | R6C 要求创建/删除、应用安装/删除、Home 归档和 launch plan；代理草稿与自定义指纹留给后续子项。 |
| `adapter/internal/profile/{directory,service}.go` | R6B 目录只支持已有记录的标签/起始页/停用更新；Profile 目录禁止变为空，尚无删除状态或归档记录。 |
| `adapter/internal/sealskin/{client,lifecycle}.go` | 已有 Home 创建、应用安装/列举和 verified Stop；尚无应用删除或 Home 归档管理调用。 |
| `adapter/internal/httpapi/manage.go`、`server.go` | 管理面只有 R6B 表单更新/启用/停用/关闭；无创建/删除/launch plan 路由。 |
| R6B 验收与当前 git | `8b6fc5f` 已收尾，工作区干净，生产仍是 candidate-4；本项从该候选代码开始。 |

## 实施与偏差

代码入口核对发现 SealSkin 上游归档接口未在当前客户端契约中声明，因此本项以控制器所有权的 `POST /api/homedirs/{home}/archive` 补丁建立归档能力；Adapter 不直接操作 Home。该差异登记为 [DEV-048](../deviations/DEV-2026-09-18-048-home-archive-controller-api.md)，生产控制器未替换，缺少补丁能力时删除请求必须拒绝。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 创建固定 Profile、Home、应用 | `profile.Directory`、管理 API、SealSkin admin client | fake 管理 API、目录原子写入和重复/失败回滚测试 | 候选隔离验证 |
| 删除前 Stop/资源为空，Home 归档、应用删除 | `profile.DeleteBrowser`、SealSkin client、`environment-management.patch` | busy/unknown 拒绝、归档与应用删除顺序测试；控制器端点归档/idempotent 重试测试 | 候选隔离验证 |
| 一次性 launch plan 绑定账号、修订和过期 | `profile/management.go`、入口 POST | 过期、重复、跨账号、修订漂移拒绝测试 | 候选隔离验证 |
| DIRECT/现有策略前置 | Profile 定义校验与创建请求 | 固定策略引用/缺少能力拒绝测试 | 候选隔离验证；生产前置未测 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确（[R6C 验收](../../infra/sealskin/environment-create-delete-acceptance-2026-09-18.md)）。
- [x] 相关偏差已处理并复核；未完成项有明确状态。
- [x] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认是否允许开始下一项。

收尾结论：候选代码与隔离验收完成，未部署生产。下一步：按顺序选取 R6D；R6C 的 DIRECT 生产前置与 R6F 组合 QA 仍未验证，不得据此部署。
