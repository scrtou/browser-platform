# DEV-144 · BiDi端口就绪早于初始文档可观察

状态：处理中。关联[R6AW](../work-items/R6AW-2026-10-02-protected-builtins.md)。

矩阵v2首个Camoufox任务在初始A0页面探针读取document.title时返回`script.evaluate failed: unknown error`，未进入动态输入验收。端口已通但BiDi初始文档仍不可读；原DEV-110只对no such frame做等待，其他错误立即失败。原失败报告、正常关闭与合成Home保留，未发布。

处理：把初始页面就绪轮询独立出来，在30秒总窗口内每次重新读取顶层上下文，只有观察到预期HTTPS初始页面标题才继续。仅初始script.evaluate的no such frame/unknown error可有界重试并记录次数/原因；其他错误和所有后续指纹、存储、网络、输入断言仍立即失败。持续unknown error必须耗尽窗口并拒绝，不能跳过任一次Home重建。增加暂态恢复、持续失败和非暂态立即失败回归，完整矩阵另以新作业执行。
