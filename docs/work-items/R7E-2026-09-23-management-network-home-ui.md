# R7E · 管理页网络代理 Tab 与首页工作区

状态：已收尾（离线候选）。开始/收尾日期：2026-09-23。候选未部署。

对应计划：[R7 第 5 步](../roadmap.md#r7)。代码入口：`access.Gateway` 根页与只读 `HomeProvider`、`httpapi.managePage`、R7C `NetworkProfiles` 与 R7D `CompatibleTemplates`；写入继续由现有管理 API、Profile 服务和生命周期锁负责。开始时工作区已有 R7C/R7D 及部分 R7E 未提交改动，均保留。

## 范围

- 承接 R7D 已验证的模板/回退服务端能力与 R7C 统一代理目录，不修改它们的安全边界。
- 管理页新增“网络代理”顶级 Tab：列出脱敏的代理配置修订、状态、探针、引用数和可执行动作；创建/探针/停用/撤销继续调用既有 R7C API，凭据不回显。
- 浏览器页改用服务端可选对象：R7D accepted 模板组合与 R7C accepted 代理修订作为配置来源，不再把 policy ID/SHA 当作普通 UI 主输入。
- 首页 / 从 Profile 文本列表改为服务端渲染工作区：只显示当前账号可访问浏览器、运行/健康/网络/模板摘要、采样时间和授权入口；管理员显示管理入口，普通账号不显示管理操作。
- 响应式目标：1280×800 首屏主要状态可读，窄屏单列；无外部资源、无 JavaScript。

## 安全与副作用

- 本项只改服务端 HTML/只读数据编排和现有 API 的表单入口；不新增绕过 CSRF、reauth、manage grant、revision 或 lifecycle 锁的写路径。
- “网络代理”Tab 的目录创建本身无浏览器运行副作用；绑定仍须 stopped/0-resources 且不会隐式 Stop。
- 首页不显示代理密码、secret refs、Session URL、Cookie、Home 路径、完整 policy SHA 或容器内部地址。
- 不部署、不重启生产 Adapter/控制器，不启动或停止生产 Personal/Work。

## 验收

- [x] 网络代理 Tab 只在 NetworkProfiles capability 开启时显示；关闭时路由/Tab 不泄漏能力。
- [x] 列表包含 label、协议、认证、脱敏 host:port、状态、探针码/时间、引用数、revision；不含 secret refs/CA/凭据。探针时间缺口记录并修复于 [DEV-068](../deviations/DEV-2026-09-23-068-network-probe-time.md)。
- [x] create/probe/disable/revoke 表单保留 CSRF、reauth、幂等与既有错误边界。
- [x] 浏览器配置分别提供服务端 accepted 浏览器/指纹/显示模板及代理选项；组合在服务端复核，低层 X11/Wayland/Selkies 只作为详情。目录为空时禁用新建。
- [x] 首页只列授权 Profile；管理员与普通账号动作边界正确，健康过期/网络未配置不伪装为 healthy。
- [x] 1280×800 与窄屏 DOM/CSS 契约测试通过；全量 Go test/vet/gofmt 与关键包 race 通过。
- [x] 更新[验收](../../infra/sealskin/r7e-management-network-home-acceptance-2026-09-23.md)、组件说明、progress/roadmap；明确未部署及下一项 R7F。

收尾边界：本项仅为未部署 UI 候选。目标 Mac/Trilium 的真实视觉、生产目录生成、Work 公网恢复和发布回退仍属于 R7F；R6H 旧版目标 Mac 视觉复测也不由本项代替。QA 只用测试夹具与隔离 Go 容器，没有创建生产或 QA 浏览器资源。
