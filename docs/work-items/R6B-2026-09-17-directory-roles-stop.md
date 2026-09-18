# R6B · Profile 目录、账号角色、管理员面板与关闭按钮

状态：已收尾（候选代码与 Go 隔离测试完成；未部署生产）。登记日期：2026-09-17。开始日期：2026-09-17。结束日期：2026-09-18。

## 目标与范围

- 用户要求 / 对应计划：用户 2026-09-17 设定目标“继续按计划推进，直到完成所有的任务，项目可发布，记得做好文档更新和提交”。对应 [R6 计划](../roadmap.md#r6) 与 [管理面规格第 2 版](../specs/proxy-environment/management.md#实施顺序) 第 2 步。前置 [R6A](R6A-2026-09-17-environment-list.md) 已收尾；本项同时修复 [DEV-045](../deviations/DEV-2026-09-17-045-manage-list-role.md)。
- 本项交付与完成条件（保留父计划要求）：
  1. **Profile 目录**：Adapter 私有的 `profiles.json`（version、全局修订、逐条修订、更新时间/操作者），首次启用时从配置 `profiles` 导入，此后为事实来源；写入沿用 0600、fsync、原子替换；按修订号乐观锁；运行中可修改 `label`、`start_url`、`disabled`，服务热更新，不重启。停用的浏览器拒绝新的启动/复用（503），已运行代次不受影响。
  2. **账号角色**：账号表 version 2 增加 `role`（`admin`/`user`）；version 1 及空角色一律视为 `user`；只有存在非空角色时才写 version 2（保持对旧二进制的回退兼容）。CLI `profile-accounts put --role`；禁止禁用最后一个启用的管理员。
  3. **管理员面板**：`/manage/*` 只对 `admin` 放行，`user` 得到 403 且不泄漏任何浏览器；管理员列表覆盖全部浏览器（含未分配），并显示分配账号、启用状态、修订；页面内表单可修改标签/起始页、停用/启用、安全关闭；账号区可创建账号、重置密码、禁用/启用、分配浏览器。
  4. **重新认证与改密**：`/auth/reauth`（5 分钟内有效，不延长登录）用于重置他人密码、禁用账号、创建管理员；`/auth/password` 任意账号修改自己的密码，成功后撤销该账号其他登录、保留当前登录。
  5. **账号表变化的撤销改为按账号**：只撤销记录发生变化或消失的账号的登录/显示，其他账号不受影响；被取消分配的浏览器显示连接在后台检查中撤销。
  6. **关闭按钮**复用 `profile.Stop`：持久化停止意图、显示撤销、确认清理、失败保留；页面显示结果。
  7. Go 单元/HTTP 测试覆盖上述路径，`go vet`、race 通过；组件说明、规格、进度、计划、索引更新并提交。
- 本次验证、部署与客户端范围：Adapter 代码与 Go 测试；不改 SealSkin、Caddy、生产配置或生产二进制，不部署；真实客户端/组合 QA 归 R6F。
- 前置项及其收尾记录：R6A（`90e1019`）、设计第 2 版与两级访问（`e4e0118`）。运行基线：生产 Adapter candidate-4 `7e7ab79e…`。

## 阅读与代码核对

| 材料 / 代码入口 | 核对结论 |
| --- | --- |
| [管理面规格](../specs/proxy-environment/management.md)“核心对象”“访问账号与登录 URL（两级访问）”“实施顺序” | 目录字段、角色规则、重新认证、改密、最后管理员保护、按账号撤销均已在规格中写明；接口表以 PATCH/DELETE 表述，页面无脚本，本项以表单 POST 实现并在规格中注明 |
| [`profile/service.go`](../../adapter/internal/profile/service.go) `profiles map[string]Definition` | 19 处读取，全部为按 ID 取定义或遍历；改为目录快照读取即可，不需要改锁模型（Profile 锁仍按 ID） |
| [`state/store.go`](../../adapter/internal/state/store.go) | 提供 temp+fsync+rename 写法；目录文件只由运行中的 Adapter 写入（持有服务锁），用进程内互斥即可 |
| [`access/gateway.go`](../../adapter/internal/access/gateway.go) `reload`/`validLocked`/`checkDisplays`/`serveEntry` | 当前账号表任何变化 `clearLocked()` 撤销全部登录；`checkDisplays` 只核对绑定，不核对授权变化；`/manage/` 分支对任意登录放行（DEV-045）|
| [`cmd/profile-accounts`](../../adapter/cmd/profile-accounts/main.go) | 锁文件 + `ReadRegistry`/`WriteRegistry`；本项抽成共享的账号存储供 CLI 与面板复用 |
| 生产运行版本 | candidate-4 只接受账号表 version 1；本项写入规则保证未使用角色时仍为 version 1 |
| 已有工作区改动 | 开始时 `git status --short` 为空（`e4e0118`） |

## 实施与偏差

- `profile/directory.go`：`directory`（RWMutex、`Record{Definition, Revision, UpdatedAt, UpdatedBy}`、`open` 导入/加载/校验、`update` 乐观锁、0600/fsync/原子写）、`DirectoryProfileIDs`；`Definition.Disabled`；`Service` 的 19 处静态 map 读取改为目录快照；`WithDirectory`、`Records`、`ProfileIDs`、`KnownProfile`、`UpdateBrowser`；`Ensure` 对停用返回 `ErrProfileDisabled`。
- `access/accounts.go`：`AccountStore`（锁文件、`Put/SetPassword/SetDisabled/SetGrants/SetRole/Snapshot`、最后管理员保护、授权归一化）；`users.go`：`Role`、version 1/2 校验、无角色写回 version 1；CLI 改用该存储并增加 `--role`、`enable`，`profile_directory` 存在时按目录校验授权。
- `access/gateway.go`：`ProfileSet` 接口（生产传 `profile.Service`）、`ManagePath` 前缀、`role()`、管理员授权覆盖全部 Profile、`login.AccountHash/ReauthAt`、`reloadKeeping` 按账号撤销、`checkDisplays` 核对授权、`serveCredential`（reauth/改密）、`Reauthenticated`、`Reload`、`Accounts`；首页只对管理员显示面板链接并增加改密链接。
- `httpapi/manage.go`：管理员页面（浏览器表单：update/enable/disable/stop；账号表单：创建/重置/禁用启用/分配/角色）、固定通知表、`manageService` 接口；`server.go` 新路由与 `ErrProfileDisabled` 映射；`safelog` 登记 `management action`。
- `config`：`profile_directory`（需 lifecycle，允许 `profiles` 为空）；`main.go` 传目录与 `ProfileSet`。
- 设计细化：规格接口表的 PATCH/DELETE 在无脚本页面上以表单 POST 实现，已在规格中注明；授权变化按“账号记录变化”处理（撤销该账号登录，重新登录后生效），比规格“取消分配撤销显示”更严格且更简单。
- 偏差：DEV-045 已修复并标已解决；收尾复核发现 [DEV-046](../deviations/DEV-2026-09-18-046-profile-directory-cli-grants.md)，账号 CLI 曾把权威目录与静态种子合并并在目录读取失败时回退，现已改为目录完全取代种子且失败即拒绝；[DEV-047](../deviations/DEV-2026-09-18-047-profile-directory-lock-contract.md) 把规格中误写的目录独立 `flock` 修订为实际的 Adapter 服务锁单写者与进程内互斥契约。

## 验收复核

| 原要求 / 验收编号 | 实现位置 | 检查与证据 | 结果 / 未测范围 |
| --- | --- | --- | --- |
| 目录导入/持久化/乐观锁/热更新/停用拒绝 | `profile/directory.go`、`service.go` | `directory_test.go` 3 项：0600 导入与重载、修订/无变化/非法值、运行中 bootstrap 用新起始页、停用拒绝复用与新启动但显示/健康/停止可用、不安全文件拒绝、静态服务只读 | 通过（Go 测试） |
| 角色、version 1/2 兼容、最后管理员 | `access/users.go`、`accounts.go`、CLI | `accounts_test.go`、`main_test.go`：无角色写 version 1、有角色写 version 2、管理员可无授权、最后管理员不能禁用/降级、替换保留角色、快照无派生值；目录启用后只按权威目录校验且读取失败拒绝；生产 version 1 表只读加载通过 | 通过 |
| 面板仅管理员、user 403、全量列表与操作 | `access/gateway.go`、`httpapi/manage.go` | `manage_test.go`（两包）、`manage_gateway_test.go`：user 403 无信息、admin 全量授权、Origin/CSRF、表单更新/停用/停止、通知不回显、真实网关创建账号后管理员不掉线 | 通过 |
| 重新认证、改密、按账号撤销 | `access/gateway.go` | `manage_test.go`：reauth 安全 next/错误/过期、改密保留当前撤销其他、改密与授权变化只影响本账号、Profile 集合变化撤销显示 | 通过 |
| 关闭按钮 | `httpapi/manage.go` → `profile.Stop` | stopped/待确认/冲突三种通知；入口账号经真实网关不能停止 | 通过；真实控制器停止未测（R6F） |
| race / vet / gofmt | 全模块 | DEV-046 后 `go-race-2/race.log` 9 包 ok；147 项普通测试、vet 通过；gofmt 无输出 | 通过 |

## 文档与收尾

- [x] 逐项回看原始任务、计划、设计和实际行为（上表；7 项完成条件均有测试）。
- [x] 完成本项必要验证：[R6B 验收](../../infra/sealskin/environment-directory-acceptance-2026-09-17.md)；私有证据 `infra/sealskin/runtime/r6b-directory-roles-2026-09-17/`。
- [x] DEV-045、DEV-046、DEV-047 已处理并标已解决。
- [x] 更新 Adapter 说明、入口登录说明、管理面规格、示例配置；设计文档的 R6 段落无需再改（第 2 版已描述本步）。
- [x] 更新验收索引。
- [x] 更新开发进度与生效范围（未部署）。
- [x] 更新开发计划：R6B 收尾，下一子项 R6C。
- [x] 核对：无 QA 容器/网络/Home 创建，生产二进制/配置/账号表未变；回退注意（version 2 账号表对旧二进制不兼容）已写入验收与入口说明；链接与 whitespace 检查通过。
- [x] 更新本记录与工作项索引，并提交。

收尾结论：已收尾。候选代码与隔离测试完成，未部署生产。下一步：R6C（新增/删除浏览器：管理员 SealSkin 客户端、应用安装/删除、Home 创建与归档、launch plan、DIRECT/现有代理修订），按流程重新选取后开始。
