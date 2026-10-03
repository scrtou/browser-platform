# R6K 本机隔离灾备验收 · 2026-10-01

结论：用户选择的本机隔离演练已完成。一个合成 Work/Firefox Wayland Home 从加密归档恢复到新目录后，真实服务启动、数据读回和受控回退均通过。生产未部署或重建；独立主机冷恢复仍待资源。

## 版本与范围

- 控制器：`sha256:ad21dd6de070fce88e59a6c32fd213c017fcb587dffd3cac907693cb7b3b6525`（R6J1 日志专用版本）。
- Adapter：`7f4e2a1aee6c79de904e19b2e40c2c69c6ec39152fbc0ff13798db6ef1c49635`。
- Work 镜像：`sha256:895907b7cecf793db5b5b108e9a9ac371d0d381833e729d0b5cc16f8eee8e356`。
- Relay/Guard：`sha256:a785d443bf7ede16e0f4728bbcc552a17f6340e6a3fea2d01bd839776716888a`；探测镜像：`sha256:d52c155eb78882b27c7780e77df335939d46cd06a514c9fa310039307542ee6a`。

上述镜像均使用本机缓存，没有执行镜像导出或异机导入。QA 独立账号、Home、Store、网络和控制根，未使用生产供应方凭据。备份工具补齐管理依赖，见 [DEV-088](../../docs/deviations/DEV-2026-10-01-088-adapter-recovery-dependencies.md)。

## 实测结果

| 场景 | 结果 |
| --- | --- |
| 前置 Work 迁移 QA | 8 项检查通过 |
| 加密归档、认证校验、独立解密 | 284 条目，约 69.85 MiB；通过 |
| 错误 age 身份、损坏密文 | 均拒绝，未创建恢复目标 |
| 访问审查与恢复锁 | 未激活 Store 拒绝使用；缺少当前账号输入拒绝激活 |
| 最新权限合并 | 备份后禁用账号登录被拒绝，撤销的 secret 版本保持不可用 |
| 源退役与新目录 | 原服务、网络、挂载退役；原路径移走后恢复服务启动 |
| 实际浏览器 | 管理员登录、Session 主机显示 HTML 200、Cookie/localStorage/IndexedDB 一致、HTTPS 成功、四类绕过均拒绝、新鲜健康 healthy |
| 正常停止与回退 | 资源归零后返回保留的源检查点，三类存储读回一致；不声称反向同步新写入 |
| 三个真实生产归档 | Work、Personal、“测试”现有 R6J1 密文均离线认证并核对摘要；本轮未激活真实归档 |
| 回归 | 备份相关 124 项、恢复布局 8 项通过；最终 CLI/构造器及暂存工具摘要只读检查通过 |
| 清理与生产保持 | QA 容器/网络/进程/端口/socket/挂载清零，解密 tmpfs 和本轮合成源 Home 删除；生产容器身份、启动时间、配置摘要保持，监控 timer active |

本次备份 0.946 秒、认证校验 0.416 秒、文件恢复 0.587 秒；源退役至恢复数据读回墙钟 66.9 秒，含操作者/工具调度，使用缓存镜像，不能作为 RTO/SLA。

## 证据与限制

私有证据位于被忽略的 `runtime/r6k-disaster-recovery-20261001/`：`backup/`、`recovery-result.json`、`rollback-result.json`、`negative-inputs.json`、`production-archive-verification.json`、`recovery-timing.json`、`cleanup.json`、`final-result.json` 和 `manifest.json`。保留失败尝试日志；敏感输入和解密材料不进入公开文档。

实际运行恢复仅覆盖合成 Work/Firefox。Camoufox 新目录运行恢复、全部生产作业目录/产物依赖闭包、独立主机镜像导入、独立密钥可用性及真实整机灾难均未验证。旧生产归档没有自动获得本次新增依赖成员。异机工作待独立主机或额外磁盘，不能据此宣称全计划灾备完成。R7G/R6I 未部署，共享 journald 预算另列。

操作和重现前置见 [隔离恢复说明](checks/disaster-recovery.md)，工作范围见 [R6K](../../docs/work-items/R6K-2026-10-01-disaster-recovery.md)。
