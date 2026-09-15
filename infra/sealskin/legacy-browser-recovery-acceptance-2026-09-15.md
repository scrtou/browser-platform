# R2B · 旧 Firefox 加密备份真实浏览器恢复验收

日期：2026-09-15 UTC。范围：独立 QA，未部署生产。

## 结果

R2B 已通过。使用与当前旧生产 Worker 相同的固定 Firefox 镜像 `sha256:7e3dbebd…9b47f7`，在独立 QA Home 中启动真实 Wayland Firefox，写入 Cookie、localStorage 和 IndexedDB。正常关闭请求先得到确认，Firefox 进程退出后才调用生命周期停止，记录为空且资源已释放。

停止后的旧 Home 通过 `snapshot-legacy`、`create-legacy` 生成真实 age 加密归档，格式为 `browser-platform/encrypted-legacy-backup/v1`。`verify` 完整认证通过；错误 identity 和既有目标分别拒绝，运行中归档拒绝。归档恢复到新私有根后，重新启动同一旧镜像，三类浏览器存储均读回一致，Wayland 进程和旧镜像身份保持。恢复回执保留 `offline_only=true` / `ready_to_activate=false`，没有执行激活。

## 变更与边界

真实旧 Wayland 停止后会遗留 `.XDG/wayland-<数字>` Unix socket。该节点是桌面运行时端点，不是持久浏览器数据；备份现在只排除这个精确路径和 socket 类型，记录在加密 manifest 的 `excluded_runtime_nodes` 中。普通文件、链接和未知特殊文件仍按原规则处理；FIFO、其他 socket、设备和路径变体继续拒绝。[DEV-039](../../docs/deviations/DEV-2026-09-15-039-legacy-wayland-backup-socket.md) 已解决。

旧格式没有 Store、入口账号或密封 Session，不会生成伪造环境产物；恢复只写新目录，不能由 `activate` 直接启用。真实生产 Home、退出登录、linger、VPS/主机重启、Debian 13 和目标 Mac 未在本项执行。

## 验证证据

- 备份核心、旧格式、coherence 和运行时节点回归：115 passed。
- 真实流程私有证据：`infra/sealskin/runtime/r2b-legacy-browser-recovery-2026-09-15/`，包含生产前后摘要、三类存储写入/读回、关闭、快照、age 归档/验证/恢复、错误路径和清理结果。
- `stage-fixtures.json`：源代次先退出、新根 API 身份核对、四容器/五份生产配置及 Git index 保持。
- `read-source-1.json` 与 `read-recovered-1.json`：两次真实 Firefox 三类存储一致、旧镜像一致、Wayland 进程存在。
- `cleanup-fixtures.json`：源/恢复 Worker、QA 控制器、代理、网络和匿名卷清理；监听端口关闭。

生产容器和配置摘要在前后核对中一致；没有读取或复制生产 Home。
