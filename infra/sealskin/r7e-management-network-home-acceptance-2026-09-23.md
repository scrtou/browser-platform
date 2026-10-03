# R7E · 管理页网络代理与首页工作区验收

日期：2026-09-23。范围：当前工作树中的 Adapter R7E 候选；**未部署**，未操作生产 Personal、Work、Home、账号、Session 或代理凭据。R7F 承接隔离发布、目标 Mac/Trilium 页面视觉与生产复核。

## 核对结果

| 场景 | 结果与边界 |
| --- | --- |
| 网络代理 Tab | capability 开启时显示脱敏名称、协议、认证、部分遮盖的 host:port、状态、探针码/实际探针时间、引用数和 revision；关闭或服务不可用时 Tab 不显示。创建、探针、停用、撤销仍走 R7C 管理 API、网关 CSRF/Origin、近期密码确认与服务层幂等/引用门槛。凭据、Secret Store 引用和 CA 内容不进入 HTML。 |
| 浏览器配置 | 新建和停止后模板应用分别显示浏览器、指纹、显示模板下拉，选项由 accepted 兼容目录产生；服务端再次验证三元组合。代理下拉仅给出当前可用的受管理 DIRECT 或适用的 accepted 修订，手填 policy ID/SHA 不作为新目录路径。目录为空时新建表单禁用，不退回底层输入。运行中绑定仍由 R7C/R7D 拒绝。 |
| 首页 | 网关只向只读 provider 传入当前账号获授权的 Profile，并再次过滤 provider 返回值；页面显示缓存状态、健康、网络、模板和采样时间。过期健康显示未知，未配置网络显示需要处理。普通账号无管理入口；首页不执行探针或生命周期操作，不输出 Home 路径、Session URL、Cookie、secret 引用或完整策略摘要。 |
| 响应式与操作边界 | 首页与管理页含 viewport、语义区域、显式标签和窄屏 CSS；1280×800 与窄屏合同由 DOM/CSS 测试核对。页面不依赖外部资源或 JavaScript。目标 Mac/Trilium 实际视觉仍归 R7F。 |

验证：本地 Go 1.27.1 执行 `go test -count=1 ./...`、`go vet ./...`、gofmt 与 `git diff --check` 均通过；固定 Go 容器中的 httpapi/access/profile `go test -race -count=1` 通过。R7E 回归覆盖 Tab 能力门槛与脱敏、表单回跳、三类下拉、空目录关闭、授权首页与过期健康。`probe_at` 的旧目录可选字段及成功/失败探针持久化见 [DEV-068](../../docs/deviations/DEV-2026-09-23-068-network-probe-time.md)。

本报告证明未部署候选的代码与静态页面契约；真实 Mac 视觉、生产目录、Work 公网恢复及发布回退尚无本项证据。
