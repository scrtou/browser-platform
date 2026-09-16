# 文档导航

本项目将背景、方案、计划、事实和操作说明分别维护。首次阅读建议按 **背景 → 架构 → 进度 → 计划** 的顺序；日常使用直接查看客户端或运维说明。

## 主要文档

| 文档 | 负责回答 | 更新时机 |
| --- | --- | --- |
| [工作流程指导](workflow.md) | 先读什么、先看什么代码、怎样实施与收尾 | 工作约定变化 |
| [工作项记录](work-items/README.md) | 当前正在执行哪项、是否完成收尾 | 开始、实施、验收与结束时 |
| [设计偏差记录](deviations/README.md) | 实现与设计哪里不同、如何处理 | 发现差异时立即记录并同步 |
| [开发背景与目标](background.md) | 为什么做、服务谁、范围是什么 | 产品目标或范围变化 |
| [当前架构与决策](design.md) | 组件职责、数据归属、技术选择 | 架构或关键决策变化 |
| [开发进度](progress.md) | 已完成、已部署、何时生效、尚未验证 | 开发交付、部署或验收后 |
| [开发计划](roadmap.md) | 下一步顺序、依赖、交付与验收条件 | 优先级或工作范围变化 |
| [运维、开机与恢复](operations.md) | 如何检查、启动、停止、恢复、回滚 | 运维流程变化 |
| [Trilium 客户端](trilium-client.md) | 接入 URL、键盘、剪贴板、文件、黑框恢复 | 用户操作或客户端验收变化 |
| [客户端验收矩阵](client-matrix.md) | Linux QA 与目标 Mac/Trilium 分项结果、实机记录方法 | 客户端验收后 |
| [代理与环境规格](specs/proxy-environment/README.md) | 目标契约、数据示例、P/E/C/N/H/S 验收要求 | 契约或能力边界变化 |
| [验收索引](acceptance/README.md) | 每项结论对应哪份证据、覆盖哪个环境 | 新增验收记录后 |
| [SealSkin 上游审计](sealskin-0.3.2-audit.md) | 固定上游版本的问题与本地处理 | 上游升级或补丁范围变化 |
| [历史资料](archive/README.md) | 原长篇设计、旧里程碑与整理前清单 | 归档时，之后不追写当前进度 |

## 组件文档

命令、路径、构建参数与回滚细节保留在代码旁，避免复制多份操作步骤。

| 组件 | 说明 |
| --- | --- |
| [Adapter](../adapter/README.md) | 固定入口、配置、构建、运维 socket |
| [入口登录与 Session 访问](../infra/sealskin/entry-auth/README.md) | 短期 Cookie、主体/Profile/Session 授权、私有 HTTPS、账号管理、状态与日志边界 |
| [SealSkin 部署](../infra/sealskin/README.md) | Compose、Caddy、证书、用户服务 |
| [生命周期补丁](../infra/sealskin/lifecycle/README.md) | Home 对账、Guard/Relay/网络、安装与回滚 |
| [受管理 DIRECT](../infra/sealskin/lifecycle/direct-network.md) | 无外部上游的专属网关、批准解析器、宿主机地址证据、初始页与隔离 QA |
| [运行时一致性与会话放行](../infra/sealskin/lifecycle/runtime-coherence.md) | 真实浏览器/出口/网络报告、代次门槛、历史比较、探测与恢复 |
| [代理引导 DNS 与 TTL](../infra/sealskin/lifecycle/bootstrap-dns.md) | 固定批准解析器、代次回答/TTL、恢复绑定与公开 DNS 采样材料 |
| [专用公开权威 DNS](../infra/sealskin/checks/public-dns-authority/README.md) | QA zone、Cloudflare 委派清单、端口维护提案、区域轮换与资源条件 |
| [公开测试端点](../infra/sealskin/checks/public-dns-endpoint/README.md) | 外部机器的轻量网站/受限代理、固定离线包、隔离验证与清理 |
| [Secret Store 与加密恢复](../infra/sealskin/lifecycle/secret-store.md) | 加密版本、精确授权、tmpfs 租约、撤销、age 备份与旧部署只读快照/离线恢复 |
| [Relay](../relay/README.md) | 内部 SOCKS5、上游协议/认证矩阵、凭据边界、镜像构建 |
| [Firefox Worker](../infra/firefox-proxy/README.md) | 代理锁定、X11 环境启动校验及 Work Wayland 版本边界 |
| [Camoufox](../infra/camoufox/README.md) | 固定依赖、完整环境产物、独立应用验收 |
| [浏览器正常退出层](../infra/browser-runtime/README.md) | X11 与固定 Work Wayland 关闭、服务停止顺序、失败保留与新镜像绑定 |
| [Worker 显示认证层](../infra/browser-access/README.md) | Session 专属 tmpfs、nginx/Selkies 认证材料、恢复校验与日志边界 |

## 维护规则

实施工作先遵循 [工作流程指导](workflow.md)：本项经过验收复核并更新文档、进度、计划及工作项记录后，才能开始下一项。

1. **当前进度只在 [progress.md](progress.md) 汇总。** 写清记录日期、目标环境以及“代码完成 / QA 通过 / 已部署 / 新会话生效”的区别；不要把 HTTP 200 写成完整功能通过。
2. **计划写下一步和完成条件。** 已完成事项转入进度并附证据，不继续在设计、计划和组件 README 中堆叠重复流水账。
3. **规格写要求，验收写事实。** “必须支持”不等于已经实现；同版本 QA 恢复不等于真实 Home 迁移，独立 daemon 测试不等于生产 VPS 重启。
4. **验收报告保留当时结论。** 新报告替代旧范围时，加上后续报告链接；不要把旧失败改写成旧版本当时通过。
5. **新增文档登记入口，移动文件修复链接。** `design.md` 继续作为架构入口，`next-steps.md` 保留为跳转页；旧编号章节在规格或历史设计中可查。
6. **公开文档只放脱敏证据。** `infra/**/runtime/` 是被 Git 忽略的本机材料，干净检出不包含它；凭据、私钥、带授权参数的 Session URL 不进入文档。

若概览与验收描述不一致，先核对报告日期、版本和适用环境，再更新进度；较新的 QA 报告不能自动覆盖未迁移的存量会话。
