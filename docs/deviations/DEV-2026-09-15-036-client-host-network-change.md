# DEV-036 · QA Chromium 共享宿主网络导致启动请求取消

状态：已解决（隔离 QA 环境）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

预期：真实客户端在独立网络环境访问入口；控制器为 Worker 建立网络不应改变客户端的网络接口。

实测：R5D `client-qa-5` / `client-qa-6` 已通过未登录、错误密码、Profile 与 CSRF 拒绝。随后 Chromium 151 在固定入口的 POST 发出约 0.3 秒后报告 `net::ERR_NETWORK_CHANGED`。客户端容器使用 `--network host`，恰好与控制器创建代次网络同时发生。控制器继续完成 Worker 启动，Adapter 对已断开的请求保留 unknown 占用；普通对账恢复了同一 Session，正常停止释放该测试代次。未发现重复 Worker。

证据：被忽略的 `infra/sealskin/runtime/r5d-entry-auth-2026-09-14/client-qa-6/display-*.json` 记录请求时序和 Chromium 错误；第五轮保留正常对账/停止输出。不得把客户端环境导致的失败写成真实显示验收通过。

处理选择：修复 QA 环境。第七轮使用 internal Docker 网络和网关地址转发，但客户端至宿主的连接超时，该轮监听/网络已清理。最终采用 `--network none` 的独立客户端网络命名空间，经专属 Unix socket 转发到固定 QA Caddy loopback 端口；socket 目录 0700、文件 0600，并核对对端 UID。客户端只在自己的 loopback 监听 TLS 转发。TLS、Host、真实表单、Cookie 与 WebSocket 仍端到端验证；不改宿主防火墙、不关闭客户端网络变化检测、不放宽 TLS/授权门槛。结束时关闭并移除专属 socket 和客户端。

须验证：原固定入口启动完成、真实二进制显示帧到达、原矩阵继续执行、错误 UID 拒绝、临时监听/socket 清理。生产 Caddy、线上容器和真实 Home 不参与。

2026-09-15 最终验证：独立网络命名空间与专属 Unix socket 方案通过 `client-qa-13/` 全部 13 项，收到 2,180 个二进制显示帧；错误 UID 的实际连接拒绝。每轮客户端/转发 socket 已清理，`cleanup-1/` 另确认 Adapter/Caddy/QA Docker 代理及 loopback 监听清理，生产身份/配置保持。旧失败及其同代次对账证据保留，见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
