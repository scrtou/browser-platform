# R6U · 新增浏览器引擎与指纹联动验收

日期：2026-10-01。结论：服务器实现、隔离交互验证与 Adapter 限定部署通过。对应 [工作项](../../docs/work-items/R6U-2026-10-01-linked-create-templates.md) 和 [DEV-092](../../docs/deviations/DEV-2026-10-01-092-create-template-combination.md)。

## 用户要求与最终行为

新增浏览器保留“引擎”“指纹”两个联动模板下拉。指纹表示该引擎的已验收环境组合，标签包含语言、时区和显示说明；显示配置自动绑定，仅作只读展示。切换引擎立即刷新指纹选项，初始加载、页面恢复事件及重置都重新核对。空目录、目录异常、歧义组合或无可用网络不能提交。

提交仅包含引擎 ID 和产物 ID，由服务端从当前 accepted 目录解析唯一显示。拒绝跨引擎、失效、不允许新建、缺失/重复字段、旧显示字段及旧三元字符串，失败提示刷新重选。历史新建字段不兼容；没有迁移或清理历史数据。现有浏览器编辑和组合生成流程保持各自契约。

## 版本与增量

| 项目 | 结果 |
| --- | --- |
| 前版 Adapter | `b4dc0eb6c144d5b11f06bb7430d89d5b09cf5ada1ce8ab9d1266d4207eb618b3`（R6S） |
| 本次 Adapter | `9102ec88a5c9fdf2b0e63a43eca3c565270601a039148ee1b4cd45926eba13e2` |
| 冻结源 | R6S 基线共 95 文件，6 个变更/新增路径，均位于 HTTP API 包；其中 2 个产品代码路径、4 个测试路径 |
| 构建 | Go 1.27.1，`CGO_ENABLED=0 go build -trimpath -o ../profile-adapter ./cmd/profile-adapter` |
| 客户端 QA | Linux Chromium 151.0.7922.34，独立容器、无网络、无生产 Home |
| 发布范围 | 仅 Adapter 二进制替换及该服务重启；控制器、runner、模板目录、浏览器容器保持；未带入 R6I/R7G |

## 验证结果

| 条件 | 证据与结果 |
| --- | --- |
| 服务端绑定 | 3 引擎 × fixed/auto 共 6 组成功，校验自动派生的显示 ID；13 类非法选择在 CreateBrowser 前拒绝，无创建调用 |
| 入口安全 | 实际 access 网关测试覆盖未登录、非管理员、错误 CSRF/Origin 拒绝及管理员有效创建；全套回归保留既有近期认证边界 |
| HTTP 页面 | 每请求 nonce 与 CSP 对应；标签转义；旧显示选择与手输产物移除；目录内部错误不回显 |
| 合成交互 | 1280/768/390 三宽度，每宽度 3 引擎往返，合计 12 次实际表单提交到隔离模拟传输；核对只有两项模板字段 |
| 交互边界 | 键盘 Tab、模拟 persisted pageshow、表单 reset；空/异常/歧义/无网络四状态；脚本禁用时指纹及提交禁用 |
| CSP | Playwright 响应包含生成页面的真实 HTTP CSP；有 nonce 的联动运行，注入的无 nonce 脚本被阻止；恶意标签不执行 |
| 实际目录 | 只读加载并完整验证 13 个 accepted 绑定：Camoufox 5、Chromix 6、Firefox 2；冻结候选渲染后逐个选择，三宽度无横向溢出，显示回显匹配；人工查看 390 宽截图 |
| Go | 工作树 HTTP API/网关测试及冻结源 `go test ./...`、`go vet ./...` 通过；补充只读目录测试通过 |
| 发布 | `/proc/<pid>/exe` 摘要与候选一致，正确 Host 的 `/readyz` 通过；发布前后保护快照完全相等 |

首次调整测试时，旧三字段预期和 HTML nonce 转义比较未通过；随后按用户确认的新契约更新旧预期，以 HTML 解码后值核对 CSP，并重新完成回归。未放宽 accepted、授权或副作用门槛；首轮失败仅在工具输出中保留，没有单独失败日志。

## 发布保留与回退

私有根：`infra/sealskin/runtime/r6u-linked-create-20261001/`。`deploy.py` 分准备/应用两步，应用前重新核对输入；保留原二进制并原子替换，只重启 `profile-adapter.service`。配置、账号、Profile 目录、网络/模板/环境目录、两个服务 unit、runner 冻结源、作业及产物摘要、控制器镜像、生产容器 ID/启动时间/状态均一致。没有浏览器停止、新建或 Home 操作。

回退材料为该根下 `deployment-backup/profile-adapter`。回退前核对当前二进制身份和发布后的用户修改；只原子替换 Adapter 二进制、重启 Adapter 并检查正确 Host 的 ready，绝不用旧 Profile/账号/目录/作业快照覆盖新数据。应用脚本的失败回退仅在保护快照一致时执行，否则保留现场供核对。本次发布成功，未触发回退。

## 证据与范围

私有证据包含 `adapter-manifest.json`、`adapter-delta.json`、`validation.json`、`go-test.log`、`go-vet.log`、HTTP API/网关日志、`ui/result.json` 及截图、只读实际目录测试日志与 `actual-catalog-ui/result.json`、发布输入/前后快照/结果和旧二进制。公开报告不包含账号、凭据、Session URL 或 resolved application。

本项未在生产新建 QA 浏览器；真实创建副作用沿用未改动的 R6S 生命周期路径，新增选择与绑定通过服务端测试及浏览器表单传输验证。pageshow 使用事件模拟，不能声称真实 bfcache 导航通过。Mac/Trilium 新交互实机反馈仍归客户端计划，R6O 百分比保存及其他审计剩余事项保持独立范围，本次没有开始下一计划。

## 收尾增量

14:22 UTC 新鲜健康采样：Work 和 Chromix 为 healthy，“测试”保持停止/offline；Personal 浏览器/显示正常，原有上游 `PROXY_UPSTREAM_UNKNOWN` 保持，归既有代理出口运维范围。原始报告和脱敏摘要保存在私有根，未据此宣称生产整体健康。

`git diff --check` 通过；本次受影响文档的 998 个本地文件链接均存在，新增规格锚点核对通过。R6U QA 容器为 0，磁盘可用约 4.72 GiB。没有删除既有资源或证据；最终原需求/设计/行为/验收逐项复核通过，DEV-092与本工作项收尾。
