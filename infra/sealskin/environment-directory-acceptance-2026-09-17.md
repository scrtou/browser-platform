# R6B · Profile 目录、账号角色、管理员面板与关闭按钮验收 — 2026-09-17

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R6B 工作项](../../docs/work-items/R6B-2026-09-17-directory-roles-stop.md) · [管理面规格](../../docs/specs/proxy-environment/management.md) · [入口登录说明](entry-auth/README.md)

日期：2026-09-17（实施与测试）/ 2026-09-18（收尾），UTC。状态：**代码与 Go 隔离测试通过，未部署生产**。本项实现管理面实施顺序第 2 步并修复 [DEV-045](../../docs/deviations/DEV-2026-09-17-045-manage-list-role.md)：Profile 定义改为 Adapter 私有的可修订目录；账号表 version 2 增加 `admin`/`user` 角色；管理面板只对管理员开放并提供修改标签/起始页、停用/启用、安全关闭、账号创建/重置/禁用/分配；`/auth/reauth` 与 `/auth/password`；账号表变化改为按账号撤销。收尾复核另发现并修复 [DEV-046](../../docs/deviations/DEV-2026-09-18-046-profile-directory-cli-grants.md)：账号 CLI 在目录启用时只按权威目录校验授权，目录读取失败即拒绝；[DEV-047](../../docs/deviations/DEV-2026-09-18-047-profile-directory-lock-contract.md) 将规格中的目录独立 `flock` 修订为实际的 Adapter 服务锁单写者与进程内互斥契约。生产 Adapter、控制器、Caddy、账号表和 Home 均未改动。

## 版本与证据

本机私有根：`infra/sealskin/runtime/r6b-directory-roles-2026-09-17/`（被忽略）。

| 对象 | 版本 / 位置 |
| --- | --- |
| 源码基线 | 提交 `e4e0118` 之上的工作区改动：26 个 Go 文件（含 5 个新文件）；原逐文件 SHA-256 见 `candidate-1/adapter-build.json`，DEV-046 后的最终源码树摘要见 `candidate-2/closeout.json` |
| 工具链 | Go 1.27.1（同 R6A，`~/.local/toolchains/go1.27.1`） |
| 候选二进制 | 最终 `candidate-2/bin/profile-adapter` SHA-256 `2571d4b3…`、`profile-accounts` SHA-256 `26f7f2ab…`；`-buildvcs=false -trimpath`；candidate-1 保留为 DEV-046 前历史 |
| 生产二进制 | `~/.local/lib/browser-platform/profile-adapter` 保持 candidate-4 `7e7ab79e…`，未替换 |
| 测试日志 | 初轮 `go-tests-1/`、`go-race-1/`；DEV-046 后最终结果 `go-tests-2/result.txt`、`go-race-2/{race.log,attempts.txt}` |

## 实现边界

- **Profile 目录**：配置 `profile_directory` 指向私有 `profiles.json`（0600，fsync + 原子替换）。文件不存在时从配置 `profiles` 导入并写出；存在时以文件为准，配置 `profiles` 只作种子。每条记录带 `revision`/`updated_at`/`updated_by`，修改按修订号乐观锁；本项只允许修改 `label`、`start_url`、`disabled`，Home/应用/网络/能力字段不可经此路径改变。未配置目录的旧部署保持静态定义，管理页面的修改返回“操作暂时不可用”。
- **停用**：`disabled` 的浏览器在 `Ensure` 前拒绝（入口 503，不创建 Home、不启动、不复用）；已运行代次、显示授权、健康、停止与对账不受影响。
- **角色**：`Account.role` 为 `admin`/`user`；version 1 账号表与空角色一律视为 `user`；只要没有任何角色，写回仍为 version 1（旧二进制可读）。管理员可以没有 Profile 授权；入口账号至少一个授权。不能禁用或降级最后一个启用的管理员。CLI `profile-accounts put --role`、`enable` 与共享的账号存储。
- **管理面板**：网关只对 `admin` 放行 `/manage/*`（`user` 得到 403 页面且不含浏览器信息），GET/HEAD 直接放行，POST 先过精确 Origin + 表单 CSRF；管理员的授权覆盖全部 Profile（`view`/`manage`/`stop`，被分配的另有 `start`）。页面无脚本，CSP `default-src 'none'`，通知只从固定代码表渲染。
- **按账号撤销**：登录记录携带账号记录摘要；账号表变化只撤销记录变化或消失的账号的登录与显示（授权变化也算记录变化），其他账号不受影响；显示后台检查另撤销授权已撤回或 Profile 已不存在的显示连接。账号表缺失/无效仍撤销全部登录。
- **重新认证与改密**：`POST /auth/reauth` 校验密码后记录 5 分钟内的确认时间，不延长登录；创建管理员、禁用/启用账号、修改角色、重置他人密码要求近期确认。`POST /auth/password` 校验当前密码、新密码 12–256 字节且两次一致，写入后撤销该账号其他登录与显示，保留当前登录（当前登录已打开的画面需重新交接）。两者沿用登录的限速与并发派生上限，密码不进入日志。
- **关闭按钮**：`POST /manage/browsers/{id}`（`action=stop`）调用 `profile.Stop`；`stopped`/待确认/冲突分别以固定通知显示，不输出错误文本。

## 自动测试

| 检查 | 结果 |
| --- | --- |
| `gofmt -l` | 无输出 |
| `go vet ./...` | 通过 |
| `go test -count=1 ./...` | 9 个包全部 `ok`，模块共 147 个测试函数，其中本项新增 15 个、改写 4 个 |
| `go test -race -p 1 -count=1 ./...` | 9 个包全部 `ok`；在 checks 镜像 `ac6c880d627b`（含 gcc）内以只读源码、`--network none`、临时 tmpfs 串行运行；环境性重试保存在 `go-race-2/attempts.txt` |
| 生产配置与账号表 | 用新代码只读加载：2 个 Profile、`profile_directory` 未配置、账号表 version 1、1 个账号、0 个管理员；未修改 |

新增/改写测试覆盖：

| 场景 | 位置 | 结果 |
| --- | --- | --- |
| 目录导入为 0600 文件并可重新加载；更新递增修订、旧修订 409、无变化不递增、非法标签/URL 拒绝；运行中更新后 bootstrap 使用新起始页；不触发 launch/stop | `profile/directory_test.go` | 通过 |
| 停用：复用与新启动拒绝，显示授权、健康、停止仍可用；启用后可再次启动 | 同上 | 通过 |
| 目录文件：尾随数据、未知字段、重复 ID、空表、错误版本、非 0600 权限均拒绝；静态服务拒绝更新 | 同上 | 通过 |
| 账号存储：无角色保持 version 1，出现角色升为 version 2；管理员可无授权、入口账号需授权；未知 Profile/角色拒绝；最后管理员不能降级/禁用；替换保留角色；快照不含派生值；缺失注册表不自动创建 | `access/accounts_test.go` | 通过 |
| 面板仅管理员：`user` 对 `/manage/*` 403 且无浏览器信息、无管理链接；管理员 PUT 405、跨源/错误 CSRF POST 403、正确 POST 到达处理器；`/manage`、`/other` 404 | `access/manage_test.go` | 通过 |
| 管理员授权覆盖全部 Profile（`view,manage,stop[,start]`）；降级后本人登录撤销、他人登录保留；最后管理员保护；注册表缺失撤销全部 | 同上 | 通过 |
| 按账号撤销：改密只撤销该账号登录/显示；授权变化撤销该账号并在重新登录后生效；Profile 集合变化时显示检查撤销 | 同上 | 通过 |
| reauth：安全 `next` 校验、错误密码 401、成功记录、过期失效；改密：短密码 400、当前密码错误 401、成功保留当前登录并撤销其他、新密码生效、密码不进日志 | 同上 | 通过 |
| 处理器：更新/停用/启用按修订号、旧修订与未知通知不回显、`stop` 三种结果、能力与未授权 Profile 拒绝、无网关授权 404 | `httpapi/manage_test.go` | 通过 |
| 真实网关端到端：入口账号 403；管理员列表含账号分配；页面不含派生值；面板创建入口账号后管理员未被登出，新账号只能打开被分配的浏览器；创建管理员需 reauth；管理员可经网关停止，入口账号不能 | `httpapi/manage_gateway_test.go` | 通过 |
| CLI：`--role admin`、拒绝禁用最后管理员、未知角色拒绝、`enable`、version 2 持久化；持久化目录完全取代静态种子，目录不可读时拒绝且账号表不变（DEV-046） | `cmd/profile-accounts/main_test.go` | 通过 |

## 未测与保留范围

- 没有在真实浏览器、Trilium WebView 或目标 Mac 上操作面板；没有用真实控制器运行候选二进制；生产未部署。真实客户端与组合验收归管理面第 6 步。
- 回退注意：一旦账号表写入 version 2（存在角色），candidate-4 等旧 Adapter 会拒绝该表并撤销全部登录；回退前须用新 CLI 把所有角色降级到 version 1 或恢复旧表。
- 新增/删除浏览器、代理配置、指纹目录与作业未实现（R6C–R6E）。
