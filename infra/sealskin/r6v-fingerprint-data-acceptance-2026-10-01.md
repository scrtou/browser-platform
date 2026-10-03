# R6V · 指纹数据统一入口验收

日期：2026-10-01。结论：UI 设计、实现、服务器验证与 Adapter 限定部署通过。对应 [工作项](../../docs/work-items/R6V-2026-10-01-fingerprint-data-ui.md) 与 [UI 设计](../../docs/fingerprint-data-ui-design.md)。

## 最终功能

顶级“指纹模板”“显示模板”合为“指纹数据”，内部使用三个原生导航，每次只显示一个功能：

1. 指纹模板：创建通用语言/时区配置，查看已有来源。
2. 显示模板：查看内置自动显示，创建和查看自定义固定显示。
3. 组合验收：选择指纹、引擎和显示，提交验收任务，查看进度/结果与已验收完整组合。

规范地址 `tab=fingerprint-data&section=fingerprints|displays|combinations`。默认/未知 section 回指纹模板；旧 fingerprints/displays/jobs 入口对应三个功能。保存、失败和任务提交返回对应功能，确认密码返回保留合法 section。来源与完整环境分开展示，组合卡片注明引擎/版本、语言/时区、显示和新建资格；未验收来源不能冒充可新建组合。

## 执行方式和版本

用户最初指定本机 agy / Gemini 3.8 Flash。实际调用 `gemini-3.8-flash-high` 在生成前因地区限制被拒绝，用量为 0，无模型设计或实现输出。用户随后明确“你设计和实现”，故由主流程完成；不将本项归属 Gemini。原始回执保存在私有目录。

| 项目 | 版本 / 范围 |
| --- | --- |
| 原 Adapter | `9102ec88a5c9fdf2b0e63a43eca3c565270601a039148ee1b4cd45926eba13e2`（R6U） |
| 当前 Adapter | `949a645ddcbc43298ed807c82b5a862eec3069a0dec60791f47873950bcc708b` |
| 冻结源 | R6U 基础上 96 文件，5 个变更/新增路径；产品代码仅 `internal/httpapi/manage.go`，另外 4 个测试路径 |
| 构建 | Go 1.27.1，`CGO_ENABLED=0 go build -trimpath -o ../profile-adapter ./cmd/profile-adapter` |
| 浏览器 QA | Linux Chromium 151.0.7922.34，独立容器/回环 HTTP 服务，无外部网络或生产 Home |
| 生产维护 | 仅替换 Adapter 二进制并重启该服务；控制器/runner、生产浏览器及数据保持，未包含 R6I/R7G |

## 验证结果

| 完成条件 | 证据与结果 |
| --- | --- |
| 三功能隔离 | 每次只出现对应创建/组合表单，顶级只保留指纹数据；模板列表、内置显示、任务与 accepted 组合展示通过 |
| 导航与返回 | 默认/未知 section、旧入口、合法确认密码 next、保存成功/非法字段/组合 busy 返回正确；无任意 URL 回显 |
| 权限与字段 | 实际 access 网关覆盖三功能匿名/非管理员拒绝，三个 POST 的 CSRF/Origin/管理员校验及合法提交保持；原近期认证和 R6U 新建联动回归通过 |
| 空状态与失败 | 无来源、无引擎、无显示禁用生成；无自定义显示/无任务/无组合有明确提示。来源读取失败为 503，不泄漏内部错误；已失败任务与未验收状态仍按真实状态展示 |
| 实际交互 | 1280/768/390 三宽度，三功能切换；每宽度保存两模板、三引擎提交组合，共 15 次真实表单 POST → 303 → GET，字段集合与返回功能正确 |
| 键盘与脚本 | Tab/Enter 导航、真实前进/后退/刷新及禁用 JavaScript 的三个功能导航通过；模板页无新增脚本，R6U nonce 联动保留 |
| 布局与转义 | 各宽度无页面横向溢出，表格仅局部滚动；长恶意标签不执行且可换行。数字输入高度至少 38px；人工复核宽屏指纹、中屏显示、窄屏组合及修复后截图 |
| Go | 工作树 HTTP API 测试及最终冻结源完整 `go test ./...`、`go vet ./...` 通过 |
| 发布 | 正确 Host 的 ready 通过，运行中 `/proc/<pid>/exe` 与候选摘要一致；发布前后配置/账号/目录/作业/runner/控制器镜像/容器身份快照完全一致 |

## 偏差与证据保留

[DEV-115](../../docs/deviations/DEV-2026-10-01-115-ui-redirect-fixture.md)：首次使用 route.fulfill 的模拟 303 后 GET 未被截获，离线容器报 `ERR_INTERNET_DISCONNECTED`。独立最小诊断确认其为 QA 传输问题，改用回环 HTTP fixture 服务后完整提交/跳转与历史导航通过。

[DEV-116](../../docs/deviations/DEV-2026-10-01-116-display-number-input-style.md)：第一次交互通过后人工发现数字输入未继承共享样式。已限定于指纹数据功能补齐样式，增加实际控件高度核对，完整交互复验和截图复查通过。未把交互 PASS 当成视觉 PASS。

私有根 `infra/sealskin/runtime/r6v-fingerprint-data-20261001/` 保存 agy 原始结果/脱敏回执、冻结源/清单/差异、Go/构建日志、`ui/` 原失败、`redirect-diagnostic.log`、`ui-final/` 首轮交互成功截图、`ui-styled/` 最终 15 个状态页面/9 张截图/结果、发布输入/前后快照及结果。先前冻结和测试证据在 pre-copy-update/pre-style 中保留。

## 回退与范围

该私有根 `deployment-backup/profile-adapter` 为原 R6U 二进制。回退前核对当前二进制身份和用户新写入，只回退二进制并重启 Adapter、检查正确 Host 的 ready；不回放旧 Profile、账号、模板、作业或 Home 快照。失败自动回退仅在保护快照完全一致时执行，否则保留现场。本次成功发布，未触发回退。

本项没有生成新的真实环境或生产 QA 浏览器。生成器、来源格式和组合验收门槛未改；浏览器交互使用合成 fixture，服务端动作另由 handler/网关测试验证。Mac/Trilium 新布局实机反馈仍属客户端计划，不将 Linux QA 扩大为目标客户端通过。本次不开始下一计划。

## 收尾增量

发布后的新鲜健康采样：Work/Chromix healthy，测试保持offline；Personal浏览器/显示正常，原有上游unknown保持。原始报告与脱敏汇总私有保存，未将本项页面更新宣称为上游问题修复。

最终 `git diff --check`、gofmt、受影响文档本地链接与源包匹配检查通过；非本项HTTP API已有改动与初始清单一致。QA容器为0，磁盘可用约4.28GiB。保护快照在健康采样后再次一致。原需求/设计/代码/验收已逐项核对，文档和工作项已收尾。
