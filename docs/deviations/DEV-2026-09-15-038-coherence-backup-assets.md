# DEV-038 · 组合恢复缺少一致性资产目录

状态：已解决（代码/隔离 QA，未部署）。工作项：[R5E](../work-items/R5E-2026-09-15-release-combination.md)。

预期：S05 加密恢复必须保留运行策略所引用的环境/验收/GeoIP 材料；启用 coherence 的恢复环境不能因为备份遗漏合法资产而永久 UNKNOWN。

2026-09-15 组合准备代码核对：`coherence` 契约要求环境、完整成功报告和 GeoIP 从控制器 `coherence-assets/` 私有目录读取；`secure-backup.py collect_control_sources()` 收集应用、策略、状态、密钥及代次日志，却未收集该目录。原 R5B 真实恢复早于 coherence，R5D 真实 QA 未启用 coherence，因此其 PASS 不覆盖这个组合。R2A 的旧生产也没有此引用，保留原验收范围。

处理选择：修复共享加密备份来源，补所需一致性资产/引用完整性验证，使用启用 coherence 的 r7 隔离恢复验证。缺失、摘要或成员异常仍拒绝，不能靠关闭一致性策略使恢复通过。不改变实际环境要求或 S05 条件。

实现进展：共享归档增加 `coherence-assets/`；创建与解密验证都检查全部策略引用的直接路径、摘要、私有权限和大小上限，来源另拒绝硬链接/异属文件。`backup-tests-1/` 中原 80 项与新 21 项共 **101 passed，0 skipped**，包括新/旧格式往返、缺失/漂移/越界/不安全资产和已认证但与策略不符的归档拒绝。QA 夹具已清理；`backup-restore-1/` 与 `recovered-client-1/` 已证明实际组合在新根恢复全部三个一致性资产、Store/授权及三类浏览器数据。两次版本核对一致，QA/远端/DNS 清理完成。

验证与收尾：2026-09-15 完成 [R5E 验收](../../infra/sealskin/release-combination-acceptance-2026-09-15.md)，偏差、组件/规格/进度及索引同步。JSON 格式比较和 QA 端口配置的失败与修正保留在报告中；真实 Home/整机恢复仍归 R2。
