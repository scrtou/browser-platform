# DEV-2026-10-01-087 · 日志专用候选目录权限

工作项：[R6J1](../work-items/R6J1-2026-10-01-log-deployment.md)。状态：已解决，选择修复构建实现。

预期保留生产全部 overlay 及目录权限。首个隔离候选对目录使用 COPY --chmod=644，使 providers 目录不可遍历，QA 控制器导入失败。尚未部署生产。改为逐文件 COPY，核对完整应用内容及权限，重新准备隔离 QA；原失败证据保留在私有 r6j1-log-deployment-20261001/qa-controller-failure.log。完成条件不变。

修复验证：逐文件 COPY 后对运行候选完整导出比对，97 文件内容符合两改一增，所有原文件及目录权限保持；550 项回归与真实 Worker/Relay/Guard/probe 创建、HTTPS、禁止直连、正常启停通过。证据 installed-audit.json、qa-result.json。
