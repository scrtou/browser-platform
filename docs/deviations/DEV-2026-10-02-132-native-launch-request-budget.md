# DEV-132 · 原生启动请求仍使用普通超时

关联：[R6AS](../work-items/R6AS-2026-10-02-fixed-version-matrix.md)。状态：已解决（R6AS）。

设计预期：控制器按顺序完成网络预检、Guard/Relay、Worker与显示就绪后才返回启动结果；Adapter等待有界长操作，不因普通查询预算提前丢弃正常启动结果。真正不确定的响应仍保留unknown与Home占用，禁止盲目重发。

实测：独立机原生Firefox DIRECT固定入口于15:58:48开始，15:59:36返回409，Adapter记录`SealSkin request result is ambiguous`，控制器代次已running且Worker存在。普通客户端固定45秒；resume/probe/coherence已使用180秒长客户端，LaunchURL仍走普通客户端。原失败位于`r6as-fixed-matrix-20261002/firefox/direct/entry-1/`和Adapter日志。此前全部18协议、三引擎程序升级/回退及另外两引擎DIRECT通过，不覆盖此慢启动边界。

处理：仅将LaunchURL纳入现有180秒长操作预算，保留幂等键、单次发送、上下文取消及AmbiguousMutationError语义。增加有界延迟响应/取消回归，基于R6AR精确源码形成最小候选；通过完整Go回归、实际慢启动与剩余Firefox阶段后部署Adapter。原unknown代次通过当前正常控制入口安全关闭，Home和失败记录保留；不手工清空状态。

候选验证：新增真实HTTP延迟/取消测试在旧实现的慢启动场景稳定失败，在修正后通过；候选与工作树完整Go test/vet通过，精确R6AR基线上仅2路径差异，121文件补丁重放一致。两次真实Firefox启动响应各额外延迟50秒后，固定入口均成功且没有重复launch，原unknown通过正常安全关闭恢复，正常控制器入口已恢复。剩余DIRECT故障/恢复及部署继续核验。

最终结果：三引擎范围内验收与资源清理通过；R6AS最终Adapter已部署，运行身份/保护核对通过，详见[R6AS验收](../../infra/sealskin/r6as-fixed-version-matrix-acceptance-2026-10-02.md)。
