# DEV-083 · 成功恢复后残留错误阻止控制器接入

状态：已解决（隔离候选，未部署）。发现日期：2026-09-30。工作项：[R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md)。

预期：失败恢复保留 pending 和阻断；故障解除并由合法维护恢复所属 Relay 后，下一次控制器恢复应核对旧 lease/规则、清除当前故障并重接原地址，Worker 不重启。

实际：`_recover_pending` 成功移除 pending 后仍保留先前的 `NETWORK_DYNAMIC_ENDPOINT_ROLLBACK_FAILED`。`restore_controller_attachment` 因这个旧错误拒绝重接，即使规则已经恢复。新增回归先真实调用失败分支、恢复 Relay，再替换控制器；旧候选返回 failed，与预期 attached 不符。

处理选择：仅在已证明旧 lease/规则恢复成功后清除当前 `last_error`；失败分支继续保留 pending/错误。新增模型回归和独立 Docker 实机重试检查；先前失败证据保留，不修改生产。

验证：旧候选新增回归失败，修复后网络/DNS 140 项、QA 工具 107 项、完整控制器 557 项通过；四组真实控制器中断/恢复（含首次失败、修复后替换重试）通过。35 个实际安装文件与 manifest 一致；QA 清零且生产快照一致。见[实机恢复验收](../../infra/sealskin/r7g-controller-recovery-acceptance-2026-09-30.md)。
