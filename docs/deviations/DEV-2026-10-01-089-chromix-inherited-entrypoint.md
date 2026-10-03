# DEV-089 · Chromix 候选继承旧引擎入口

状态：已解决。关联 [R6L](../work-items/R6L-2026-10-01-chromix.md)，选择修复实现。

设计要求 Chromix 用自己的固定包/环境校验，并保留原显示认证。首个候选镜像复用了已验收桌面层，却继承 Camoufox 的 ENTRYPOINT；真实 /init QA 在启动显示前以 ENVIRONMENT_ARTIFACT_INVALID 退出。无生产影响，失败候选未登记模板或部署。

修复：镜像显式声明 Chromix 入口，启动前校验专用环境/二进制后交给 /init；桌面用户仍通过独立启动器持有 Home 锁，root 不运行浏览器。保留失败 QA 的日志和输入，重建新内容摘要镜像并重做真实桌面验收，不能以版本输出代替通过。

最终 Worker cd521d91… 的真实桌面、控制器两条网络路径、正常关闭/拒绝、管理创建和加密恢复通过，见 [R6L 验收](../../infra/sealskin/r6l-chromix-acceptance-2026-10-01.md)。失败镜像未部署。
