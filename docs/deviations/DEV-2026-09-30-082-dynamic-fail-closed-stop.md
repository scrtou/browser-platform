# DEV-082 · 动态回滚故障的 Relay 停止调用

状态：已解决（隔离候选，未部署）。发现日期：2026-09-30。归属：[R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md)。

真实隔离集成发现：规则执行回执不可读时，候选记录 `NETWORK_DYNAMIC_ENDPOINT_ROLLBACK_FAILED`，但 Relay 仍运行。代码以 `asyncio.to_thread(relay.stop, 10)` 调用 Docker SDK；真实 `Container.stop` 只接受关键字参数，FakeDocker 的位置参数签名掩盖了错误。此前单元/分离测试不能证明该故障分支已停止真实 Relay。

同路径复核还发现 pending 恢复在归属校验异常后进入通用停止分支，未限定已证实归属的 Relay；失败时也会清除 pending。处理选择：修复两个停止调用为 `timeout=10`，仅停止已证实归属的资源，并保留失败 pending，补齐 SDK 签名、恢复失败与其他代次资源保护回归，执行真实 QA 规则更新/回滚双失败注入与 Worker 绕过检查。

影响仅为尚未生产部署的 R7G 候选。R7F/生产使用静态 Relay，保持原运行身份；不得扩大此前验收结论。验证与收尾见文末。


2026-09-30 收尾：101 项 QA 边界测试、139 项网络/DNS 专项、556 项完整控制器回归和最终 8 组真实集成通过；所属 Relay 双失败停止、peer 保持及无绕过已验证，QA 清理后生产基线一致。见 [本轮验收](../../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md)。旧失败材料保留；公网供应方/目标客户端及实机控制器重启 pending 场景不在本轮通过范围。
