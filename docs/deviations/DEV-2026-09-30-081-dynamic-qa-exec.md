# DEV-081 · 动态上游隔离 QA 执行通道缺口

状态：已解决（隔离候选，未部署）。发现日期：2026-09-30。归属：[R7G](../work-items/R7G-2026-09-27-dynamic-upstream-hot-switch.md)。

实际代码核对发现：动态控制器以 root 执行固定 `network-guard.py --apply-only` 并读取摘要；现有 QA Docker 代理仅支持 detached 退出/观测命令，拒绝该调用。因此此前分离的 DNS、FakeDocker、nft 与 Relay 测试不能证明真实控制器监视器已贯通。

处理选择：补齐 QA 工具，限定已批准动态镜像、当前 QA scope/owner/代次 Relay、只读 runtime 挂载与固定命令；不得开放任意 root exec。增加正向及越界拒绝检查，再执行真实控制器集成。生产 Docker 路径与授权不变。验收结果见文末。


2026-09-30 收尾：101 项 QA 边界测试、139 项网络/DNS 专项、556 项完整控制器回归和最终 8 组真实集成通过；所属 Relay 双失败停止、peer 保持及无绕过已验证，QA 清理后生产基线一致。见 [本轮验收](../../infra/sealskin/r7g-controller-integration-acceptance-2026-09-30.md)。旧失败材料保留；公网供应方/目标客户端及实机控制器重启 pending 场景不在本轮通过范围。
