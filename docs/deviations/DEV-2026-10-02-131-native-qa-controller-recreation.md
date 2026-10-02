# DEV-131 · 原生网络 QA 控制器重建依赖

关联：[R6AS](../work-items/R6AS-2026-10-02-fixed-version-matrix.md)。状态：已解决（R6AS）。

设计要求：DIRECT控制器地址证据丢失后，按当前固定运行配置重建控制器，保留Worker身份、显示认证材料、Home及代次，并重新连接原地址。QA必须复现完整依赖。

实测：Camoufox六协议、程序升级/回退与DIRECT前七阶段通过；旧 `recreate-network-controller.py` 只复制config/storage、socket和地址证据挂载，遗漏当前准备器登记的 `display_runtime_root` → `/run/browser-platform-session-secrets`。当前控制器在恢复阶段无法就绪。该工具还只识别旧Camoufox/Firefox调试进程，且运行器的build记录缺少其最终报告所需release名称，均须补齐原生QA契约。

处理：修复QA工具，验证登记的专属 `/dev/shm/` 路径与挂载归属后保留该依赖；显式识别原生调试进程并保留PID/启动时间断言；在准备时写入固定release标识。修正后重测恢复与清理，不降低握手、显示连通、身份、存储或旁路断言，不修改生产程序。

证据：私有 `r6as-fixed-matrix-20261002/camoufox/direct/recovery-1/`及原 `direct.log`。失败和未完成代次保留，修复完成后补录验证与清理结果。

Camoufox修正后恢复/清理重测通过：两代次、浏览器进程和显示原地址保持，正常退出/恢复与三类存储通过，QA资源最终核验清零。其余原生引擎继续使用同工具验证。

Chromix首组实测补充：`/proc/*/cmdline`重写成单个以空格分隔的进程标题，且renderer也携带调试端口；旧精确argv匹配无法识别主进程。QA只对Chromix规范化标题中的标志，并排除`--type=`子进程，仍断言唯一主进程PID/启动时间；Camoufox/Firefox保留原精确argv路径。身份观察提前到包捕获启动之前，避免身份断言失败留下观察进程。旧失败位于`chromix/protocols-1790951020/`。

最终结果：三引擎范围内验收与资源清理通过；R6AS最终Adapter已部署，运行身份/保护核对通过，详见[R6AS验收](../../infra/sealskin/r6as-fixed-version-matrix-acceptance-2026-10-02.md)。
