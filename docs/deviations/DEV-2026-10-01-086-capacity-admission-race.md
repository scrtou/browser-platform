# DEV-086 · 跨 Profile 容量准入竞争

状态：已解决（代码/隔离QA，2026-10-02由R6AI部署）。工作项：[R6I](../work-items/R6I-2026-10-01-capacity.md)。

预期：并发启动和活动 Profile 上限在写占用前生效。源码事实：Ensure 只持各 Profile 锁；checkCapacity 读全局 launching 后另行 atomic.Add，活动计数与 prepareLaunch 也分离。不同 Profile 可同时通过检查并各写占用；launching 的普通读与原子写还存在数据竞争。已有 R3 串行测试不覆盖此窗口。

处理：增加仅覆盖“容量检查 + 持久 reservation + 并发计数”的全局准入锁，远程启动不持此锁；计数释放使用同一锁。保持既有会话复用、未知占用与停止规则。补确定性并发回归和 race，验证前不得宣称容量门槛完整通过。

验证：原 12 请求两组都超限；修复后各 11 拒绝/1 占用。完整 Go test/vet、专项 race 与真实 HTTP 磁盘拒绝/并发唯一/复用/停止释放通过，见[验收](../../infra/sealskin/r6i-capacity-acceptance-2026-10-01.md)。

部署增量：[R6AI](../work-items/R6AI-2026-10-02-capacity-release.md)已发布原子准入及机器自动容量；原R6I报告保留当时未部署事实。
