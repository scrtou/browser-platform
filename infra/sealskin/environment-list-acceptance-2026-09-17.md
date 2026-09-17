# R6A · 授权环境列表与只读环境摘要验收 — 2026-09-17

[验收索引](../../docs/acceptance/README.md) · [当前进度](../../docs/progress.md) · [R6A 工作项](../../docs/work-items/R6A-2026-09-17-environment-list.md) · [管理面规格](../../docs/specs/proxy-environment/management.md) · [入口登录说明](entry-auth/README.md)

日期：2026-09-17，UTC。状态：**代码与 Go 隔离测试通过，未部署生产**。本项实现管理面实施顺序第 1 步：登录账号只能列出自己获授权的 Profile，并读取只读的环境摘要（记录状态、缓存健康结果及其采样时间/有效期、环境产物身份、网络模式、显示/语言/时区、应用/Home）。列表不触发观测、启动、恢复或停止；生产 Adapter、控制器、Caddy、账号表和 Home 均未改动。

## 版本与证据

本机私有根：`infra/sealskin/runtime/r6a-environment-list-2026-09-17/`（被忽略）。

| 对象 | 版本 / 位置 |
| --- | --- |
| 源码基线 | 提交 `61ba102` 之上的工作区改动：6 个修改文件、6 个新文件（4 个测试文件）；逐文件 SHA-256 见 `candidate-1/adapter-build.json` |
| 工具链 | Go 1.27.1 官方 linux-amd64 归档，SHA-256 `63d339f0…` 校验后安装到 `~/.local/toolchains/go1.27.1`（与 R4B candidate-4 相同版本；主机与 checks 镜像原本均无 Go） |
| 候选二进制 | `candidate-1/bin/profile-adapter` SHA-256 `971012db…`、`profile-accounts` SHA-256 `15300b71…`；`-buildvcs=false -trimpath` |
| 生产二进制 | `~/.local/lib/browser-platform/profile-adapter` 保持 candidate-4 `7e7ab79e…`，未替换 |
| 测试日志 | `go-tests-1/{gofmt,vet,test}.log`（gofmt 输出为空）；`go-race-1/race.log` |

## 实现边界

- **授权来源**：沿用 R5D 账号表的 Profile 授权，账号表格式仍为 version 1。网关把授权解释为 `view` 与 `start` 两项能力并随请求上下文传给处理器；`stop`/`configure_proxy`/`select_environment` 在需要它们的后续子项再引入。
- **路径**：`GET /manage/`（无脚本 HTML）与 `GET /manage/environments`（JSON）只在登录网关之后可达；未登录分别 303 到登录页（不带 `next` 提示）和 401，POST 等方法 405，其他 `/manage/*` 路径 404。没有配置 `access` 的旧部署两个路径直接 404。前置 Caddy 已把全部路径转发 Adapter，不需要改路由。
- **摘要来源**：`profile.Service.Environment` 读取 Profile 定义、原子 journal（不取 Profile 锁）和 `CachedOnly` 健康缓存；无缓存时 `observed=false`，报告过期时 `stale=true` 且整体 `unknown`。摘要不含 operation、Session、bootstrap、幂等键、策略摘要、错误文本或 resolved config；未知 Profile 从列表中跳过，摘要失败时该行只保留 Profile 与能力并记录固定日志事件。
- **标签**：Profile 定义新增可选 `label`（≤ 64 个可打印字符、无首尾空白）；生产配置未设置时显示 ID。生产配置在新代码下只读加载通过，未修改。

## 自动测试

| 检查 | 结果 |
| --- | --- |
| `gofmt -l` | 无输出 |
| `go vet ./...` | 通过 |
| `go test -count=1 ./...` | 9 个包全部 `ok`，模块共 138 个测试函数，其中本项新增 12 个 |
| `go test -race ./...` | 9 个包全部 `ok`；在 checks 镜像 `ac6c880d627b`（含 gcc）内以只读源码、`--network none`、临时 tmpfs 运行 |

新增测试覆盖：

| 场景 | 位置 | 结果 |
| --- | --- | --- |
| 摘要只读：运行中 Profile 无缓存时未观测，缓存后带采样时间/有效期/环境身份，过期后 stale+unknown，全程 observe/launch/stop/resume 调用不变 | `profile/environment_test.go` | 通过 |
| 摘要不含 journal 能力：JSON 中无 operation/session_id/bootstrap/idempotency/sha256/last_error 键与值 | 同上 | 通过 |
| 受管理 DIRECT 代次报告 `direct`；停止后状态 stopped 且不再沿用旧代次 healthy；未知 Profile 返回未找到；取消的上下文不产生摘要 | 同上 | 通过 |
| 无 lifecycle/无绑定的旧配置仍能列出定义字段（标签、Wayland、语言、时区），未观测 | 同上 | 通过 |
| 标签校验：空/中文/64 字符通过；首尾空白、换行、制表、65 字符、非法 UTF-8、控制字符拒绝 | 同上、`config/config_test.go` | 通过 |
| 网关：未登录 303/401、POST 405、非管理路径 404；授权列表只含本账号 Profile 并按 ID 排序，能力为 `view,start`；HEAD 允许 | `access/manage_test.go` | 通过 |
| 网关：禁用账号、账号表缺失、注销后列表立即不可用；首页含管理链接 | 同上 | 通过 |
| 处理器：无网关时两个路径 404 且不读取摘要；列表只含授权条目、未知 Profile 被跳过；页面无脚本、CSP `default-src 'none'`、`no-store`；页面不显示完整产物摘要 | `httpapi/manage_test.go` | 通过 |
| 处理器：摘要失败时保留该行但不含错误文本；空授权页面提示无环境 | 同上 | 通过 |
| 真实网关端到端：alice 只见 personal、bob 见 personal+work、匿名 401、POST 405、管理授权不放宽固定入口的跨 Profile 404、不触发 Ensure/Health | `httpapi/manage_gateway_test.go` | 通过 |

## 未测与保留范围

- 没有在真实浏览器、Trilium WebView 或目标 Mac 上打开 `/manage/`；没有部署生产，也没有用真实控制器/QA Home 运行新二进制。真实客户端与组合验收归管理面第 5 步。
- 健康证据只来自现有缓存报告；列表不新增观测项，不改变 R1 健康报告的语义或 60 秒有效期。
- 关闭按钮、指纹选择、代理草稿、launch plan 与审计事件均未实现；账号表没有新的能力字段。
- R2 的退出全部登录与 Debian 13 验收不受本项影响，仍待外部条件。
