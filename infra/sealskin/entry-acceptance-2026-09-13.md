# 固定入口启动回归（2026-09-13）

Trilium 打开固定入口后出现 `Cross-origin start request rejected`。使用 Chromium 151.0.7922.34 复现：入口页原来的 `Referrer-Policy: no-referrer` 使自动表单 POST 携带 `Origin: null`，被 Adapter 同源校验拒绝。另一个阻塞是 `form-action 'self'`：Chromium 会对表单的重定向目标继续应用该 CSP，因而拦截到独立 Session 域名的跳转。

入口页现使用 `Referrer-Policy: same-origin`，`form-action` 允许入口自身和配置的 `https://mysession.azhen.de`。启动与 bootstrap 重定向仍使用 `no-store`、`no-referrer`；`Origin: null` 和异源启动请求仍返回 403。

## 验证

Go 全部测试、`go vet ./...`、构建及 `git diff --check` 通过。回归测试覆盖入口策略、同源 POST、Session 重定向，以及拒绝不透明来源、外部来源、伪造域名后缀和 HTTP 降级来源。

真实 Chromium 客户端验证了以下路径，均保持 HTTPS 证书校验：

| 路径 | Profile | 入口 GET | 启动 POST | Session 页面 |
| --- | --- | --- | --- | --- |
| 直接访问本机 Caddy，保留原域名和 TLS | Personal | 200 | 303 | 200 |
| 直接访问本机 Caddy，保留原域名和 TLS | Work | 200 | 303 | 200 |
| 公网 Cloudflare → Caddy | Personal | 200 | 303 | 200 |
| 公网 Cloudflare → Caddy | Work | 200 | 303 | 200 |

四次启动均携带 `Origin: https://mybrowser.azhen.de`，成功加载 Selkies 页面中的 `#overlayInput`，没有 `form-action` 拦截；Session 导航链中没有 Referer。验证客户端使用本地模拟 WebSocket，不连接 Worker 的显示通道，也不发送尺寸或输入指令。本次自动化验证范围是入口与跳转。

用户随后确认 Personal 和 Work 在 Trilium 中均可正常查看，并补充客户端为 **Trilium 0.105.0、macOS Sequoia 15.1**。用户确认中文输入、缩放和滚动正常，能正常恢复会话；复制粘贴失败，单独排查。显示缩放比例、具体输入法和 screen/DPR 观测尚未提供；不能把恢复会话的反馈扩大为主机重启或网络故障恢复验收。

剪贴板排查已确认 Trilium 的 WebView 权限限制，并完成禁用 Async Clipboard API 时的手动面板双向文本隔离测试。用户随后在 Mac 上复测并确认手动面板路径通过；自动同步仍未启用，见 [Trilium 客户端记录](../../docs/trilium-client.md)。

部署只更新并重启 `profile-adapter.service`。更新后 `/readyz` 返回 200；原有两个 Firefox Worker、Relay 和 SealSkin 的容器 ID、启动时间、配置及网络一致，Adapter 配置和会话绑定文件 SHA-256 一致。所有临时验证客户端均已清理。

已部署二进制 SHA-256：`b48efae76ca6fa213ef5dc3fb634a72e4f75edeb0b614ce3526a6cb22aa0fb96`。原二进制保存在主机 `/home/sshUser/.local/lib/browser-platform/profile-adapter.before-entry-fix-20260913`，可用于回滚；Camoufox 冻结镜像和环境产物未修改。
