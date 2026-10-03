# DEV-109 · 冻结执行器缺少动态验收客户端缓存路径

状态：已解决，R6S服务器验收并部署。关联 [R6S](../work-items/R6S-2026-10-01-shared-display-templates.md)。

源码目录下动态显示诊断通过，但完整冻结 runner 以自身目录推导 Playwright 缓存，Docker bind source 不存在，首个组合在浏览器启动前失败。失败报告保留在 R6S integration，不进入发布目录。

处理：将客户端缓存作为显式 runner 参数传入动态验收；部署单元固定该路径，并纳入依赖核对。使用新作业完成实际验收，不覆盖已有失败报告。

最终验证（2026-10-01）：冻结runner显式绑定客户端缓存，动态验收和最终发布依赖摘要检查通过，运行单元已更新。 证据根为 `infra/sealskin/runtime/r6s-shared-display-20261001/`，见[R6S最终验收](../../infra/sealskin/r6s-shared-display-acceptance-2026-10-01.md)。
