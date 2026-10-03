# DEV-144 · BiDi端口就绪早于初始文档可观察

状态：已完成本项处理、最终验收及部署（2026-10-03）。关联[R6AW](../work-items/R6AW-2026-10-02-protected-builtins.md)。

矩阵v2首个Camoufox任务在初始A0页面探针读取document.title时返回`script.evaluate failed: unknown error`，未进入动态输入验收。端口已通但BiDi初始文档仍不可读；原DEV-110只对no such frame做等待，其他错误立即失败。原失败报告、正常关闭与合成Home保留，未发布。

处理：把初始页面就绪轮询独立出来，在30秒总窗口内每次重新读取顶层上下文，只有观察到预期HTTPS初始页面标题才继续。仅初始script.evaluate的no such frame/unknown error可有界重试并记录次数/原因；其他错误和所有后续指纹、存储、网络、输入断言仍立即失败。持续unknown error必须耗尽窗口并拒绝，不能跳过任一次Home重建。增加暂态恢复、持续失败和非暂态立即失败回归，完整矩阵另以新作业执行。

最终复核：R6AW v6完整24组合、四份固定Camoufox桌面补验、真实包/安装拒绝和实际部署均通过，原失败及早期诊断保持各自范围，详见[R6AW最终验收](../../infra/sealskin/r6aw-builtins-acceptance-2026-10-03.md)。本条不扩大供应商或其他主机性能的验证范围。
