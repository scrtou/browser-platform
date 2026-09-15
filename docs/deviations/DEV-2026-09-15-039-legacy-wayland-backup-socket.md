# DEV-039 · 旧 Wayland 运行时 socket 阻断 Home 加密备份

状态：已解决（代码/QA）。工作项：[R2B](../work-items/R2B-2026-09-15-legacy-browser-recovery.md)。发现日期：2026-09-15。解决日期：2026-09-15。

R2B 使用实际旧 Firefox 镜像，BiDi `browser.close` 确认 Firefox 正常退出后，原生命周期停止 Worker 并确认 Home 无占用。第一次 `create-legacy` 仍返回 `BACKUP_FILE_TYPE_UNSUPPORTED`：Home 中残留 `.XDG/wayland-1` Unix socket。R2A 文件夹具没有桌面运行时节点，未覆盖这个实际行为。失败证据保留在被忽略的本项运行目录。

选择修复实现：停止/无占用前提保持，只排除 Home 顶层 `.XDG/wayland-<数字>` 且真实类型为 Unix socket 的运行时节点；不删除或读取 socket，不排除整个目录，不静默忽略其他特殊类型。记录排除清单并在密文发布前复核；归档校验拒绝伪造/冲突清单，恢复不重建旧 socket。普通文件与安全链接仍按原规则归档，FIFO、设备和未知 socket 继续拒绝。

验收：运行时节点边界、旧/新格式及 coherence 回归 115 项通过；真实旧 Firefox/Wayland Home 完成 age 加密、新私有根恢复和三类存储读回。生产 Home、会话和配置没有改动；正常关闭这一前置条件仍不能由排除规则代替。
