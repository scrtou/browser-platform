# DEV-127 · 原生异机恢复工具同名模块冲突

状态：已解决（2026-10-02，异机实测通过）。关联 [R6AP](../work-items/R6AP-2026-10-02-remote-recovery.md)。

预期：复用原生引擎回放和 Camoufox 作业 Fixture 时，各自使用自己的 Docker 调用约定；精确镜像和恢复数据不变。

异机第一轮发现 `check-remote-recovery.py` 先以全局名 `acceptance` 导入原生模块，随后 environment-job.py 的同名导入误用它。原生 Docker 包装器接收可变参数，作业模块传入列表，导致创建 QA 网络前抛出 TypeError。没有浏览器数据写入，也没有生产影响。

处理：使用唯一模块名显式加载原生回放模块，保留 Camoufox 包的常规导入；不修改 Fixture 行为或降低运行断言。修复后重新执行同一加密检查点的真实异机恢复、重开与回退。私有失败日志保留在异机 R6AP 的 `remote-native.log`，最终结果另行记录。

更新恢复工具、R6AP 工作项/验收、偏差索引；验证通过后关闭。

最终：R6AP 修复后的真实异机验收通过，原失败保留，见[R6AP 验收](../../infra/sealskin/r6ap-remote-recovery-acceptance-2026-10-02.md)。
