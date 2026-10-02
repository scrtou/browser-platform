# Adapter 精确发布增量

`r6ar-display-persistence.patch` 以 `server-2026.10.02.2` 发布树的 `adapter/` 为基线。在该目录运行 `git apply /path/to/r6ar-display-persistence.patch`；不能直接套到仍含其他未提交改动的开发工作树。变更覆盖 Profile 百分比保存、管理表单、当前 Session 授权入口、三个已审核 Selkies 资产及对应测试。未知资产不变换，原固定画面逻辑保持。

这是 R6AR 的完整源码增量；独立发布树保存精确可构建源码，开发树已有改动保持。当前部署、验证和回退边界见 [R6AR 工作项](../../../docs/work-items/R6AR-2026-10-02-display-persistence.md) 与 [验收](../r6ar-display-persistence-acceptance-2026-10-02.md)。真实显示运行器为 `../checks/check-display-persistence.py`，需要从补丁后的源码编译 `internal/access` 测试可执行文件，并使用被忽略的独立运行目录。测试不连接生产 Home。
