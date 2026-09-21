# DEV-063 · Work QA 未识别 Firefox 进程形态

状态：已解决（工具修复、R7B 第六轮与清理通过）。日期：2026-09-21。
关联：[R7B](../work-items/R7B-2026-09-21-managed-work-egress.md)。

R7B 首轮独立 QA 已正常启动生产兼容的 Firefox legacy / Wayland Worker、Guard 与 DIRECT Relay，但验收脚本等待浏览器进程身份时超时。首轮现场曾出现 `--remote-debugging-port=9228`，首版诊断器只接受独立 `--remote-debugging-port`；修正后第二轮又确认容器内 root 因 `/proc` 权限不能读取普通用户 Firefox 的 `environ`，原脚本捕获该错误后跳过整个进程。两者都会把已运行的唯一浏览器误报为缺失。

影响仅限新增 QA 诊断器；浏览器、网络控制器和生产环境未因此变更。首轮失败目录保留，失败后按 reservation 精确调用正常 Stop，已确认该独立 QA Home 的 record、Worker 与网络资源均归零；真实 Personal 和已停用 Work 未参与。

决定：诊断器同时接受独立参数与 `--remote-debugging-port=<port>` 形式，仍要求进程可执行文件为 Firefox 且恰好只有一个匹配项；身份扫描只读公开的命令行、UID 与启动时间，再以该进程 UID 读取环境和文件描述符，要求 `WAYLAND_DISPLAY` 且实际持有 Wayland 资源，不以仅有 Xwayland 进程冒充原生 Wayland。重跑入口先只读检查当前 Home，空运行态不重复 Stop，非空时仅允许停止与准备阶段精确一致的初始 QA 代次。两轮失败均按 reservation 精确正常 Stop 并确认资源归零；R7B 完整重跑、资源清理和生产不变性通过后再标为已解决。

最终结果：第六轮识别唯一原生 Wayland Firefox 并完成全部网络/换代检查；最终 QA 资源和设施清零，生产保持，见 [R7B 验收](../../infra/sealskin/r7b-managed-work-egress-acceptance-2026-09-21.md)。
