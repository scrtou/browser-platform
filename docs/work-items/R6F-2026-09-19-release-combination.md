# R6F · 组合 QA、真实客户端、生产候选与回退

状态：进行中。开始日期：2026-09-19。结束日期：未结束。

## 目标与范围

- 用户要求 / 对应计划：[R6 远程浏览器管理面](R6-2026-09-16-environment-management.md)、[R6 计划](../roadmap.md#r6)、[管理面规格第 2 版](../specs/proxy-environment/management.md#实施顺序)。
- 本项交付：以 R6A–R6E 候选源码为同一版本，在独立 QA 根完成组合控制器/Adapter/Worker 验证；覆盖管理员与浏览器账号边界、固化和自定义指纹、DIRECT 与真实上游代理、创建/停止/删除/归档、恢复和日志脱敏；准备真实客户端（Trilium/macOS）复测清单；核对加密备份/离线恢复；演练可逆回退并形成生产候选包、清单和部署前置。
- 明确不在本项自动执行：未经用户明确维护窗口授权的生产部署、真实 Mac 上的操作、生产 Home/Session 的破坏性回退、删除真实数据，以及把隔离回归结果扩大为生产通过。按用户决定不建立专用 QA 根，直接复用现有环境；控制器 overlay 的安装仍须通过现有管理员身份核验。
- 完成条件：组合 QA 与失败保留/清理证据完整；真实客户端分项由用户在 Mac/Trilium 实测或明确保持待验证；备份恢复和回退材料可复现且不泄露敏感数据；候选源码、二进制、镜像、控制器补丁和配置摘要一致；未通过或外部条件明确列为未完成。
- 验证环境：本机 Debian 12、独立 Docker 网络/卷/tmpfs、固定 Camoufox r9 与现有 checks 镜像；真实客户端为 macOS 15.1 / Trilium 0.105.0（需用户操作）。本项开始时生产为 R4B `release-ready-2` 运行态；用户随后授权部署管理面进行实测。
- 前置项及其收尾记录：[R6E](R6E-2026-09-18-custom-fingerprint-jobs.md) 已收尾（`c7e946f`）；R6A–R6D 均已收尾，候选均未部署。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| 进度、计划、设计、规格与验收索引 | R6F 是 R6A–R6E 后的最后组合项；父项仍进行中，生产为 R4B `release-ready-2`。 |
| Adapter 启动/配置、HTTP 管理入口、Profile 状态与 SealSkin 客户端 | `adapter/cmd/profile-adapter/main.go` → `internal/config`/`profile`/`httpapi`/`sealskin`；Adapter 只拥有授权、目录和状态，SealSkin 仍拥有 Worker/Home 生命周期。 |
| R6D 控制器补丁、R6E 执行器、R5E 组合工具、备份工具 | R5E 的组合协调器可复用其网络/入口/恢复检查，但固定 R5E 路径、版本和资源注册表不能直接冒充 R6F；R6E 主机执行器尚未安装为服务。 |
| 已有工作区改动、运行版本与生效范围 | 本项开始时源码工作区干净（`c7e946f`）、生产 Adapter 为 candidate-4；2026-09-19 用户授权后仅切换 Adapter/配置并升级账号角色，控制器、Caddy、Home、Session 和浏览器容器保持。 |

## 实施与偏差

实施前先登记本工作项并锁定 `infra/sealskin/runtime/r6f-release-combination-2026-09-19/` 为私有证据根。按用户决定本轮不创建专用资源，现有 Personal/Work、Home、Session 和容器保持；发现实现与设计或环境前置不符时，先在 `docs/deviations/` 登记并链接本项，再决定修复、修订设计或保留待处理。

已登记 [DEV-052](../deviations/DEV-2026-09-19-052-stale-release-package.md)：R4B 历史 `release-ready-2` 的准备摘要早于当前 r9 生产状态写入，复核按预期拒绝 `live input drift`；旧包只保留为回退材料，R6F 已重新绑定当前输入。新增 [DEV-053](../deviations/DEV-2026-09-19-053-management-production-gating.md)：补齐无损首管理员升级和可选管理后端的页面/接口能力门控，允许生产只启用已具备前置的安全子集。新增 [DEV-054](../deviations/DEV-2026-09-19-054-r6f-combination-runner-scope.md)：按用户决定改为复用现有环境；overlay 已通过 11 项隔离管理/Home 归档测试并安装，固化/自定义指纹浏览器和真实代理探测已完成受控组合验证与清理；原运行器仍绑定旧 R5E 资源，自动化适配另列后续。新增 [DEV-055](../deviations/DEV-2026-09-19-055-encrypted-backup-account-version.md)：当前账号表已升级为 version 2，旧加密备份校验器拒绝带角色的账号表；校验器已与现行 admin/user 契约对齐，固定回归和组合根离线恢复通过。R6E 的执行器安装位置差异沿用 [DEV-051](../deviations/DEV-2026-09-18-051-environment-job-runner.md)。临时 Profile 已完成创建、停用拒绝启动、启用、启动、健康、安全关闭和归档删除；真实 Mac 自定义 artifact、真实 Personal/Work Home 备份、现有 Personal/Work 的生命周期写操作和实际回退仍保持未决，不以临时 Profile 或旧版本 QA 代替。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| R6 管理面组合：账号、目录、创建/删除、代理/DIRECT、指纹、停止 | Adapter `internal/{access,httpapi,profile}`、控制器第二层补丁 | 当前源码 test/vet/gofmt 和固定 checks 镜像全模块 race 通过；控制器 checks 镜像全量 545 项通过；固定 r9 artifact unit 17 项、R6E 主机回归 21 项通过；overlay 安装后，固化/自定义指纹浏览器均完成创建、启动、health/ready、代理探测和删除清理；另一个临时固化 Profile 完成停用、启动拒绝、启用、健康启动、安全关闭、Home 归档和删除清理 | 安全子集、现有环境组合、临时 Profile 完整生命周期及组合控制根恢复已验证；现有 Personal/Work 写操作、真实 Mac 自定义产物和实际回退仍未完成 |
| P/N/C/S/E/H 适用矩阵 | R5A–R5E 工具与 R6D/R6E 入口 | 复用工具但重建 R6F 版本/资源绑定；不得扩大旧报告范围 | 未验证 |
| 真实客户端与账号操作 | Trilium WebView / macOS 15.1、生产 Adapter HTTPS | 用户截图确认原 `owner` 登录、Personal/Work 列表、账号区、安全子集表单和未启用提示正常；随后提交 Personal 名称修改，服务器确认 `revision=2`，再临时修改并恢复起始页，最终 `revision=4`、起始页原值和运行绑定保持；创建 `test` 普通账号，仅分配 Personal；`test` 可进入 Personal、访问 `/manage/` 被拒绝且看不到 Work；复用 QA 管理员完成 reauth、自助改密、其他登录撤销、旧/新密码切换和管理面重置，最终禁用 QA 账号 | 页面、能力门控、名称/起始页、创建账号、普通账号边界及账号密码操作通过；临时 Profile 生命周期由服务器端 HTTPS 验证，真实 Mac 自定义产物及现有 Personal/Work 停启/关闭未测 |
| 备份/恢复与日志脱敏 | `secure-backup.py`、R5E 恢复工具、候选日志 | 固定 age v1.2.1 的 checks 镜像备份回归通过；修复 version 2 账号表校验后，使用当前控制根、Session/Secret Store、账号表和 r9 环境资产，对已停止且不再绑定生产的旧 QA Home 完成 4543 成员加密归档、verify 和离线 restore，scratch 为空，未触及生产运行态 | 组合控制根恢复通过；真实 Personal/Work Home 停机备份仍待用户选择 Profile/维护窗口 |
| 回退演练与生产候选 | R4B release tooling、候选 manifest、回退配置 | 首轮 `candidate-10` 后当前运行 Adapter 摘要为 `7f699ce3…`，与 `candidate-14` 复核候选一致；控制器 overlay `r6f-existing-overlay-recheck` 已安装并重启 `sealskin`，生产服务 active/enabled，正确 Host 路由的 health/ready 均为 200；候选/旧 Adapter/配置/状态/账号表回退材料仍保留 | overlay 安装和当前运行态复核通过；组合控制根恢复另有隔离证据，但未执行破坏性实际回退 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为。
- [x] 完成本项必要验证，公开报告与私有证据范围明确。（安全子集部署、Mac/Trilium 普通账号边界及组合控制根离线恢复证据已完成；真实生产 Home/客户端自定义 artifact 仍待外部条件。）
- [x] 相关偏差已处理并复核；未完成项有明确状态。（DEV-052–055 已链接；剩余缺口未改写为通过。）
- [x] 更新设计/规格/组件/用户或运维说明，或记录不适用原因。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围。
- [x] 更新开发计划的完成条件、剩余工作和下一项。
- [x] 核对 QA 清理、回滚材料、链接及工作区变更。
- [x] 更新本记录与工作项索引，确认当前不允许结束 R6 父项。

收尾结论：未收尾。当前生产已启用列表、账号、名称/起始页修改、停用/启用和安全关闭；控制器 overlay 已安装。现有环境中固化指纹浏览器和自定义指纹浏览器均完成创建、启动、健康/代理探测、删除和审计清理；另一个临时固化 Profile 已完成停用拒绝启动、启用、健康启动、安全关闭、资源归零、Home 归档与删除，目录保留 `deleted` 审计记录。临时 QA 管理员最终已再次禁用，旧会话和新登录均被拒绝，owner/test 完整账号记录和 Personal/Work 绑定保持。Mac/Trilium 页面、能力门控、名称修改、起始页修改/恢复、创建普通账号及普通账号三项边界已实测通过；生产 HTTPS 上的 reauth、自助改密、其他登录撤销、旧/新密码切换及管理面重置也已通过。组合控制根已在隔离旧 QA Home 上完成加密归档、verify 和离线 restore；真实 Personal/Work Home 停机备份、真实 Mac 自定义产物、现有 Personal/Work 停用/启用/安全关闭和实际回退仍待完成。本项未收尾前不开始新的计划工作项。
